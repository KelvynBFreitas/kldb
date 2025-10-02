# KLDB

**KLDB** é um pacote Python para facilitar conexões e operações em bancos **Oracle** e **Postgres**, utilizando **SQLAlchemy** e **Pandas**. Ele oferece:

- Conexão simplificada com Oracle e Postgres  
- Execução de queries com parâmetros  
- Inserção e atualização em lote (UPSERT)  
- Deleção de registros (total ou condicional por chave)  
- Integração com variáveis de ambiente via `.env`  

---
## Metodo de Uso 
from kldb import kloracle, klpostgres

 Conexão com Oracle usando arquivo .env
db_oracle = kloracle(env_file=".env")

 Consulta sem parâmetros
df1 = db_oracle.loadOracle("consultas")

 Consulta com parâmetros (:ano dentro do SQL)
df2 = db_oracle.loadOracle("consultas", params={"ano": 2024})

 Conexão com Postgres usando arquivo .env
db_postgres = klpostgres(env_file=".env")
df3 = db_postgres.loadPostgres("consultas_postgres")



from kldb import DatabaseManager
import pandas as pd

  Dados de exemplo
dados = [
    {"nome": "Kelvyn", "idade": 30, "email": "kelvyn@example.com"},
    {"nome": "Maria", "idade": 25, "email": "maria@example.com"},
]

  Uso com context manager (recomendado)
with DatabaseManager() as db:

    # Inserir ou atualizar registros em lote (UPSERT)
    db.insert_or_update_batch("usuarios", dados, unique_fields=["email"])

    # Deletar todos os registros de uma tabela
    # db.delete_table("usuarios")

    # Deletar registros específicos por chave(s)
    keys = {"email": ["kelvyn@example.com"], "idade": [30]}
    db.delete_by_keys("usuarios", keys)

    # Executar query arbitrária
    resultado = db.execute_query("SELECT * FROM usuarios")
    print(pd.DataFrame(resultado))




## Instalação

Via PyPI (quando publicado):

```bash
pip install kldb
pip install "kldb[postgres,oracle,dev]"
