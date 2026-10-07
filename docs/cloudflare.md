# Cloudflare Workers Free (SCRUM-430)

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
