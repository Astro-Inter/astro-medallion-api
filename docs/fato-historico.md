# Geração virtual do fato (SCRUM-425)

Fonte: procedure `03_atualizar_fato_historico.sql` publicada no workspace do
banco em 03/10/2026, preservada em `reference/atualizar_fato_historico.sql`.
A consulta à documentação confirmou a implementação; a inspeção do banco
ativo ainda depende do CA do Aiven.

## Regras confirmadas na documentação

- Grão: uma linha por unidade e data de referência, incluindo unidades sem
  indicadores, com contagens zeradas.
- NRs: COUNT DISTINCT codigo_nr da view dim_nr_catalogo, agrupado por unidade;
  referência da dimensão = MIN(id_dim_nr_catalogo).
- Funcionários: soma da view dim_resumo_funcionario por unidade, que considera
  COLABORADOR/ATIVO e agrupa por cargo; referência = MIN(id_dim_resumo).
- Eventos: COUNT DISTINCT id_evento com status diferente de CANCELADO, ligado
  a usuario GESTOR/ATIVO e **unidade_id = 1**. A restrição à unidade 1 é uma
  regra existente da procedure e será preservada até decisão de negócio.
- A procedure captura CURRENT_DATE e usa ON CONFLICT DO NOTHING: o primeiro
  snapshot persistido do dia não muda após alterações nas fontes.

## Contrato virtual

A API calcula o snapshot **atual**, sem executar a procedure e sem acessar
a tabela física. A referência deve ser o dia atual em America/Sao_Paulo;
pedidos de dias anteriores são recusados, pois não existe histórico de
mudanças nas fontes suficiente para reconstruir snapshots passados.

Todas as dez colunas do fato serão retornadas. `id_fato_historico` e
`dt_criacao` serão NULL: são valores gerados pela inserção física e não
existem em uma consulta virtual. A chave lógica é
`(id_unidade, dt_referencia)`. Os IDs de dimensão seguem os ROW_NUMBER das
views atuais e podem mudar quando seus conjuntos de linhas mudam.

A nomenclatura pública do headcount virtual é `qtd_colaborador`; ela
corresponde à antiga coluna `qtd_funcionario` da procedure de referência.

`dim_resumo_funcionario` será reproduzida em CTE a partir de usuario, cargo e
unidade, eliminando a dependência dessa view auxiliar. O fato utiliza o
headcount atual dessa dimensão, conforme a procedure, e não a soma de dias
de resumo_colaborador_dia.

Calendário, posições e resumo são reprocessáveis por intervalo. A projeção
de posições usa o status, cargo e unidade **atuais** do colaborador e a data
de criação; não reconstitui transferências ou desativações passadas. Essa
limitação já existe na regra de cross join fornecida como referência.

Para manter um histórico real após retirar as tabelas físicas, o Databricks
deve persistir os snapshots diários em Delta. A geração virtual por si só
não substitui armazenamento histórico. A retirada das tabelas requer
migração dos snapshots existentes e verificação dos consumidores.
