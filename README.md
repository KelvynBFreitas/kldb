# KLDB

Um pacote Python para facilitar conexões ao Oracle e postgres usando SQLAlchemy + Pandas.

## Uso 


from kldb import kloracle,klpostgres

db = kloracle(env_file=".env")

# Consulta sem parâmetros
df1 = db.loadOracle("consultas")
# Consulta com parâmetros (:ano dentro do SQL)
df2 = db.loadOracle("consultas", params={"ano": 2024})



## Instalação

Via PyPI (quando publicado):
```bash
pip install kldb
pip install kldb['postgres','oracle','dev']

