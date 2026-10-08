# Astro Medallion API

API Python/FastAPI para extrair fontes PostgreSQL e fornecer estruturas
medalhão ao Databricks. Card: SCRUM-423. Versão: 0.2.0 / contrato JSON 2.0.

Swagger publicado: https://astro-medallion-api.app-4str0.workers.dev/docs

## Camadas

- Bronze: dez fontes com textos normalizados, deduplicação por chave e
  snapshots diários. Filtros de data referem-se à captura, não a mudanças da fonte.
- Silver: calendário, posição histórica via SCD Tipo 2 e resumo por unidade/dia
  com linhas zeradas.
- Gold: fato por unidade em snapshots imutáveis, disponível para datas capturadas;
  eventos de todas as unidades, IDs/horários persistidos e dimensão determinística.

A API acessa as fontes por leitura. Escreve somente nas estruturas de controle
do schema `astro_api`; não grava diretamente no Databricks. O consumidor em
`databricks/ingest_api.py` grava as 14 tabelas no schema silver sem prefixos,
com 13 cargas diárias e a fato semanal.

## Executar localmente

Requer Python >= 3.12. Crie um ambiente virtual, instale
`pip install -r requirements.lock` e `pip install -e ".[local,dev]"`.
Configure `.env` a partir de `.env.example` e execute
`python -m uvicorn app.main:app --port 8000 --no-access-log`.
Nunca versionar `.env`, certificados privados nem tokens.

Antes de publicar esta versão, aplique a migração com o dono do banco e
configure as permissões/cache conforme [instalação do histórico](docs/history-deployment.md).
Sem essa preparação os endpoints dependentes de controle retornarão 503.
Não há reconstrução de estados anteriores à implantação sem histórico existente.

## Endpoints e contrato

Autenticação: `Authorization: Bearer <API_TOKEN>`. `/docs` e `/openapi.json`
são públicos. `/health` verifica o processo; `/health/db` consulta PostgreSQL.
`/v1/datasets` publica nomes, tipos, chaves e início de captura.

Dados: `/v1/bronze/{dataset}`, `/v1/silver/{dataset}`,
`/v1/gold/fato_historico_geral_unidade?date=YYYY-MM-DD`.
Use a URL inteira de `pagination.next`; ela congela a extração pelo UUID snapshot.
Snapshots expirados exigem reinício. `limit` máximo 1000; intervalos até 366 dias.
O limite padrão é 120 requests/minuto por API_TOKEN e tem headers de controle.

Detalhes: [contrato da API](docs/api-contract.md),
[consumo Databricks](docs/databricks.md), [fontes](docs/schema.md),
[Gold](docs/fato-historico.md), [Cloudflare](docs/cloudflare.md).

## Testes

`python -m unittest discover -s tests -v`.
`npm ci` e `npm run test:sql` validam também SQL, migração e SCD em PostgreSQL
isolado sem tocar o banco de produção.
