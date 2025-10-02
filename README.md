# KLDB

**KLDB** é um pacote Python que simplifica a **conexão e operações de dados** em bancos **Oracle** e **Postgres**, aproveitando o poder do **SQLAlchemy** e do **Pandas**.

Ele oferece uma API limpa e eficiente para:

* Conexão simplificada com Oracle e Postgres.
* Execução de queries parametrizadas.
* Operações em lote de **UPSERT** (Inserção ou Atualização) de DataFrames ou listas de dicionários.
* Deleção de registros (total ou condicional por chaves).
* Integração nativa com variáveis de ambiente via arquivo `.env`.

---

## 💻 Instalação

Você pode instalar o `kldb` via PyPI (quando publicado):

```bash
pip install kldb


Para incluir suporte a bancos de dados específicos, use os extras:

# Para incluir suporte a Postgres
pip install "kldb[postgres]"

# Para incluir suporte a Oracle
pip install "kldb[oracle]"

# Para incluir todos os suportes e dependências de desenvolvimento
pip install "kldb[all,dev]"

🚀 Uso Básico
Conexões e Consultas Simples
Este exemplo mostra como usar as classes específicas para cada banco (kloracle e klpostgres) para carregar dados.
from kldb import kloracle, klpostgres

# Conexão com Oracle usando variáveis do arquivo .env
db_oracle = kloracle(env_file=".env")

# Consulta sem parâmetros
df1 = db_oracle.loadOracle("consultas_simples")

# Consulta com parâmetros (substitui :ano dentro do seu SQL)
df2 = db_oracle.loadOracle("consultas_parametrizada", params={"ano": 2024})

# Conexão com Postgres usando arquivo .env
db_postgres = klpostgres(env_file=".env")
df3 = db_postgres.loadPostgres("consultas_postgres")

Operações em Lote e Gerenciamento de Banco
Para operações transacionais e em lote (como UPSERT e DELETE), recomenda-se usar a classe DatabaseManager como um context manager (with...).

from kldb import DatabaseManager
import pandas as pd

# Dados de exemplo para UPSERT
dados = [
    {"nome": "Kelvyn", "idade": 30, "email": "kelvyn@example.com"},
    {"nome": "Maria", "idade": 25, "email": "maria@example.com"},
]

# Uso com context manager (RECOMENDADO)
with DatabaseManager() as db:
    # 1. Inserir ou atualizar registros em lote (UPSERT)
    # 'unique_fields' define quais colunas usar para verificar duplicidade
    db.insert_or_update_batch("usuarios", dados, unique_fields=["email"])

    # 2. Executar query arbitrária e obter resultados
    resultado = db.execute_query("SELECT * FROM usuarios WHERE idade > 20")
    print("Registros na tabela:")
    print(pd.DataFrame(resultado))

    # 3. Deletar registros específicos por chave(s)
    # Deleta registros onde email='kelvyn@example.com' E idade=30
    keys_to_delete = {"email": ["kelvyn@example.com"], "idade": [30]}
    db.delete_by_keys("usuarios", keys_to_delete)
    
    # 4. Deletar todos os registros de uma tabela (Use com cautela!)
    # db.delete_table("outra_tabela")