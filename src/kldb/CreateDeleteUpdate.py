import os
import logging
from typing import List, Dict, Any, Optional, Union, Generator
from contextlib import contextmanager

from dotenv import load_dotenv
import pandas as pd
from sqlalchemy import create_engine, Table, MetaData, text, and_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine, Connection

load_dotenv()

# Configuração minimalista de log para auditoria corporativa
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Gerenciador de banco PostgreSQL usando SQLAlchemy.
    Suporta inserção/atualização em lote, exclusão e execução de queries arbitrárias.
    Focado em performance (vetorização) e segurança/auditoria de execução.
    """

    def __init__(
        self,
        dbname: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        host: Optional[str] = None,
        port: int = 5432,
        echo: bool = False
    ):
        """Inicializa a conexão com o banco PostgreSQL."""
        dbname = dbname or os.getenv("DBNAMEPOSTGRES")
        user = user or os.getenv("USER_POSTGRES")
        password = password or os.getenv("SENHAPOSTGRES")
        host = host or os.getenv("IPPOSTGRES")

        self.engine: Engine = create_engine(
            f"postgresql+psycopg://{user}:{password}@{host}:{port}/{dbname}",
            echo=echo,
            future=True
        )
        self.metadata = MetaData()
        self.conn: Optional[Connection] = None
        self._transaction_ctx = None

    # ---------------- Context Managers ---------------- #
    def __enter__(self):
        self._transaction_ctx = self.engine.begin()
        self.conn = self._transaction_ctx.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._transaction_ctx:
            self._transaction_ctx.__exit__(exc_type, exc_val, exc_tb)
        self.engine.dispose()

    @contextmanager
    def _get_connection(self) -> Generator[Connection, None, None]:
        """Garante uma conexão ativa, reaproveitando a transação se existir."""
        if self.conn is not None:
            yield self.conn
        else:
            with self.engine.begin() as conn:
                yield conn

    # ---------------- Métodos de Tabela ---------------- #
    def get_table_columns(self, table_name: str) -> List[str]:
        """Retorna as colunas de uma tabela, ignorando a PK 'id'."""
        table = Table(table_name, self.metadata, autoload_with=self.engine)
        return [col.name for col in table.columns if col.name.lower() != 'id']

    # ---------------- Insert / Update ---------------- #
    def insert_or_update_batch(
        self,
        table_name: str,
        data_list: List[Dict[str, Any]],
        unique_fields: List[str],
        batch_size: int = 5000
    ) -> None:
        """Faz upsert (insert ou update) de dados na tabela focando em operações vetorizadas."""
        if not data_list:
            logger.info("Nenhum dado fornecido para insert/update.")
            return

        table = Table(table_name, self.metadata, autoload_with=self.engine)
        valid_cols = [c.name for c in table.columns if c.name.lower() != 'id']

        # Limpeza Vetorizada (Pandas) ao invés de loops iterativos
        df = pd.DataFrame(data_list)
        cols_to_keep = [col for col in valid_cols if col in df.columns]
        
        # Filtra colunas válidas e converte NaNs nativos do Pandas/Numpy para None (NULL em SQL)
        df = df[cols_to_keep].where(pd.notna(df), None)
        cleaned_data = df.to_dict(orient="records")

        total_rows_affected = 0
        total_batches = 0

        with self._get_connection() as conn:
            for i in range(0, len(cleaned_data), batch_size):
                batch = cleaned_data[i:i + batch_size]
                stmt = insert(table).values(batch)
                
                update_cols = {c: stmt.excluded[c] for c in cols_to_keep if c not in unique_fields}
                
                if update_cols:
                    stmt = stmt.on_conflict_do_update(index_elements=unique_fields, set_=update_cols)
                else:
                    stmt = stmt.on_conflict_do_nothing(index_elements=unique_fields)
                
                result = conn.execute(stmt)
                total_rows_affected += result.rowcount
                total_batches += 1
            
            # Log consolidado para evitar poluição no stdout
            logger.info(
                f"Upsert concluído na tabela '{table_name}': "
                f"{total_batches} lote(s) processado(s), {total_rows_affected} linhas afetadas."
            )

    # ---------------- Delete ---------------- #
    def delete_table(self, table_name: str) -> None:
        """Deleta todos os registros de uma tabela."""
        table = Table(table_name, self.metadata, autoload_with=self.engine)
        
        with self._get_connection() as conn:
            deleted = conn.execute(table.delete())
            logger.info(f"Delete: {deleted.rowcount} registros removidos da tabela '{table_name}'.")

    def delete_by_keys(self, table_name: str, keys: Dict[str, List[Any]]) -> None:
        """Deleta registros com base em chaves específicas providenciadas."""
        table = Table(table_name, self.metadata, autoload_with=self.engine)
        conditions = []

        for col_name, values in keys.items():
            if col_name not in table.c:
                raise ValueError(f"A coluna '{col_name}' não existe na tabela '{table_name}'.")
            if values:
                conditions.append(table.c[col_name].in_(values))

        if not conditions:
            logger.warning("Delete ignorado: Nenhuma condição válida fornecida.")
            return

        delete_stmt = table.delete().where(and_(*conditions))

        with self._get_connection() as conn:
            result = conn.execute(delete_stmt)
            logger.info(f"Delete: {result.rowcount} registros removidos da tabela '{table_name}' usando chaves condicionais.")

    # ---------------- Queries Arbitrárias ---------------- #
    def execute_query(self, query: Union[str, text], fetch: bool = True) -> Optional[List[Any]]:
        """Executa queries raw e retorna os resultados se solicitado."""
        stmt = text(query) if isinstance(query, str) else query
        
        with self._get_connection() as conn:
            result = conn.execute(stmt)
            return result.fetchall() if fetch else None

    # ---------------- Fechamento ---------------- #
    def close(self):
        """Encerra a Engine, ideal caso não se utilize contexto (with)."""
        self.engine.dispose()


# ---------------- Forma de Uso ---------------- #
# from database_manager import DatabaseManager
# import pandas as pd

# dados = [
#     {"nome": "Kelvyn", "idade": 26, "email": "kelvyn@example.com"},
#     {"nome": "Maria", "idade": 25, "email": "maria@example.com"},
# ]

# with DatabaseManager() as db:
#     # Inserir ou atualizar registros
#     db.insert_or_update_batch("usuarios", dados, unique_fields=["email"])
#
#     # Deletar todos os registros
#     # db.delete_table("usuarios")
#
#     # Deletar registros específicos por chave
#     # keys = {"email": ["kelvyn@example.com"], "idade": [30]}
#     # db.delete_by_keys("usuarios", keys)
#
#     # Executar query arbitrária e retornar Pandas DataFrame
#     # resultado = db.execute_query("SELECT * FROM usuarios")
#     # df = pd.DataFrame(resultado)
#     # print(df.head())
