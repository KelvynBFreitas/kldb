# KLDB

**KLDB** e um pacote Python que simplifica a **conexao e operacoes de dados** em bancos **Oracle** e **Postgres**, aproveitando o poder do **SQLAlchemy** e do **Pandas**.

---

## Funcionalidades

- Conexao simplificada com Oracle (via oracledb) e PostgreSQL (via psycopg2).
- Execucao de queries SQL parametrizadas com retorno como DataFrame.
- Operacoes em lote de **UPSERT** (insercao ou atualizacao) com controle de batch.
- Delecao de registros (total ou condicional por chaves).
- Execucao de queries arbitarias com retorno como lista ou DataFrame.
- Integracao nativa com variaveis de ambiente via arquivo `.env`.
- Suporte a context manager (`with`) para gerenciamento seguro de conexoes.
- Cache automatico de queries SQL e metadata de tabelas.

---

## Instalacao

```bash
# Instalacao base (Oracle + Postgres inclusos nas dependencias de opcao)
pip install git+https://github.com/KelvynBFreitas/kldb

# Com suporte a Oracle
pip install "kldb[oracle]"

# Com suporte a PostgreSQL
pip install "kldb[postgres]"

# Tudo incluido
pip install "kldb[all]"

# Com ferramentas de desenvolvimento (black, ruff, pytest)
pip install "kldb[all,dev]"
```

---

## Variaveis de Ambiente

Crie um arquivo `.env` na raiz do seu projeto:

```env
# Oracle
USERORACLE=seu_usuario_oracle
SENHAORACLE=sua_senha_oracle
IPORACLE=192.168.1.100
SCHEMA=meuservice

# PostgreSQL
USER_POSTGRES=seu_usuario_postgres
SENHAPOSTGRES=sua_senha_postgres
IPPOSTGRES=192.168.1.200
DBNAMEPOSTGRES=meu_banco
```

> O arquivo `.env` **nunca** deve ser versionado. Ja esta incluido no `.gitignore`.

---

## API Completa

### 1. `kloracle` -- Leitura de dados Oracle

```python
from kldb import kloracle

# Inicializando
db = kloracle(env_file=".env", folder="consultas", port=1521)

# ou com context manager (recomendado)
with kloracle(env_file=".env", folder="consultas") as db:
    ...
```

**Parametros do construtor:**

| Parametro | Tipo | Padrao | Descricao |
|-----------|------|--------|-----------|
| `env_file` | `str` | `".env"` | Caminho para o arquivo `.env` |
| `folder` | `str` | `"consultas"` | Pasta com os arquivos `.sql` |
| `port` | `int` | `1521` | Porta de conexao do Oracle |

**Metodos:**

#### `load_oracle(sql_file, params=None)`

Executa uma consulta SQL e retorna um DataFrame.

```python
# Consulta sem parametros
df = db.load_oracle("vendas_mensais")

# Consulta com parametros
# SQL: SELECT * FROM vendas WHERE ano = :ano AND regiao = :regiao
df = db.load_oracle("vendas_filtradas", params={"ano": 2024, "regiao": "SU"})

# O nome original loadOracle tambem funciona (backward-compatible)
df = db.loadOracle("vendas_mensais")
```

**Args:**

| Parametro | Tipo | Descricao |
|-----------|------|-----------|
| `sql_file` | `str` | Nome do arquivo `.sql` (sem extensao) |
| `params` | `dict` | Parametros para bind na query. Use `:nome` no SQL |

**Retorno:** `pandas.DataFrame`

**Erros:**
- `FileNotFoundError` -- Se o arquivo `.sql` nao for encontrado.
- `ValueError` -- Se as variaveis de ambiente estiverem faltando.

#### `close()`

Fecha a conexao e libera recursos.

```python
db.close()
```

---

### 2. `klpostgres` -- Leitura de dados PostgreSQL

```python
from kldb import klpostgres

# Inicializando
db = klpostgres(env_file=".env", folder="consultas", port=5432)

# ou com context manager
with klpostgres(env_file=".env", folder="consultas") as db:
    ...
```

**Parametros do construtor:**

| Parametro | Tipo | Padrao | Descricao |
|-----------|------|--------|-----------|
| `env_file` | `str` | `".env"` | Caminho para o arquivo `.env` |
| `folder` | `str` | `"consultas"` | Pasta com os arquivos `.sql` |
| `port` | `int` | `5432` | Porta de conexao do PostgreSQL |

