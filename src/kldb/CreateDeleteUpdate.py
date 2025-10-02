import os
from typing import List, Dict, Any, Optional, Union
from dotenv import load_dotenv
import pandas as pd
from sqlalchemy import create_engine, Table, MetaData, text, and_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine, Connection

load_dotenv()


class DatabaseManager:
    """
    Gerenciador de banco PostgreSQL usando SQLAlchemy.
    Suporta inserção/atualização em lote, exclusão (total ou condicional) e execução de queries arbitrárias.
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
        """
        Inicializa a conexão com o banco PostgreSQL.
        """
        dbname = dbname or os.getenv("DBNAMEPOSTGRES")
        user = user or os.getenv("USER_POSTGRES")
        password = password or os.getenv("SENHAPOSTGRES")
        host = host or os.getenv("IPPOSTGRES")

        self.engine: Engine = create_engine(
            f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}",
            echo=echo,
            future=True
        )
        self.metadata = MetaData()
        self.conn: Optional[Connection] = None
        self._transaction_ctx = None  # guarda o context manager

    # ---------------- Context Manager ---------------- #
    def __enter__(self):
        self._transaction_ctx = self.engine.begin()
        self.conn = self._transaction_ctx.__enter__()  # pega a Connection real
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._transaction_ctx:
            self._transaction_ctx.__exit__(exc_type, exc_val, exc_tb)
        self.engine.dispose()

    # ---------------- Métodos de Tabela ---------------- #
    def get_table_columns(self, table_name: str) -> List[str]:
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
        if not data_list:
            print("Nenhum dado para inserir ou atualizar.")
            return

        table = Table(table_name, self.metadata, autoload_with=self.engine)
        columns = [c.name for c in table.columns if c.name.lower() != 'id']

        if self.conn is None:
            with self.engine.begin() as conn:
                self._execute_upsert(conn, table, columns, data_list, unique_fields, batch_size)
        else:
            self._execute_upsert(self.conn, table, columns, data_list, unique_fields, batch_size)

    def _execute_upsert(
        self,
        conn: Connection,
        table: Table,
        columns: List[str],
        data_list: List[Dict[str, Any]],
        unique_fields: List[str],
        batch_size: int
    ):
        for i in range(0, len(data_list), batch_size):
            batch = data_list[i:i + batch_size]
            cleaned_batch = [
                {k: (None if pd.isna(v) else v) for k, v in item.items() if k in columns}
                for item in batch
            ]
            stmt = insert(table).values(cleaned_batch)
            update_cols = {c: stmt.excluded[c] for c in columns if c not in unique_fields}
            stmt = stmt.on_conflict_do_update(index_elements=unique_fields, set_=update_cols)
            result = conn.execute(stmt)
            print(f"Lote de {len(batch)}: {result.rowcount} inseridos/atualizados")

    # ---------------- Delete ---------------- #
    def delete_table(self, table_name: str) -> None:
        table = Table(table_name, self.metadata, autoload_with=self.engine)
        if self.conn is None:
            with self.engine.begin() as conn:
                deleted = conn.execute(table.delete())
                print(f"{deleted.rowcount} registros deletados da tabela '{table_name}'")
        else:
            deleted = self.conn.execute(table.delete())
            print(f"{deleted.rowcount} registros deletados da tabela '{table_name}'")

    def delete_by_keys(self, table_name: str, keys: Dict[str, List[Any]]) -> None:
        table = Table(table_name, self.metadata, autoload_with=self.engine)
        conditions = []

        for col_name, values in keys.items():
            if col_name not in table.c:
                raise ValueError(f"Coluna '{col_name}' não existe na tabela '{table_name}'")
            if values:
                conditions.append(table.c[col_name].in_(values))

        if not conditions:
            print("Nenhuma condição válida para deletar.")
            return

        delete_stmt = table.delete().where(and_(*conditions))

        if self.conn is None:
            with self.engine.begin() as conn:
                result = conn.execute(delete_stmt)
                print(f"{result.rowcount} registros deletados da tabela '{table_name}'")
        else:
            result = self.conn.execute(delete_stmt)
            print(f"{result.rowcount} registros deletados da tabela '{table_name}'")

    # ---------------- Queries Arbitrárias ---------------- #
    def execute_query(self, query: Union[str, text], fetch: bool = True):
        if self.conn is None:
            with self.engine.begin() as conn:
                result = conn.execute(text(query) if isinstance(query, str) else query)
                return result.fetchall() if fetch else None
        else:
            result = self.conn.execute(text(query) if isinstance(query, str) else query)
            return result.fetchall() if fetch else None

    # ---------------- Fechamento ---------------- #
    def close(self):
        self.engine.dispose()


# ---------------- Forma de Uso ---------------- #

# from database_manager import DatabaseManager

# dados = [
#     {"nome": "Kelvyn", "idade": 26, "email": "kelvyn@example.com"},
#     {"nome": "Maria", "idade": 25, "email": "maria@example.com"},
# ]

# # Uso com context manager (mais seguro)

# with DatabaseManager() as db:
#     # Inserir ou atualizar registros
#     db.insert_or_update_batch("usuarios", dados, unique_fields=["email"])

#     # Deletar todos os registros
#     # db.delete_table("usuarios")

#     # Deletar registros específicos por chave
#     keys = {"email": ["kelvyn@example.com"], "idade": [30]}
#     db.delete_by_keys("usuarios", keys)

#     # Executar query arbitrária
#     resultado = db.execute_query("SELECT * FROM usuarios")
#     import pandas as pd
#     print(pd.DataFrame(resultado))
