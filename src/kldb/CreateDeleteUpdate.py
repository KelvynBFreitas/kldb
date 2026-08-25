"""
Modulo de gerenciamento de banco PostgreSQL (CRUD em lote).

Este modulo fornece a classe :class:`DatabaseManager` para operacoes de
escrita e leitura em bancos PostgreSQL, com suporte a:

- **UPSERT** (insert ou update) em lote com controle de tamanho de batch.
- **DELETE** total ou condicional por chaves.
- **Queries arbitarias** com retorno como lista de tuplas ou ``DataFrame``.
- **Context manager** para gerenciamento seguro de transacoes.

Exemplo rapido::

    from kldb import DatabaseManager

    dados = [
        {"nome": "Ana", "email": "ana@example.com"},
        {"nome": "Joao", "email": "joao@example.com"},
    ]

    with DatabaseManager() as db:
        db.insert_or_update_batch("usuarios", dados, unique_fields=["email"])
        df = db.execute_query_to_df("SELECT * FROM usuarios")
"""

import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional, Union

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import MetaData, Table, and_, create_engine, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import URL, Connection, Engine

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Gerenciador de banco PostgreSQL com suporte a operacoes em lote.

    Combina a simplicidade do SQLAlchemy com operacoes vetorizadas via pandas
    para maximizar performance em cargas de dados.

    A classe pode ser usada de duas formas:

    1. **Context manager** (recomendado) -- garante commit/rollback automatico.
    2. **Instancia direta** -- cada operacao é commitada imediatamente.

    Variaveis de ambiente usadas (caso os parametros nao sejam informados):

    ==================  ==========================
    Variavel            Descricao
    ==================  ==========================
    DBNAMEPOSTGRES      Nome do banco de dados
    USER_POSTGRES       Usuario do banco
    SENHAPOSTGRES       Senha do usuario
    IPPOSTGRES          Host ou IP do banco
    ==================  ==========================

    Args:
        dbname: Nome do banco de dados.
        user: Usuario do banco.
        password: Senha do usuario.
        host: Host ou IP do banco.
        port: Porta de conexao. Padrao: ``5432``.
        echo: Se ``True``, loga todas as queries SQL no console. Padrao: ``False``.
        env_file: Caminho para arquivo ``.env``. Se informado, carrega as
            variaveis antes de resolver os parametros. Padrao: ``None``.

    Raises:
        ValueError: Se os parametros de conexao estiverem incompletos.

    Exemplo::

        # Context manager (recomendado para operacoes em lote)
        with DatabaseManager(env_file=".env") as db:
            db.insert_or_update_batch("usuarios", dados, unique_fields=["email"])
            df = db.execute_query_to_df("SELECT * FROM usuarios")
            print(df)

        # Instancia direta (para queries avulsas)
        db = DatabaseManager()
        resultado = db.execute_query("SELECT COUNT(*) FROM usuarios")
        db.close()
    """

    def __init__(
        self,
        dbname: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        host: Optional[str] = None,
        port: int = 5432,
        echo: bool = False,
        env_file: Optional[str] = None,
    ):
        if env_file is not None:
            load_dotenv(env_file)

        dbname = dbname or os.getenv("DBNAMEPOSTGRES")
        user = user or os.getenv("USER_POSTGRES")
        password = password or os.getenv("SENHAPOSTGRES")
        host = host or os.getenv("IPPOSTGRES")

        if not all([dbname, user, password, host]):
            missing = [
                v
                for v, val in [
                    ("DBNAMEPOSTGRES", dbname),
                    ("USER_POSTGRES", user),
                    ("SENHAPOSTGRES", password),
                    ("IPPOSTGRES", host),
                ]
                if not val
            ]
            raise ValueError(
                f"Parametros de conexao incompletos: {', '.join(missing)}. "
                "Passe-os diretamente ou defina as variaveis de ambiente."
            )

        url = URL.create(
            drivername="postgresql+psycopg",
            username=user,
            password=password,
            host=host,
            port=port,
            database=dbname,
        )

        self.engine: Engine = create_engine(url, echo=echo, future=True)
        self.metadata = MetaData()
        self._table_cache: Dict[str, Table] = {}
        self.conn: Optional[Connection] = None
        self._transaction_ctx = None

    # ------------------------------------------------------------------ #
    #  Context Managers                                                    #
    # ------------------------------------------------------------------ #

    def __enter__(self):
        """Abre uma transacao. Use ``with DatabaseManager() as db:``."""
        self._transaction_ctx = self.engine.begin()
        self.conn = self._transaction_ctx.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Fecha a transacao e o engine. Rollback automatico se houver excecao."""
        if self._transaction_ctx:
            self._transaction_ctx.__exit__(exc_type, exc_val, exc_tb)
        self.engine.dispose()

    @contextmanager
    def _get_connection(self) -> Generator[Connection, None, None]:
        """Garante uma conexao ativa, reaproveitando a transacao se existir."""
        if self.conn is not None:
            yield self.conn
        else:
            with self.engine.begin() as conn:
                yield conn

    # ------------------------------------------------------------------ #
    #  Metodos de Tabela                                                   #
    # ------------------------------------------------------------------ #

    def _get_table(self, table_name: str) -> Table:
        """Retorna a ``Table`` do SQLAlchemy, usando cache."""
        if table_name not in self._table_cache:
            self._table_cache[table_name] = Table(
                table_name, self.metadata, autoload_with=self.engine
            )
        return self._table_cache[table_name]

    def get_table_columns(self, table_name: str) -> List[str]:
        """Retorna a lista de colunas de uma tabela, ignorando a PK ``id``.

        Util para descobrir quais colunas estao disponiveis antes de montar
        os dados para ``insert_or_update_batch``.

        Args:
            table_name: Nome da tabela no banco de dados.

        Returns:
            Lista com os nomes das colunas (excluindo ``id``).

        Exemplo::

            colunas = db.get_table_columns("usuarios")
            print(colunas)  # ['nome', 'email', 'criado_em']
        """
        table = self._get_table(table_name)
        return [col.name for col in table.columns if col.name.lower() != "id"]

    # ------------------------------------------------------------------ #
    #  Insert / Update (Upsert)                                            #
    # ------------------------------------------------------------------ #

    def insert_or_update_batch(
        self,
        table_name: str,
        data_list: List[Dict[str, Any]],
        unique_fields: List[str],
        batch_size: int = 5000,
    ) -> None:
        """Insere ou atualiza registros em lote (UPSERT).

        Para cada registro, verifica se ja existe um registro com os mesmos
        valores nas ``unique_fields``. Se existir, atualiza os demais campos.
        Se nao existir, insere um novo registro.

        Os dados sao processados em lotes de ``batch_size`` registros para
        maximizar performance com tabelas grandes.

        .. note::
            A coluna ``id`` (PK) e automaticamente ignorada nos dados de entrada.

        Args:
            table_name: Nome da tabela de destino.
            data_list: Lista de dicionarios, onde cada dict e um registro.
                As chaves devem ser nomes de colunas da tabela.
                Ex: ``[{"nome": "Ana", "email": "ana@x.com"}, ...]``
            unique_fields: Lista de colunas que identificam unicamente um registro.
                Usadas na clausula ``ON CONFLICT``.
                Ex: ``["email"]`` ou ``["cpf", "orgao"]``.
            batch_size: Tamanho de cada lote. Padrao: ``5000``.

        Raises:
            sqlalchemy.exc.SQLAlchemyError: Se houver erro na execucao.

        Exemplo::

            dados = [
                {"nome": "Ana", "email": "ana@example.com", "ativo": True},
                {"nome": "Joao", "email": "joao@example.com", "ativo": False},
            ]

            with DatabaseManager() as db:
                db.insert_or_update_batch(
                    "usuarios",
                    dados,
                    unique_fields=["email"],
                    batch_size=1000,
                )
        """
        if not data_list:
            logger.info("Nenhum dado fornecido para insert/update.")
            return

        table = self._get_table(table_name)
        valid_cols = [c.name for c in table.columns if c.name.lower() != "id"]

        df = pd.DataFrame(data_list)
        cols_to_keep = [col for col in valid_cols if col in df.columns]

        # Converte NaN/NaT do pandas para None (NULL no SQL)
        df = df[cols_to_keep].where(pd.notna(df), None)
        cleaned_data = df.to_dict(orient="records")

        total_rows_affected = 0
        total_batches = 0

        with self._get_connection() as conn:
            for i in range(0, len(cleaned_data), batch_size):
                batch = cleaned_data[i : i + batch_size]
                stmt = insert(table).values(batch)

                update_cols = {
                    c: stmt.excluded[c] for c in cols_to_keep if c not in unique_fields
                }

                if update_cols:
                    stmt = stmt.on_conflict_do_update(
                        index_elements=unique_fields, set_=update_cols
                    )
                else:
                    stmt = stmt.on_conflict_do_nothing(index_elements=unique_fields)

                result = conn.execute(stmt)
                total_rows_affected += result.rowcount
                total_batches += 1

            logger.info(
                "Upsert concluido na tabela '%s': "
                "%d lote(s) processado(s), %d linhas afetadas.",
                table_name,
                total_batches,
                total_rows_affected,
            )

    # ------------------------------------------------------------------ #
    #  Delete                                                              #
    # ------------------------------------------------------------------ #

    def delete_table(self, table_name: str) -> None:
        """Deleta **todos** os registros de uma tabela.

        .. warning::
            Esta operacao e irreversivel. Use com extrema cautela.

        Args:
            table_name: Nome da tabela que tera todos os registros removidos.

        Exemplo::

            with DatabaseManager() as db:
                db.delete_table("logs_antigos")
        """
        table = self._get_table(table_name)

        with self._get_connection() as conn:
            deleted = conn.execute(table.delete())
            logger.info(
                "Delete: %d registros removidos da tabela '%s'.", deleted.rowcount, table_name
            )

    def delete_by_keys(self, table_name: str, keys: Dict[str, List[Any]]) -> None:
        """Deleta registros com base em valores especificos de uma ou mais colunas.

        Os valores dentro de cada lista sao combinados com ``OR``.
        As diferentes colunas sao combinadas com ``AND``.

        Args:
            table_name: Nome da tabela.
            keys: Dicionario onde a chave e o nome da coluna e o valor e uma
                lista de valores aceitaveis para aquela coluna.

                Ex: ``{"status": ["inativo", "suspenso"], "ano": [2020, 2021]}``
                Equivale a: ``WHERE status IN ('inativo','suspenso') AND ano IN (2020, 2021)``

        Raises:
            ValueError: Se alguma coluna nao existir na tabela.

        Exemplo::

            with DatabaseManager() as db:
                # Deleta usuarios inativos ou suspensos de 2020/2021
                db.delete_by_keys("usuarios", {
                    "status": ["inativo", "suspenso"],
                    "ano_cadastro": [2020, 2021],
                })
        """
        table = self._get_table(table_name)
        conditions = []

        for col_name, values in keys.items():
            if col_name not in table.c:
                raise ValueError(f"A coluna '{col_name}' nao existe na tabela '{table_name}'.")
            if values:
                conditions.append(table.c[col_name].in_(values))

        if not conditions:
            logger.warning("Delete ignorado: Nenhuma condicao valida fornecida.")
            return

        delete_stmt = table.delete().where(and_(*conditions))

        with self._get_connection() as conn:
            result = conn.execute(delete_stmt)
            logger.info(
                "Delete: %d registros removidos da tabela '%s' usando chaves condicionais.",
                result.rowcount,
                table_name,
            )

    # ------------------------------------------------------------------ #
    #  Queries Arbitrarias                                                 #
    # ------------------------------------------------------------------ #

    def execute_query(self, query: Union[str, text], fetch: bool = True) -> Optional[List[Any]]:
        """Executa uma query SQL arbitraria e retorna os resultados.

        Util para queries de selecao, DDL ou DML que precisam de retorno
        customizado (ex: ``RETURNING``, ``SELECT COUNT(*)``, etc.).

        Args:
            query: Query SQL como string ou ``sqlalchemy.text()``.
            fetch: Se ``True``, retorna os resultados com ``fetchall()``.
                Se ``False``, executa a query sem retornar dados (util para
                DDL/DML). Padrao: ``True``.

        Returns:
            Lista de tuplas com os resultados, ou ``None`` se ``fetch=False``.

        Exemplo::

            # Query simples
            resultado = db.execute_query("SELECT COUNT(*) FROM usuarios")
            print(resultado)  # [(42,)]

            # Execute sem retorno
            db.execute_query("VACUUM ANALYZE usuarios", fetch=False)
        """
        stmt = text(query) if isinstance(query, str) else query

        with self._get_connection() as conn:
            result = conn.execute(stmt)
            return result.fetchall() if fetch else None

    def execute_query_to_df(
        self,
        query: Union[str, text],
        params: Optional[Dict[str, Any]] = None,
        chunksize: Optional[int] = None,
    ) -> pd.DataFrame:
        """Executa uma query e retorna diretamente um ``DataFrame``.

        Util quando o resultado sera processado com pandas (analises,
        exportacoes, transformacoes). Suporta leitura em blocos para
        tabelas muito grandes.

        Args:
            query: Query SQL como string ou ``sqlalchemy.text()``.
            params: Dicionario de parametros para bind na query.
                Use chaves ``:nome_parametro`` no SQL.
                Ex: ``{"ano": 2024, "status": "ativo"}``
            chunksize: Se informado, le os dados em blocos de N linhas
                e concatena ao final. Util para tabelas com milhoes de
                registros. Padrao: ``None`` (le tudo de uma vez).

        Returns:
            ``pandas.DataFrame`` com o resultado da consulta.

        Raises:
            sqlalchemy.exc.SQLAlchemyError: Se houver erro na execucao da query.

        Exemplo::

            # Query simples
            df = db.execute_query_to_df(
                "SELECT * FROM vendas WHERE ano = :ano",
                params={"ano": 2024},
            )

            # Query grande com leitura em blocos
            df = db.execute_query_to_df(
                "SELECT * FROM logs",
                chunksize=100_000,
            )
        """
        stmt = text(query) if isinstance(query, str) else query

        with self._get_connection() as conn:
            if chunksize is not None:
                chunks = pd.read_sql(stmt, conn, params=params or {}, chunksize=chunksize)
                return pd.concat(chunks, ignore_index=True)
            return pd.read_sql(stmt, conn, params=params or {})

    # ------------------------------------------------------------------ #
    #  Fechamento                                                          #
    # ------------------------------------------------------------------ #

    def close(self) -> None:
        """Fecha a conexao e libera recursos do pool.

        Chame este metodo quando nao estiver usando context manager.
        """
        self.engine.dispose()