**Metodos:**

#### `load_postgres(sql_file, params=None)`

Executa uma consulta SQL e retorna um DataFrame.

```python
# Consulta sem parametros
df = db.load_postgres("usuarios_ativos")

# Consulta com parametros
df = db.load_postgres("usuarios_por_status", params={"status": "ativo"})

# O nome original loadPostgres tambem funciona
df = db.loadPostgres("usuarios_ativos")
```

**Args:**

| Parametro | Tipo | Descricao |
|-----------|------|-----------|
| `sql_file` | `str` | Nome do arquivo `.sql` (sem extensao) |
| `params` | `dict` | Parametros para bind na query |

**Retorno:** `pandas.DataFrame`

#### `close()`

Fecha a conexao e libera recursos.

---

### 3. `DatabaseManager` -- CRUD em lote PostgreSQL

```python
from kldb import DatabaseManager

# Context manager (recomendado)
with DatabaseManager(env_file=".env") as db:
    ...

# Instancia direta
db = DatabaseManager()
db.close()
```

**Parametros do construtor:**

| Parametro | Tipo | Padrao | Descricao |
|-----------|------|--------|-----------|
| `dbname` | `str` | `None` | Nome do banco (ou env `DBNAMEPOSTGRES`) |
| `user` | `str` | `None` | Usuario (ou env `USER_POSTGRES`) |
| `password` | `str` | `None` | Senha (ou env `SENHAPOSTGRES`) |
| `host` | `str` | `None` | Host (ou env `IPPOSTGRES`) |
| `port` | `int` | `5432` | Porta de conexao |
| `echo` | `bool` | `False` | Logar queries SQL no console |
| `env_file` | `str` | `None` | Arquivo `.env` para carregar antes |

> Se os parametros nao forem informados, sao lidos das variaveis de ambiente.

#### `get_table_columns(table_name)`

Retorna a lista de colunas de uma tabela (ignorando `id`).

```python
with DatabaseManager() as db:
    colunas = db.get_table_columns("usuarios")
    print(colunas)  # ['nome', 'email', 'criado_em']
```

**Retorno:** `List[str]`

#### `insert_or_update_batch(table_name, data_list, unique_fields, batch_size=5000)`

Insere ou atualiza registros em lote (UPSERT).

```python
dados = [
    {"nome": "Ana", "email": "ana@example.com", "ativo": True},
    {"nome": "Joao", "email": "joao@example.com", "ativo": False},
]

with DatabaseManager() as db:
    # Insere ou atualiza pelo email
    db.insert_or_update_batch(
        "usuarios",
        dados,
        unique_fields=["email"],
        batch_size=1000,
    )
```

**Args:**

| Parametro | Tipo | Descricao |
|-----------|------|-----------|
| `table_name` | `str` | Nome da tabela de destino |
| `data_list` | `List[Dict]` | Lista de dicts com os dados |
| `unique_fields` | `List[str]` | Colunas para detectar duplicidade |
| `batch_size` | `int` | Tamanho do lote (default: 5000) |

**Comportamento:**
- Se o registro ja existe (conforme `unique_fields`), atualiza os demais campos.
- Se nao existe, insere um novo registro.
- A coluna `id` e automaticamente ignorada.

#### `delete_table(table_name)`

Deleta **todos** os registros de uma tabela.

```python
with DatabaseManager() as db:
    db.delete_table("logs_antigos")  # Cuidado: irreversivel!
```

#### `delete_by_keys(table_name, keys)`

Deleta registros com base em valores especificos.

```python
with DatabaseManager() as db:
    db.delete_by_keys("usuarios", {
        "status": ["inativo", "suspenso"],
        "ano_cadastro": [2020, 2021],
    })
    # Equivale a:
    # DELETE FROM usuarios
    # WHERE status IN ('inativo', 'suspenso')
    # AND ano_cadastro IN (2020, 2021)
```

**Args:**

| Parametro | Tipo | Descricao |
|-----------|------|-----------|
| `table_name` | `str` | Nome da tabela |
| `keys` | `Dict[str, List]` | Coluna -> lista de valores |

**Erros:**
- `ValueError` -- Se alguma coluna nao existir na tabela.

#### `execute_query(query, fetch=True)`

