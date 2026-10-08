# Instalação e operação do histórico (SCRUM-423)

Esta versão prepara a captura real; ela não cria fatos anteriores ao início
da coleta. A migração e o deploy devem ser executados pelo responsável pelo
banco/Worker. Este repositório não aplica migrações durante requests.

## Ordem de implantação

1. Fazer backup e aplicar `migrations/001_history_and_snapshots.sql` com o dono
   das tabelas. A migração é transacional e reaplicável; bloqueia brevemente
   escritas em usuario/cargo para instalar o baseline e os triggers sem lacunas.
2. Conceder ao papel do runtime os privilégios comentados ao final da migração.
   As fontes públicas continuam acessadas por SELECT; o runtime escreve somente
   nas tabelas de controle e utiliza a sequência da fato. Triggers SCD executam
   com o dono da migração e search_path fixo. Não conceder escrita na fonte nem
   em usuario_history ao papel de runtime.
3. Desabilitar o cache de consultas do Hyperdrive deste binding: SELECTs de
   controle/SCD precisam refletir imediatamente as escritas. A configuração é
   feita no recurso Hyperdrive, não no arquivo de binding do Worker.
4. Publicar o Worker 0.2.0 e confirmar `/health/db` e `/v1/datasets` com token.
5. O cron captura Bronze/Gold às 00h de São Paulo, com tentativas adicionais às
   01h e 02h (03h, 04h e 05h UTC). Cada snapshot diário é publicado uma única
   vez. A primeira chamada de hoje também pode criar a captura daquele dataset.
6. Atualizar clientes para seguir pagination.next inteira. O consumidor em
   `databricks/ingest_api.py` foi ajustado e mantém as 13 cargas diárias e a fato
   semanal no schema silver com nomes sem prefixo.

## Histórico e falhas

O primeiro snapshot de cada dia é imutável; mudanças posteriores entram na
captura do dia seguinte. A SCD registra todas as alterações relevantes do
usuario e renomeações de cargo a partir da instalação. Cada paginação congela
o conjunto inteiro de um dataset, mas datasets diferentes não compartilham
uma única transação. As três tentativas do cron não garantem captura em um dia
com indisponibilidade prolongada: o cliente recebe 409 para lacunas.

IDs/horários da fato ficam congelados no snapshot. O cron coleta a fato
diariamente no PostgreSQL mesmo que o consumidor Databricks a leia semanalmente.
Para consultar dias anteriores à implantação, importar snapshots existentes
com um processo específico validado contra o schema real; esta migração não
adivinha campos de tabelas legadas nem fabrica estados de usuario.

Snapshots temporários expiram e são removidos pelo cron. Históricos diários e
SCD são preservados: planejar armazenamento, backup e uma política de retenção
adequada ao projeto. Monitore falhas do cron e crescimento das tabelas.
O limite de linhas evita cargas sem limite em memória; se o volume ultrapassar
o padrão, dimensione o banco antes de aumentar MAX_SNAPSHOT_ROWS.

## Validação local

`python -m unittest discover -s tests -v` executa testes de contrato/backend.
`npm ci` e `npm run test:sql` executam as consultas e a migração num PostgreSQL
isolado (PGlite), incluindo SCD, contagens, normalização e snapshots.
Os testes não usam credenciais nem alteram o banco de produção.
