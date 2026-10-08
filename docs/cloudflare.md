# Cloudflare Workers Free (SCRUM-430)

## Grafana Cloud

A exportação nativa de OpenTelemetry usa dois destinos da conta Cloudflare:
`astro-grafana-traces` (Tempo) e `astro-grafana-logs` (Loki). O endpoint base é
`https://otlp-gateway-prod-sa-east-1.grafana.net/otlp`, com `/v1/traces` e
`/v1/logs`, respectivamente. O header Authorization é protegido na configuração
dos destinos; não faz parte do Git nem do bundle da API.

`wrangler.jsonc` habilita a exportação com amostragem de 100%, `persist: false`
e remoção dos parâmetros da URL nos eventos do runtime.
A aplicação registra JSON com serviço, request_id, método, rota normalizada,
status HTTP e duração em milissegundos. Não registra filtros, headers de
autenticação ou conteúdo dos datasets. Logs de invocação são desativados para
evitar registrar URLs com parâmetros. Traces são gerados pelo runtime Cloudflare.

No Grafana Explore, selecionar Loki e buscar o serviço `astro-medallion-api`;
usar Tempo para pesquisar os traces do Worker. O nome de serviço efetivo dos
traces depende dos atributos emitidos pelo Cloudflare. A exportação nativa não
inclui métricas OTLP; volume, erros e latência podem ser consultados a partir dos
logs. Ajustar a amostragem conforme as quotas gratuitas de ingestão do Grafana.
Verificar em Observability > Destinations o status da entrega após o deploy.

Referência: https://developers.cloudflare.com/observability/export/opentelemetry/grafana-cloud/.

A API Python/FastAPI é publicada como Python Worker, sem Containers e sem
contratar Workers Paid. Bronze, Silver e Gold continuam em `app/`.
`worker.py` adapta FastAPI para o ASGI do Cloudflare e usa Asyncpg no binding
Hyperdrive. O driver Psycopg permanece disponível na execução local/Uvicorn.

## Publicação

Instalar `uv`, Node e as ferramentas oficiais `workers-py`/`workers-runtime-sdk`.
Instalar as dependências de implantação com `npm ci`. Preparar os pacotes
Python com `pywrangler sync` e publicar com `node node_modules/wrangler/bin/wrangler.js deploy`.
`prepare_worker.py` copia apenas os módulos da API para `.wrangler/python-deploy`
antes de empacotar; ambientes locais, `.env` e temporários não entram no Worker.
`pylock.toml` fixa as dependências compiladas para Pyodide; `requirements.lock`
fixa as dependências do ambiente Python local/container.

## Conexão e autenticação

O binding `HYPERDRIVE` reutiliza a conexão `astro-email-db` da conta autorizada,
para o mesmo banco `astro_2`, com cache desativado e TLS `verify-full` usando
`astro-aiven-ca`. A origem Aiven é validada pelo Hyperdrive; o socket entre
Worker e binding é interno ao Cloudflare. As transações são READ ONLY.
O token exclusivo é o secret `API_TOKEN` do Worker, preservado do `.env`.
Não publicar o valor do token ou credenciais do banco no Git.

`/docs` e `/openapi.json` são públicos; `/health` e dados exigem Bearer token.
O Databricks chama a URL HTTPS publicada e segue a paginação.

## Limites gratuitos

Workers Free limita requisições e CPU por requisição. Hyperdrive Free oferece
até 100.000 consultas por dia, compartilhadas na conta; comandos da transação
também contam. Ao atingir limites, chamadas podem falhar até a renovação da
quota. Manter paginação e ajustar a frequência de ingestão no Databricks.

Referências: https://developers.cloudflare.com/workers/languages/python/packages/fastapi/
e https://developers.cloudflare.com/hyperdrive/platform/pricing/.

## Publicação atual

URL: https://astro-medallion-api.app-4str0.workers.dev

Swagger: https://astro-medallion-api.app-4str0.workers.dev/docs

Publicada em 07/10/2026 no plano Free. Swagger e OpenAPI retornam HTTP 200;
chamadas sem token retornam 401. Health, catálogo e chamadas das três camadas
foram conferidos com o token, sem imprimir dados pessoais.


## API 0.2: snapshots e SCD

Aplique a migração PostgreSQL e as permissões antes do deploy.
Desabilite query caching no recurso Hyperdrive usado por este Worker para que
as leituras de controle e SCD reflitam imediatamente as escritas.
O scheduled handler tem os argumentos self/controller/env/ctx e usa os crons
03h/04h/05h UTC (00h/01h/02h America/Sao_Paulo) para captura diária e retries.
RATE_LIMIT_PER_MINUTE, SNAPSHOT_TTL_SECONDS, MAX_SNAPSHOT_ROWS e RETRY_AFTER_SECONDS
são variáveis não secretas. API_TOKEN continua secret, sem logging de valor.
As fontes públicas são consultadas por leitura; os writes se limitam ao schema
astro_api e à sua sequência. /health/db testa a conexão real.