Executa uma query SQL arbitraria.

```python
with DatabaseManager() as db:
    # Com retorno
    resultado = db.execute_query("SELECT COUNT(*) FROM usuarios")
    print(resultado)  # [(42,)]

    # Sem retorno (DDL/DML)
    db.execute_query("VACUUM ANALYZE usuarios", fetch=False)
```

**Retorno:** `List[tuple]` ou `None` se `fetch=False`.

#### `execute_query_to_df(query, params=None, chunksize=None)`

Executa uma query e retorna diretamente um DataFrame.

```python
with DatabaseManager() as db:
    # Query parametrizada
    df = db.execute_query_to_df(
        "SELECT * FROM vendas WHERE ano = :ano",
        params={"ano": 2024},
    )

    # Query grande com leitura em blocos
    df = db.execute_query_to_df(
        "SELECT * FROM logs",
        chunksize=100_000,
    )

    print(df.head())
```

**Args:**

| Parametro | Tipo | Descricao |
|-----------|------|-----------|
| `query` | `str` ou `text` | SQL a executar |
| `params` | `dict` | Parametros para bind |
| `chunksize` | `int` | Tamanho do bloco para leitura em partes |

**Retorno:** `pandas.DataFrame`

#### `close()`

Fecha a conexao e libera recursos.

---

## Exemplo Completo

### Estrutura de pastas recomendada

```
meu_projeto/
  .env                  # Variaveis de ambiente (NAO versionar)
  consultas/
    vendas.sql          # Query de vendas
    usuarios.sql        # Query de usuarios
  main.py
```

### Exemplo `consultas/vendas.sql`

```sql
SELECT
    v.id,
    v.data_venda,
    v.valor,
    u.nome AS vendedor
FROM vendas v
JOIN usuarios u ON v.usuario_id = u.id
WHERE v.data_venda >= :data_inicio
  AND v.data_venda <= :data_fim
```

### Exemplo `main.py`

```python
from kldb import kloracle, klpostgres, DatabaseManager

# === Leitura Oracle ===
with kloracle(env_file=".env", folder="consultas") as oracle:
    df_vendas = oracle.load_oracle("vendas", params={
        "data_inicio": "2024-01-01",
        "data_fim": "2024-12-31",
    })
    print(f"Vendas encontradas: {len(df_vendas)}")

# === Leitura PostgreSQL ===
with klpostgres(env_file=".env", folder="consultas") as pg:
    df_usuarios = pg.load_postgres("usuarios")
    print(f"Usuarios: {len(df_usuarios)}")

# === Escrita PostgreSQL (UPSERT) ===
dados_para_gravar = df_vendas.to_dict(orient="records")

with DatabaseManager(env_file=".env") as db:
    # Descobre as colunas da tabela
    colunas = db.get_table_columns("vendas_gravadas")
    print(f"Colunas disponiveis: {colunas}")

    # Insere ou atualiza em lote
    db.insert_or_update_batch(
        "vendas_gravadas",
        dados_para_gravar,
        unique_fields=["id"],
        batch_size=5000,
    )

    # Consulta como DataFrame
    df_resumo = db.execute_query_to_df(
        "SELECT vendedor, COUNT(*) as total FROM vendas_gravadas GROUP BY vendedor"
    )
    print(df_resumo)

    # Deleta registros antigos
    db.delete_by_keys("vendas_gravadas", {"ano": [2020, 2021]})
```

---

## Tips e Boas Praticas

1. **Use context manager (`with`)** sempre que possivel. Ele garante que a conexao seja fechada automaticamente e que erros causem rollback.

2. **Separe seus SQLs em arquivos `.sql`**. Facilita manutencao, versionamento e reuso.

3. **Use parametros (`:param`)** em vez de concatenar strings. Previne SQL injection e melhora a legibilidade.

4. **Ajuste `batch_size`** conforme a memoria disponivel. Valores entre 1000 e 10000 sao um bom ponto de partida.

5. **Use `chunksize`** em `execute_query_to_df` para tabelas com milhoes de linhas, evitando estouro de memoria.

6. **Nao versione o `.env`**. Ja esta no `.gitignore` por padrao.

7. **Use `get_table_columns()`** para descobrir quais colunas estao disponiveis antes de montar os dados para insercao.

---

## Licenca

MIT -- veja o arquivo `pyproject.toml` para detalhes.
