# Mapeamento das fontes (SCRUM-424)

Referência: https://astro-inter.github.io/banco-de-dados/ (build de 03/10/2026).
O schema publicado foi consultado em 06/10/2026. A validação contra o banco
ativo depende do certificado CA do Aiven: a conexão recusou a cadeia TLS.
`python -m app.bronze.inspect_schema` consulta metadados em transação READ ONLY e não executa
procedures. Configure `DATABASE_SSL_CA` antes de usar o banco com CA privada.

| Fonte | Campos públicos solicitados | Chave / relações |
| --- | --- | --- |
| unidade | nome, id_unidade | id_unidade |
| usuario | id_usuario, unidade_id, tipo, status, nome | unidade_id → unidade; cargo_id → cargo |
| dim_nr_catalogo | codigo_nr, id_unidade | view; par id_unidade/codigo_nr |
| turma_funcionario | usuario_id, turma_id | usuario_id → usuario; turma_id → turma |
| turma | id_turma, data_inicial | evento_id → evento |
| conclusao_evento | status, turma_funcionario_id, id_conclusao_evento, data_conclusao, data_validacao | turma_funcionario_id → turma_funcionario |
| conformidade | nr_id, conclusao_evento_id | nr_id → nr_catalogo; conclusao_evento_id → conclusao_evento |
| evento | status, id_evento, gestor_id, nr_id, modo_conclusao | gestor_id → usuario |
| cargo_nr | nr_id, cargo_id | chave composta cargo_id/nr_id |
| cargo | id_cargo, nome | id_cargo |

`usuario.nome` é herdado de `conta`. Os nomes físicos são `usuario`,
`turma_funcionario`, `data_inicial`, `data_conclusao` e `modo_conclusao`.
As consultas internas de geração também precisam de `usuario.cargo_id`,
`usuario.criado_em` e `dim_nr_catalogo.id_dim_nr_catalogo`.
Esses campos não ampliam a projeção pública de `usuario`.

As quatro estruturas derivadas serão calculadas por SELECT, sem ler/escrever
as tabelas físicas `calendario`, `funcionario_posicao`, `resumo_funcionario_dia`
ou `fato_historico_geral_unidade`. Não há migração DROP neste projeto.
`dim_nr_catalogo` continua sendo uma view de origem.

Para relacionar conclusões, a extração de `turma_funcionario` também expõe
`id_turma_funcionario`, e `turma` expõe `evento_id`: são chaves de ligação
necessárias para a integração e estão documentadas no contrato.
