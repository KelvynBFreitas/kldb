import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

class kloracle:
    def __init__(self, env_file=".env", folder="consultas", port=1521):
        """
        Inicializa a conexão com Oracle usando variáveis do .env
        """
        load_dotenv(env_file)

        user = os.getenv("USERORACLE")
        password = os.getenv("SENHAORACLE")
        host = os.getenv("IPORACLE")
        service_name = os.getenv("SCHEMA")

        if not all([user, password, host, service_name]):
            raise ValueError("⚠️ Variáveis de ambiente do Oracle não foram encontradas no .env")

        dsn = f"oracle+oracledb://{user}:{password}@{host}:{port}/?service_name={service_name}"
        self.engine = create_engine(dsn, pool_pre_ping=True)
        self.folder = folder

    def loadOracle(self, sql_file, params=None):
        """
        Executa consulta SQL a partir de um arquivo .sql
        :param sql_file: nome do arquivo SQL (sem extensão)
        :param params: dicionário de parâmetros {chave: valor} para bind
        :return: DataFrame pandas
        """
        file_path = os.path.join(self.folder, f"{sql_file}.sql")
        with open(file_path, 'r', encoding="utf-8") as file:
            query = file.read()

        with self.engine.connect() as conn:
            df = pd.read_sql(text(query), conn, params=params or {})
        return df
