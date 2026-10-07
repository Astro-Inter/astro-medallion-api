# Contrato v1 (SCRUM-426)

Todos os endpoints exigem `Authorization: Bearer <API_TOKEN>`. O token único
está no `.env` local; em produção, use um secret do Cloudflare Workers.

- `GET /health`: disponibilidade do processo; não testa a conexão PostgreSQL.
- `GET /openapi.json`: contrato OpenAPI gerado pelo FastAPI, protegido pelo token.
- `GET /v1/datasets`: nomes, camadas, campos, chaves, semântica histórica.
- `GET /v1/bronze/{nome}`: projeção das fontes PostgreSQL selecionadas.
- `GET /v1/silver/{nome}`: calendário, posições e resumo gerados virtualmente.
- `GET /v1/gold/fato_historico_geral_unidade`: snapshot virtual do dia atual.

Nomes canônicos em `app/catalog.py`. Aliases virtuais aceitos: `Calendario`,
`Func_posicao`, `Resumo_func_dia`. Não existe endpoint para SQL arbitrário.

## Parâmetros e resposta

`limit`: 1–1000 (padrão 500); `offset`: 0–1000000 (padrão 0).
Silver/Gold também aceitam `from` e `to` no formato YYYY-MM-DD, inclusivos,
até hoje, com no máximo 366 dias. Silver usa 1º de janeiro até hoje por
padrão. Gold aceita somente hoje. Fuso de negócio: America/Sao_Paulo.
Bronze representa as fontes atuais e rejeita filtros de data.

```json
{
  "dataset": "resumo_funcionario_dia",
  "layer": "silver",
  "virtual": true,
  "extracted_at": "2026-10-06T12:00:00.000Z",
  "timezone": "America/Sao_Paulo",
  "period": {"from": "2026-10-06", "to": "2026-10-06"},
  "data": [{"qtd_funcionario": "45", "data_evento": "2026-10-06", "id_unidade": "1"}],
  "pagination": {"limit": 500, "offset": 0, "has_more": false, "next": null}
}
```

Datas SQL DATE são strings YYYY-MM-DD. Identificadores e contagens inteiras
são strings decimais para preservar precisão. Atributos do calendário
(ano, mes, dia, trimestre) são números JSON. TIMESTAMP sem timezone representa o horário
local do banco (America/Sao_Paulo) e é emitido sem offset; extracted_at é UTC.
Valores NULL são preservados. `id_unidade` no resumo será BIGINT vindo da fonte,
sem o limite INT da antiga tabela física. As chaves de paginação incluem
`conformidade.id_conformidade` internamente, sem expor essa coluna.

Cada página é uma transação READ ONLY consistente. As fontes podem mudar
entre páginas ou datasets; paginação por offset não é um snapshot congelado.
Para cargas consistentes entre páginas, executar durante janela sem alterações
ou integrar CDC/snapshot persistido numa evolução futura.

## Erros

Formato: `{"error":{"code":"invalid_date","message":"..."},"request_id":"..."}`.
400 parâmetros inválidos; 401 token ausente/incorreto; 404 recurso inexistente;
405 método diferente de GET; 409 histórico do fato indisponível;
503 credenciais ausentes ou fonte PostgreSQL indisponível.
Respostas usam Cache-Control: no-store. Erros não expõem SQL ou credenciais.

## Campos adicionais necessários

`turma_funcionario.id_turma_funcionario` e `turma.evento_id` permitem os joins
participação → conclusão e turma → evento. `resumo_funcionario_dia.id_unidade`
preserva o grão dia/unidade. Todos os outros campos respeitam a projeção
solicitada. O fato retorna todas as colunas; os valores físicos de ID e data
de inserção são NULL, conforme `fato-historico.md`.
