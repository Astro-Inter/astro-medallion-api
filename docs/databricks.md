# Consumo no Databricks (SCRUM-429)

O código de consumo será implementado diretamente no Databricks. Este
repositório fornece a API e não contém notebooks ou pipelines externos.

## Chamadas HTTP

1. Guardar o token exclusivo da API no Databricks Secrets.
2. Consultar `/v1/datasets` para conhecer os datasets e seus campos.
3. Fazer requisições HTTPS com `Authorization: Bearer <API_TOKEN>`.
4. Consumir `/v1/bronze/{dataset}`, `/v1/silver/{dataset}` e
   `/v1/gold/{dataset}`; seguir `pagination.next` até `has_more` ser falso.
5. Para estruturas virtuais, informar `from` e `to` em YYYY-MM-DD quando necessário.

O calendário, as posições e o resumo diário são calculados na Silver da API;
o fato consolidado é calculado na Gold. A ingestão, persistência em Delta,
qualidade, histórico e agendamento serão configurados no Databricks.

## Histórico e consistência

O fato virtual representa o dia atual. Preservar snapshots por unidade/dia
no Databricks e migrar o histórico físico existente antes de retirar tabelas.
Posições de datas anteriores usam o cadastro atual, sem reconstruir antigas
transferências ou desativações. A API não congela as fontes entre páginas;
para uma carga consistente, usar uma janela sem alterações no PostgreSQL.
