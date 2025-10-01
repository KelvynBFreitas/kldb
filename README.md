# KLoracle

Um pacote Python para facilitar conexões ao Oracle usando SQLAlchemy + Pandas.

## Instalação

Via PyPI (quando publicado):
```bash
pip install KLoracle

## Uso 

from KLoracle import kloracle

db = kloracle(env_file=".env")

# Consulta sem parâmetros
df1 = db.loadOracle("consultas")

# Consulta com parâmetros (:ano dentro do SQL)
df2 = db.loadOracle("consultas", params={"ano": 2024})
