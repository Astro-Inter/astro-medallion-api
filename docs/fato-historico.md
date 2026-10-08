# Fato histórico persistido (SCRUM-423)

A regra de referência anterior permanece arquivada em
`reference/atualizar_fato_historico.sql`. A API 2.0 amplia a contagem de eventos
para todas as unidades; status diferente de cancelado, gestor ativo.

O grão é unidade/data. NRs são códigos distintos por unidade; colaboradores
são usuários ativos do tipo colaborador, ligados a cargo. Unidades sem
indicadores são mantidas com zero. Valores textuais seguem a normalização.

Na primeira captura do dia a API atribui id_fato_historico com a sequência de
controle e dt_criacao com o instante de captura; esses valores são retidos.
id_dim_resumo usa MD5 de unidade/data truncado a 60 bits e convertido para bigint:
é uma chave do snapshot, não uma FK da antiga dimensão. Colisões são teoricamente
possíveis; IDs sequenciais podem ter lacunas por rollback/concorrrência.

`date` aceita dias anteriores apenas se o snapshot estiver armazenado. O cron
captura diariamente mesmo sem chamada do Databricks. Dias anteriores à implantação
ou perdidos por falha prolongada retornam 409, sem simular passado com fontes atuais.
Se o consumidor ler apenas hoje semanalmente, ele continua armazenando apenas a
semana lida, mas pode buscar as outras datas que a API já tenha capturado.

SCD de usuario/cargo é mantida por triggers desde a migração. Capturas completas
e limpeza de extrações temporárias estão em `history-deployment.md`.
