# Mapeamento das fontes (SCRUM-424)

ReferÃªncia: https://astro-inter.github.io/banco-de-dados/ (modelo de 21/10/2026).
Os nomes das fontes acompanham as renomeaÃ§Ãµes de 21/10/2026. A API publicada acessa o Aiven
pelo Hyperdrive com validaÃ§Ã£o TLS usando o certificado CA configurado.
`python -m app.bronze.inspect_schema` consulta metadados das fontes do catÃ¡logo
Bronze em transaÃ§Ã£o READ ONLY e nÃ£o executa
procedures. Configure `DATABASE_SSL_CA` antes de usar o banco com CA privada.
O inspetor consulta colunas e constraints somente dessas fontes; nÃ£o consulta
as estruturas virtuais nem a procedure antiga do fato histÃ³rico.
A cÃ³pia da procedure em `reference/` documenta a regra de origem.

| Fonte | Campos pÃºblicos solicitados | Chave / relaÃ§Ãµes |
| --- | --- | --- |
| unidade | nome, id_unidade | id_unidade |
| usuario | id_usuario, unidade_id, cargo_id, tipo, status, nome | unidade_id â†’ unidade; cargo_id â†’ cargo |
| dim_nr_catalogo | codigo_nr, id_unidade | view; par id_unidade/codigo_nr |
| turma_colaborador | usuario_id, turma_id | usuario_id â†’ usuario; turma_id â†’ turma |
| turma | id_turma, data_inicial | evento_id â†’ evento |
| conclusao_evento | status, turma_colaborador_id, id_conclusao_evento, data_conclusao, data_validacao | turma_colaborador_id â†’ turma_colaborador |
| conformidade | id_conformidade, nr_id, conclusao_evento_id | nr_id â†’ nr_catalogo; conclusao_evento_id â†’ conclusao_evento |
| evento | status, id_evento, gestor_id, nr_id, modo_conclusao | gestor_id â†’ usuario |
| evento_astro | id_evento, firebase_uid, cliente_ip, tipo_evento, nome_botao, nome_tela, contexto_tela, nome_dialog, dialog_clicado, showcase_click, nome_showcase, criado_em | id_evento; eventos de uso da aplicaÃ§Ã£o |
| cargo_nr | nr_id, cargo_id | chave composta cargo_id/nr_id |
| cargo | id_cargo, nome | id_cargo |

`usuario.nome` Ã© herdado de `conta`. Os nomes fÃ­sicos sÃ£o `usuario`,
`turma_colaborador`, `data_inicial`, `data_conclusao` e `modo_conclusao`.
`usuario.cargo_id` tambÃ©m Ã© publicado no dataset Bronze e relaciona o usuÃ¡rio
com `cargo.id_cargo`. As consultas internas de geraÃ§Ã£o precisam ainda de
`usuario.criado_em` e `dim_nr_catalogo.id_dim_nr_catalogo`; esses dois campos
nÃ£o ampliam a projeÃ§Ã£o pÃºblica de `usuario`.

CalendÃ¡rio e agregaÃ§Ãµes continuam sendo derivados por SQL; posiÃ§Ã£o/resumo
leem a SCD em astro_api.usuario_history e Gold Ã© retida em astro_api.snapshots.
As fontes pÃºblicas nÃ£o sÃ£o alteradas pela API. Triggers registram versÃµes na SCD,
e o runtime grava snapshots/controle no schema astro_api.
dim_nr_catalogo continua sendo uma view de origem. NÃ£o hÃ¡ migraÃ§Ã£o DROP.

Na API, os nomes virtuais sÃ£o `colaborador_posicao` e
`resumo_colaborador_dia`, com `id_colaborador` e `qtd_colaborador`.
O fato virtual tambÃ©m publica `qtd_colaborador`. Os nomes fÃ­sicos acima e a
procedure preservada em `reference/` descrevem a origem anterior; nÃ£o sÃ£o
renomeados no PostgreSQL.

Para relacionar conclusÃµes, a extraÃ§Ã£o de `turma_colaborador` tambÃ©m expÃµe
`id_turma_colaborador`, e `turma` expÃµe `evento_id`: sÃ£o chaves de ligaÃ§Ã£o
necessÃ¡rias para a integraÃ§Ã£o e estÃ£o documentadas no contrato.

`conclusao_evento.turma_colaborador_id` referencia
`turma_colaborador.id_turma_colaborador` e Ã© obrigatÃ³rio na origem. A extraÃ§Ã£o
usa a coluna diretamente, sem depender da antiga chave de funcionÃ¡rio.

`evento_astro` Ã© uma fonte distinta de `evento`. As 11 colunas originais foram
conferidas na documentaÃ§Ã£o publicada e nos metadados do Aiven em 15/10/2026.
O campo adicional `cliente_ip INET`, opcional, segue a
[PR de banco 39 (SCRUM-407)](https://github.com/Astro-Inter/banco-de-dados/pull/39).
Ã‰ publicado como texto IPv4/IPv6 ou NULL e deve existir no banco antes do deploy.
Sua existÃªncia como `INET` no Aiven foi conferida por metadados em 18/10/2026.
`firebase_uid` preserva maiÃºsculas, minÃºsculas e o conteÃºdo original para manter
a identidade do Firebase. `criado_em` Ã© publicado como timestamp ISO 8601,
sem acrescentar fuso ao valor original (TIMESTAMP WITHOUT TIME ZONE).


## Contrato 2.0

As projeÃ§Ãµes Bronze acima acrescentam snapshot_date; tipos e chaves estÃ£o no
catÃ¡logo. A Silver de posiÃ§Ãµes/resumo agora consulta astro_api.usuario_history
(SCD Tipo 2); Gold Ã© calculada na primeira captura e mantida em astro_api.snapshots.
O runtime escreve nessas estruturas de controle e consulta as fontes por leitura.
A instalaÃ§Ã£o e o limite de histÃ³rico da versÃ£o atual estÃ£o em history-deployment.md.
