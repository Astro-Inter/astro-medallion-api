# Consumo no Databricks (SCRUM-429)

O notebook consumidor está em `databricks/ingest_api.py`. Importe ou cole esse
arquivo em um notebook Python do Databricks e crie dois Jobs apontando para o
mesmo notebook: um com o parâmetro `load_mode=daily` e outro com
`load_mode=weekly`.

Todos os datasets são gravados no catálogo/schema configurado no arquivo
(`workspace.silver` por padrão), usando o nome original publicado pela API, sem
prefixo de camada. A carga diária inclui os dez datasets Bronze e os três
Silver; a semanal inclui somente `fato_historico_geral_unidade`. A origem da
API continua respeitando as rotas e camadas Bronze, Silver e Gold.

## Chamadas HTTP

1. Guardar o token exclusivo da API no Databricks Secrets como scope
   `meus-secrets` e key `api-token`, ou ajustar esses nomes no notebook.
2. Configurar `CATALOG` e `SCHEMA` no notebook para os nomes existentes no
   workspace.
3. O notebook consulta `/v1/datasets`, seleciona os datasets conforme
   `load_mode` e segue a paginação até `has_more` ser falso.
4. Bronze usa o snapshot diário; Silver usa o período desde o maior entre
   1º de janeiro e o início do SCD; Gold usa o snapshot diário persistido.
5. Seguir pagination.next inteira, incluindo o UUID snapshot. O cron da API
   mantém capturas diárias mesmo se a leitura da fato no Databricks for semanal.

O notebook grava em Delta com `overwrite`; cada execução substitui a tabela
pela carga mais recente. Para preservar snapshots semanais da Gold, altere a
escrita para `append` e inclua uma data de ingestão.

## Histórico e consistência

A API 2.0 mantém snapshots Gold/Bronze e SCD de colaboradores desde a
instalação da migração. As páginas de uma extração são imutáveis. Histórico
anterior sem snapshots continua indisponível; consulte `history-deployment.md`.
