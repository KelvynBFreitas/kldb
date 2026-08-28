"""
Modulo de leitura de dados Oracle e PostgreSQL.

Este modulo fornece classes para conectar a bancos Oracle e PostgreSQL,
executar consultas SQL parametrizadas e retornar resultados como DataFrames
do pandas. As credenciais sao lidas automaticamente de um arquivo ``.env``.

Classes:
    kloracle: Conexao e leitura de dados Oracle.
    klpostgres: Conexao e leitura de dados PostgreSQL.

Exemplo rapido::

    from kldb import kloracle, klpostgres

    # Oracle
    with kloracle() as db:
        df = db.load_oracle("minha_consulta", params={"ano": 2024})

    # PostgreSQL
    with klpostgres() as db:
        df = db.load_postgres("minha_consulta")
"""

import logging
import os
from typing import Any, Dict, Optional
from urllib.parse import quote_plus

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class kloracle:
    """Classe para conexao e leitura de dados Oracle.

    Utiliza SQLAlchemy + oracledb para gerenciar a conexao e o pool de
    conexoes. As credenciais sao lidas de um arquivo ``.env`` (ou variaveis
    de ambiente ja configuradas).

    Variaveis de ambiente esperadas:

    ===============  ==========================
    Variavel         Descricao
    ===============  ==========================
    USERORACLE       Usuario do banco Oracle
    SENHAORACLE      Senha do usuario
    IPORACLE         Host ou IP do banco
    SCHEMA           Service name do Oracle
    ===============  ==========================

    Args:
        env_file: Caminho para o arquivo ``.env``. Padrao: ``".env"``.
        folder: Pasta onde estao os arquivos ``.sql``. Padrao: ``"consultas"``.
        port: Porta de conexao do Oracle. Padrao: ``1521``.

    Raises:
        ValueError: Se alguma variavel de ambiente obrigatoria nao for encontrada.

    Exemplo::

        from kldb import kloracle

        # Usando context manager (recomendado)
        with kloracle(env_file=".env", folder="sql") as db:
            df = db.load_oracle("vendas_2024")
            print(df.head())

        # Forma classica
        db = kloracle()
        df = db.load_oracle("relatorio")
        db.close()
    """

    def __init__(self, env_file: str = ".env", folder: str = "consultas", port: int = 1521):
        load_dotenv(env_file)

        user = os.getenv("USERORACLE")
        password = os.getenv("SENHAORACLE")
        host = os.getenv("IPORACLE")
        service_name = os.getenv("SCHEMA")

        if not all([user, password, host, service_name]):
            missing = [
                v
                for v, val in [
                    ("USERORACLE", user),
                    ("SENHAORACLE", password),
                    ("IPORACLE", host),
                    ("SCHEMA", service_name),
                ]
                if not val
            ]
            raise ValueError(
                f"Variaveis de ambiente do Oracle nao encontradas no .env: {', '.join(missing)}"
            )

        password_esc = quote_plus(password)

        self.engine: Engine = create_engine(
            f"oracle+oracledb://{user}:{password_esc}@{host}:{port}/?service_name={service_name}",
            pool_pre_ping=True,
        )
        self.folder = folder
        self._sql_cache: Dict[str, str] = {}

    def _read_sql(self, sql_file: str) -> str:
        """Le e cacheia o conteudo de um arquivo ``.sql``.

        Args:
            sql_file: Nome do arquivo SQL (sem extensao ``.sql``).

        Returns:
            Conteudo do arquivo SQL como string.

        Raises:
            FileNotFoundError: Se o arquivo nao for encontrado na pasta configurada.
        """
        if sql_file in self._sql_cache:
            return self._sql_cache[sql_file]

        file_path = os.path.join(self.folder, f"{sql_file}.sql")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                query = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Arquivo SQL nao encontrado: '{file_path}'. "
                f"Verifique se o arquivo existe na pasta '{self.folder}'."
            )

        self._sql_cache[sql_file] = query
        return query

    def loadOracle(self, sql_file: str, params: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
        """Executa uma consulta SQL e retorna um DataFrame.

        Le o conteudo de um arquivo ``.sql``, executa no banco Oracle e
        retorna o resultado como ``pandas.DataFrame``.

        Args:
            sql_file: Nome do arquivo SQL (sem extensao ``.sql``).
                O arquivo deve estar na pasta definida no construtor.
            params: Dicionario de parametros para bind na query.
                Use chaves ``:nome_parametro`` no SQL.
                Exemplo: ``{"ano": 2024, "regiao": "SU"}``

        Returns:
            ``pandas.DataFrame`` com o resultado da consulta.

        Raises:
            FileNotFoundError: Se o arquivo ``.sql`` nao for encontrado.
            sqlalchemy.exc.SQLAlchemyError: Se houver erro na execucao da query.

        Exemplo::

            # SQL: SELECT * FROM vendas WHERE ano = :ano AND regiao = :regiao
            df = db.load_oracle("vendas", params={"ano": 2024, "regiao": "SU"})
        """
        query = self._read_sql(sql_file)
        with self.engine.connect() as conn:
            df = pd.read_sql(text(query), conn, params=params or {})
        logger.info("loadOracle: '%s' retornou %d linhas.", sql_file, len(df))
        return df

    # Alias snake_case (backward-compatible)
    load_oracle = loadOracle

    def close(self) -> None:
        """Fecha a conexao e libera recursos do pool."""
        self.engine.dispose()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class klpostgres:
    """Classe para conexao e leitura de dados PostgreSQL.

    Utiliza SQLAlchemy + psycopg2 para gerenciar a conexao e o pool de
    conexoes.

    As credenciais podem ser informadas diretamente no construtor ou,
    caso nao sejam informadas, serao lidas de um arquivo ``.env`` /
    variaveis de ambiente.

    Variaveis de ambiente esperadas:

    ==================  ==========================
    Variavel            Descricao
    ==================  ==========================
    USER_POSTGRES       Usuario do banco PostgreSQL
    SENHAPOSTGRES       Senha do usuario
    IPPOSTGRES          Host ou IP do banco
    DBNAMEPOSTGRES      Nome do banco de dados
    ==================  ==========================

    Args:
        env_file: Caminho para o arquivo ``.env``. Padrao: ``".env"``.
        folder: Pasta onde estao os arquivos ``.sql``. Padrao: ``"consultas"``.
        port: Porta de conexao do PostgreSQL. Padrao: ``5432``.
        user: Usuario do PostgreSQL. Se nao informado, busca no ambiente.
        password: Senha do PostgreSQL. Se nao informada, busca no ambiente.
        host: Host/IP do PostgreSQL. Se nao informado, busca no ambiente.
        database: Nome do banco. Se nao informado, busca no ambiente.

    Raises:
        ValueError: Se alguma credencial obrigatoria nao for encontrada.

    Exemplo usando .env::

        from kldb import klpostgres

        db = klpostgres()

    Exemplo passando as credenciais diretamente::

        db = klpostgres(
            user="postgres",
            password="123456",
            host="192.168.1.100",
            database="meubanco"
        )

    Exemplo usando context manager::

        with klpostgres() as db:
            df = db.load_postgres("usuarios_ativos")
    """

    def __init__(
        self,
        env_file: str = ".env",
        folder: str = "consultas",
        port: int = 5432,
        user: Optional[str] = None,
        password: Optional[str] = None,
        host: Optional[str] = None,
        database: Optional[str] = None,
    ):
        # Carrega o .env caso exista
        load_dotenv(env_file)

        # Prioridade:
        # 1. Valor passado diretamente
        # 2. Variavel de ambiente
        user = user or os.getenv("USER_POSTGRES")
        password = password or os.getenv("SENHAPOSTGRES")
        host = host or os.getenv("IPPOSTGRES")
        database = database or os.getenv("DBNAMEPOSTGRES")

        if not all([user, password, host, database]):
            missing = [
                v
                for v, val in [
                    ("USER_POSTGRES", user),
                    ("SENHAPOSTGRES", password),
                    ("IPPOSTGRES", host),
                    ("DBNAMEPOSTGRES", database),
                ]
                if not val
            ]

            raise ValueError(
                "Dados de conexao do PostgreSQL nao encontrados: "
                + ", ".join(missing)
            )

        # Escapa caracteres especiais da senha
        password_esc = quote_plus(password)

        self.engine: Engine = create_engine(
            f"postgresql+psycopg2://"
            f"{user}:{password_esc}@{host}:{port}/{database}",
            pool_pre_ping=True,
        )

        self.folder = folder
        self._sql_cache: Dict[str, str] = {}

    def _read_sql(self, sql_file: str) -> str:
        """Le e cacheia o conteudo de um arquivo SQL."""

        if sql_file in self._sql_cache:
            return self._sql_cache[sql_file]

        file_path = os.path.join(
            self.folder,
            f"{sql_file}.sql"
        )

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                query = f.read()

        except FileNotFoundError:
            raise FileNotFoundError(
                f"Arquivo SQL nao encontrado: '{file_path}'. "
                f"Verifique se o arquivo existe na pasta '{self.folder}'."
            )

        self._sql_cache[sql_file] = query

        return query

    def loadPostgres(
        self,
        sql_file: str,
        params: Optional[Dict[str, Any]] = None
    ) -> pd.DataFrame:
        """Executa uma consulta SQL e retorna um DataFrame."""

        query = self._read_sql(sql_file)

        with self.engine.connect() as conn:
            df = pd.read_sql(
                text(query),
                conn,
                params=params or {}
            )

        logger.info(
            "loadPostgres: '%s' retornou %d linhas.",
            sql_file,
            len(df)
        )

        return df

    # Alias snake_case
    load_postgres = loadPostgres

    def close(self) -> None:
        """Fecha a conexao e libera recursos do pool."""
        self.engine.dispose()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
