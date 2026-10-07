# Astro Medallion API

API **Python com FastAPI**, Uvicorn e Psycopg para extrair fontes PostgreSQL
e gerar estruturas virtuais para consumo no Databricks. Tarefa pai SCRUM-423;
subtarefas SCRUM-424 a SCRUM-430.

## Executar localmente

Requisitos: Python 3.12 ou superior.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
# Preencher .env a partir de .env.example, se ainda não existir.
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000 --no-access-log
```

Em Linux/macOS, usar `.venv/bin/python` nos mesmos comandos. `requirements.lock`
fixa as versões de runtime validadas; os extras dev incluem cliente HTTP e Ruff.

Neste checkout o `.env` já tem a conexão autorizada e o token exclusivo criado
anteriormente, que foi preservado. O arquivo é ignorado pelo Git. `API_TOKEN`
é a credencial compartilhada da API e não um token de administração Cloudflare.

Todas as rotas exigem `Authorization: Bearer <API_TOKEN>`, inclusive `/health`
e `/openapi.json`. OpenAPI é gerado pelo FastAPI; as interfaces Swagger/Redoc
públicas estão desativadas. `/v1/datasets` descreve os campos de cada dataset.

```sh
curl -H "Authorization: Bearer $API_TOKEN" http://localhost:8000/v1/datasets
curl -H "Authorization: Bearer $API_TOKEN" \
  'http://localhost:8000/v1/silver/resumo_funcionario_dia?from=2026-10-06&to=2026-10-06'
```

Os exemplos curl exigem a variável API_TOKEN no terminal; carregar `.env` no
servidor não a exporta para outros processos. No PowerShell, usar `$env:API_TOKEN`.

## Dados e processamento

- Bronze: projeção das dez fontes PostgreSQL selecionadas.
- Silver: calendário, posições e resumo de funcionários calculados sob demanda.
- Gold: fato de unidade calculado conforme a procedure publicada.

As consultas usam parâmetros e transações READ ONLY. As quatro estruturas
derivadas não usam suas tabelas físicas. O fato mantém a regra documentada de
contar eventos apenas de gestores ativos da unidade 1.

O fato virtual representa hoje; ID físico e timestamp de inserção são NULL.
O Databricks preserva os snapshots diários. Posições de datas passadas usam
o cadastro atual; transferências e desativações antigas não são reconstituídas.

## Verificações

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m ruff check app scripts tests databricks
.\.venv\Scripts\python.exe -m ruff format --check app scripts tests databricks
.\.venv\Scripts\python.exe -m scripts.inspect_schema
```

Os testes de API usam FastAPI TestClient e fontes simuladas. O teste SQL opcional
usa `TEST_DATABASE_URL`, cria um schema isolado e desfaz a transação. Use um
banco de teste. Sem essa variável, o teste é pulado. O SQL gerado também foi
validado em PostgreSQL em memória durante a migração de implementação.

`scripts.inspect_schema` consulta o schema real em modo somente leitura e
depende da conexão TLS. Para o Aiven, configure o CA em `DATABASE_SSL_CA`
ou em um arquivo apontado por `DATABASE_SSL_CA_FILE`.

## Cloudflare

O [Dockerfile](Dockerfile) executa **a API Python** em Cloudflare Containers.
`cloudflare/gateway.js` é somente o adaptador de infraestrutura que encaminha
requisições para o container. `package.json` e Wrangler são usados apenas na
implantação Cloudflare; a aplicação local não depende de Node.js.

O adaptador foi empacotado em modo dry-run. O container completo não foi
executado, pois o daemon Docker local está parado. A API não foi publicada.
Consulte [implantação e operação](docs/cloudflare.md).

## Documentação

- [Schema e relacionamentos](docs/schema.md) — SCRUM-424.
- [Regras do fato histórico](docs/fato-historico.md) — SCRUM-425.
- [Contrato da API](docs/api-contract.md) — SCRUM-426.
- Extração FastAPI/Psycopg em `app/main.py` e `app/database.py` — SCRUM-427.
- Geração virtual em `app/virtual.py` — SCRUM-428.
- [Integração Databricks](docs/databricks.md) — SCRUM-429.
- [Cloudflare e operação](docs/cloudflare.md) — SCRUM-430.

A inspeção do banco ativo depende do CA do Aiven; execução Spark/Lakeflow
e migração do histórico físico dependem do ambiente Databricks.
