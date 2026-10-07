# Integração Databricks (SCRUM-429)

O slide de referência separa dados brutos (Bronze), tipagem e qualidade
(Silver) e indicadores (Gold). Os exemplos usam `pyspark.pipelines` e
`@dp.materialized_view`, com ingestão externa executada como tarefa de Job.

## Preparação

Os arquivos de integração ficam em `integrations/databricks/`. As consultas
da API estão separadas em `app/bronze/`, `app/silver/` e `app/gold/`.

1. Publicar a API e adicionar seu API_TOKEN ao Databricks Secrets em
   `astro_secrets/medallion_api_token`.
2. Selecionar um catálogo gravável de Unity Catalog. O catálogo federado
   PostgreSQL não é o destino das tabelas Delta. Criar schemas bronze, silver
   e gold, e um Volume para os arquivos recebidos da API.
3. Importar `ingest_api.py` como notebook e `pipeline.py` como fonte de um
   pipeline Lakeflow. Definir catálogo/schema no pipeline e permitir nomes
   qualificados dos três schemas no runtime escolhido.
4. Configurar `astro.landing_root` com `/Volumes/<catalogo>/<schema>/<volume>`.
   O cluster do Job precisa de requests e permissão para ler secrets,
   acessar a URL da API e escrever nesse Volume.

## Execução diária

Criar um Job com duas tarefas encadeadas: notebook `ingest_api.py`, seguido
da atualização do pipeline. Usar `api_url` e `landing_root` nos widgets.
Agendar em America/Sao_Paulo, após o fechamento dos dados de origem.

O notebook baixa todas as páginas de todos os datasets antes de promovê-las
da pasta `_pending` para as pastas de ingestão. Se a extração falhar, a tarefa
falha e a atualização do pipeline não deve rodar. Limpar lotes `_pending`
abandonados conforme a política de retenção. A promoção envolve múltiplas
pastas; se ela falhar, corrigir/remover o lote incompleto antes de atualizar
o pipeline. Não executar atualização concorrente com promoção de arquivos.

Bronze mantém payloads e lote/data de extração; Silver tipa os campos e usa
o último lote completo para as fontes e derivados do ano atual; Gold mantém
o primeiro snapshot observado por unidade/dia. Arquivos de lotes antigos
devem permanecer disponíveis enquanto o pipeline depender deles. Estabelecer
retenção e compactação antes de operar em grande volume.

O Gold preserva histórico desde a primeira ingestão. Para datas anteriores,
migrar os registros físicos existentes para Delta antes de retirar as tabelas
PostgreSQL. No rollover anual, a Silver de posições/resumo passa ao ano atual;
o histórico de lotes permanece na Bronze e o fato diário permanece na Gold.

## Limites de validação

A sintaxe Python pode ser verificada localmente. A execução Spark/Lakeflow,
as permissões de Unity Catalog e o agendamento precisam ser verificados no
workspace Databricks. Não foram criados recursos no workspace por este código.
A API não congela fontes entre páginas; para cargas consistentes, usar uma
janela sem alterações no PostgreSQL.
