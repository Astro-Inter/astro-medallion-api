from app.errors import ApiError
from app.models import Dataset

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
    if dataset.name != "fato_historico_geral_unidade":
        raise ApiError(404, "dataset_not_found", "Dataset gold não encontrado.")
    return f"WITH {FACT} SELECT {', '.join(dataset.columns)} FROM fato_virtual"
