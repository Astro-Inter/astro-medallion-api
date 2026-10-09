# Contrato da API 2.0 (SCRUM-423)

As URLs `/v1/...` permanecem, mas o contrato de dados é `api_version: "2.0"`.
O catálogo também mantém `columns` como lista de nomes e acrescenta
`column_types`, `required_columns`, `date_filter_basis` e `history_capture_started`.
Os tipos descritos são os tipos lógicos da saída normalizada: `integer`,
`string`, `date` e `timestamp`. Inteiros continuam sendo strings no JSON, exceto
ano/mês/dia/trimestre do calendário. NULL continua NULL.

## Endpoints

Dados, catálogo e saúde exigem `Authorization: Bearer <API_TOKEN>`.
`/docs` e `/openapi.json` são públicos.

- `GET /health`: disponibilidade do processo, sem consultar o banco.
- `GET /health/db`: executa `SELECT 1`; 503 se a fonte estiver indisponível.
- `GET /v1/datasets`: 14 datasets e seus tipos/regras de histórico.
- `GET /v1/bronze/{nome}`: snapshot diário normalizado da fonte.
- `GET /v1/silver/{nome}`: calendário ou posição/resumo com SCD Tipo 2.
- `GET /v1/gold/fato_historico_geral_unidade`: snapshot diário persistido.

## Bronze

O dataset `usuario` publica `cargo_id`, relacionado a `cargo.id_cargo`, como
identificador inteiro (string decimal no JSON, ou NULL quando ausente).
Snapshots de `usuario` capturados antes dessa inclusão não recebem o campo
retroativamente: o histórico preserva o payload original, e novas capturas
diárias passam a incluí-lo.

As dez fontes preservam seus nomes, acrescentando `snapshot_date` às
projeções anteriores e expondo `id_conformidade` como chave pública de conformidade. Textos são convertidos para minúsculas e aparados com BTRIM;
strings vazias viram NULL. Colunas declaradas como date são convertidas para
DATE no PostgreSQL. Cada fonte é deduplicada pela chave do catálogo.
Quando uma chave tem versões divergentes, a linha com os menores valores
normalizados das outras colunas (NULLS LAST) é escolhida de forma determinística;
isso não representa seleção de uma versão mais recente. Chave obrigatória nula
impede a publicação de todo o snapshot e retorna 503 `invalid_source_data`.

`from` e `to` filtram **datas de captura**, não datas de criação/modificação do
registro. Assim todas as dez fontes suportam períodos, inclusive fontes sem
timestamp de negócio. A saída inclui uma versão por registro/dia e
`snapshot_date` distingue essas versões. O padrão é hoje. Dias sem captura
retornam 409; passado nunca é reconstruído a partir do cadastro atual.

## Silver

`calendario` gera as datas solicitadas. `colaborador_posicao` lê
`astro_api.usuario_history`, que guarda versões de status, tipo, cargo e unidade,
incluindo o nome do cargo. O estado considerado é o fim do dia em São Paulo;
para hoje, o instante de captura. Colaboradores ativos são incluídos a partir de
`criado_em`. `resumo_colaborador_dia` inclui todas as unidades atuais em todos
os dias solicitados, com zero quando não existem colaboradores.

A captura SCD começa na instalação da migração. Períodos anteriores são
recusados com 409. O início padrão é o maior entre 1º de janeiro e a primeira
data disponível. Calendário não depende desse limite. O cadastro de unidades
da grade de zeros é o cadastro atual; não existe SCD de unidades neste contrato.

## Gold

Use `date=YYYY-MM-DD` para hoje ou para um snapshot já capturado. `from` e `to`
continuam aceitos se forem iguais; não combine os dois formatos. Não há
reconstrução retroativa: dia sem snapshot retorna 409.

Eventos são contados para **todas** as unidades, considerando evento diferente
de cancelado e gestor ativo. `id_unidade` filtra opcionalmente o resultado.
Contagens de NRs/colaboradores e unidades com zeros continuam disponíveis.

`id_fato_historico` é obtido da sequência de controle na primeira captura e
`dt_criacao` registra essa captura. `id_dim_resumo` é uma chave determinística
de 60 bits baseada em unidade/data, não mais o ROW_NUMBER do conjunto atual.
IDs de sequência podem ter lacunas; hashes têm risco teórico de colisão e não
devem ser tratados como uma chave estrangeira da antiga view de dimensão.

## Paginação consistente

A primeira requisição cria uma extração imutável no PostgreSQL. Continue
usando **a URL inteira de `pagination.next`**, incluindo `snapshot` e filtros.
Offset sozinho não é mais aceito quando maior que zero. Trocar filtros ou
dataset com o mesmo UUID retorna 409. As páginas não voltam a consultar a fonte.
As extrações temporárias expiram em 3.600 segundos por padrão; reinicie a carga
se receber 409 `snapshot_unavailable`. Snapshots diários de origem são retidos.
`limit`: 1–1000, padrão 500; `offset`: até 1000000. Intervalos: até 366 dias,
inclusivos, sem datas futuras. Fuso de negócio: America/Sao_Paulo.

```json
{
  "api_version": "2.0",
  "dataset": "resumo_colaborador_dia",
  "layer": "silver",
  "virtual": true,
  "extracted_at": "2026-10-08T12:00:00+00:00",
  "timezone": "America/Sao_Paulo",
  "period": {"from": "2026-10-08", "to": "2026-10-08"},
  "data": [{"qtd_colaborador": "0", "data_evento": "2026-10-08", "id_unidade": "2"}],
  "pagination": {"limit": 500, "offset": 0, "has_more": false,
    "snapshot": "00000000-0000-0000-0000-000000000001", "next": null}
}
```

## Rate limiting e erros

O limite padrão é 120 requisições por minuto **compartilhadas por API_TOKEN**,
com contador atômico no PostgreSQL, inclusive entre instâncias do Worker.
Documentação e `/health` ficam fora desse limite. Respostas após a contagem
incluem `X-RateLimit-Limit`, `X-RateLimit-Remaining` e `X-RateLimit-Reset` (Unix).
429 inclui `Retry-After` até a próxima janela. 503 inclui `Retry-After: 5` por
padrão. Ausência de headers de taxa em uma falha de armazenamento não significa
limite infinito. Nenhum valor de token é persistido: o contador usa SHA-256.

Erros incluem `api_version`, `error.code`, `error.message` e `request_id`.
400 parâmetros inválidos; 401 autenticação; 404 dataset; 405 método;
409 histórico/snapshot indisponível; 429 limite; 503 fonte, armazenamento,
chave nula ou extração acima de MAX_SNAPSHOT_ROWS (padrão 100000).
Não registrar nem retornar SQL, credenciais ou conteúdo pessoal nos logs.
