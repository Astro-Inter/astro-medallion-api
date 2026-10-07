"""Virtual SELECTs matching the published database procedure."""

from app.catalog import Dataset
from app.errors import ApiError

CALENDAR = """calendario_virtual AS (
  SELECT dia::date AS data_evento,
    EXTRACT(YEAR FROM dia)::integer AS ano,
    EXTRACT(MONTH FROM dia)::integer AS mes,
    EXTRACT(DAY FROM dia)::integer AS dia,
    EXTRACT(QUARTER FROM dia)::integer AS trimestre
  FROM generate_series(%(start)s::date::timestamp, %(end)s::date::timestamp, interval '1 day') AS dia
)"""

POSITIONS = """calendario_virtual AS (
  SELECT dia::date AS data_evento,
    EXTRACT(YEAR FROM dia)::integer AS ano,
    EXTRACT(MONTH FROM dia)::integer AS mes,
    EXTRACT(DAY FROM dia)::integer AS dia,
    EXTRACT(QUARTER FROM dia)::integer AS trimestre
  FROM generate_series(%(start)s::date::timestamp, %(end)s::date::timestamp, interval '1 day') AS dia
), posicao_virtual AS (
  SELECT cal.data_evento, u.id_usuario AS id_funcionario,
    c.nome AS cargo, u.unidade_id AS id_unidade
  FROM calendario_virtual cal
  CROSS JOIN public.usuario u
  JOIN public.cargo c ON c.id_cargo = u.cargo_id
  WHERE u.status = 'ATIVO' AND u.tipo = 'COLABORADOR'
    AND cal.data_evento >= u.criado_em::date
)"""

FACT = """nr_resumo AS (
  SELECT id_unidade, COUNT(DISTINCT codigo_nr) AS qtd_nr,
    MIN(id_dim_nr_catalogo) AS id_dim_nr_catalogo
  FROM public.dim_nr_catalogo GROUP BY id_unidade
), funcionarios_por_cargo AS (
  SELECT u.unidade_id, un.nome AS unidade, u.cargo_id, c.nome AS cargo,
    COUNT(DISTINCT u.id_usuario) AS qtd_funcionario
  FROM public.usuario u
  JOIN public.cargo c ON c.id_cargo = u.cargo_id
  JOIN public.unidade un ON un.id_unidade = u.unidade_id
  WHERE u.tipo = 'COLABORADOR' AND u.status = 'ATIVO'
  GROUP BY u.unidade_id, un.nome, u.cargo_id, c.nome
), dimensao_funcionario AS (
  SELECT *, ROW_NUMBER() OVER (ORDER BY unidade_id, cargo) AS id_dim_resumo
  FROM funcionarios_por_cargo
), funcionarios_resumo AS (
  SELECT unidade_id, SUM(qtd_funcionario)::bigint AS qtd_funcionario,
    MIN(id_dim_resumo) AS id_dim_resumo
  FROM dimensao_funcionario GROUP BY unidade_id
), eventos_resumo AS (
  SELECT g.unidade_id, COUNT(DISTINCT e.id_evento) AS qtd_evento
  FROM public.evento e JOIN public.usuario g ON g.id_usuario = e.gestor_id
  WHERE e.status <> 'CANCELADO' AND g.tipo = 'GESTOR'
    AND g.status = 'ATIVO' AND g.unidade_id = 1
  GROUP BY g.unidade_id
), fato_virtual AS (
  SELECT NULL::bigint AS id_fato_historico, un.id_unidade,
    un.nome AS nome_unidade, nr.id_dim_nr_catalogo, f.id_dim_resumo,
    COALESCE(nr.qtd_nr, 0)::bigint AS qtd_nr,
    COALESCE(f.qtd_funcionario, 0)::bigint AS qtd_funcionario,
    COALESCE(e.qtd_evento, 0)::bigint AS qtd_evento,
    %(start)s::date AS dt_referencia, NULL::timestamp AS dt_criacao
  FROM public.unidade un
  LEFT JOIN nr_resumo nr ON nr.id_unidade = un.id_unidade
  LEFT JOIN funcionarios_resumo f ON f.unidade_id = un.id_unidade
  LEFT JOIN eventos_resumo e ON e.unidade_id = un.id_unidade
  WHERE %(start)s::date = %(end)s::date
)"""


def virtual_sql(dataset: Dataset) -> str:
    fields = ", ".join(dataset.columns)
    if dataset.name == "calendario":
        return f"WITH {CALENDAR} SELECT {fields} FROM calendario_virtual"
    if dataset.name == "funcionario_posicao":
        return f"WITH {POSITIONS} SELECT {fields} FROM posicao_virtual"
    if dataset.name == "resumo_funcionario_dia":
        return (
            f"WITH {POSITIONS} SELECT COUNT(DISTINCT id_funcionario) AS qtd_funcionario, "
            "data_evento, id_unidade FROM posicao_virtual GROUP BY data_evento, id_unidade"
        )
    if dataset.name == "fato_historico_geral_unidade":
        return f"WITH {FACT} SELECT {fields} FROM fato_virtual"
    raise ApiError(404, "dataset_not_found", "Estrutura virtual não encontrada.")
