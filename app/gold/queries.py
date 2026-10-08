from app.errors import ApiError
from app.models import Dataset

FACT = """unidades AS (
  SELECT DISTINCT ON (id_unidade) id_unidade, NULLIF(LOWER(BTRIM(nome)), '') AS nome
  FROM public.unidade ORDER BY id_unidade, NULLIF(LOWER(BTRIM(nome)), '') NULLS LAST
), nr_resumo AS (
  SELECT id_unidade, COUNT(DISTINCT NULLIF(LOWER(BTRIM(codigo_nr::text)), '')) AS qtd_nr,
    MIN(id_dim_nr_catalogo) AS id_dim_nr_catalogo
  FROM public.dim_nr_catalogo GROUP BY id_unidade
), colaboradores_resumo AS (
  SELECT u.unidade_id, COUNT(DISTINCT u.id_usuario) AS qtd_colaborador
  FROM public.usuario u JOIN public.cargo c ON c.id_cargo = u.cargo_id
  WHERE LOWER(BTRIM(u.tipo::text)) = 'colaborador'
    AND LOWER(BTRIM(u.status::text)) = 'ativo'
  GROUP BY u.unidade_id
), eventos_resumo AS (
  SELECT g.unidade_id, COUNT(DISTINCT e.id_evento) AS qtd_evento
  FROM public.evento e JOIN public.usuario g ON g.id_usuario = e.gestor_id
  WHERE LOWER(BTRIM(e.status::text)) <> 'cancelado'
    AND LOWER(BTRIM(g.tipo::text)) = 'gestor'
    AND LOWER(BTRIM(g.status::text)) = 'ativo'
  GROUP BY g.unidade_id
), fato_virtual AS (
  SELECT nextval('astro_api.fact_id_seq') AS id_fato_historico, un.id_unidade,
    NULLIF(LOWER(BTRIM(un.nome)), '') AS nome_unidade, nr.id_dim_nr_catalogo,
    ('x' || SUBSTR(MD5(un.id_unidade::text || ':' || %(start)s::date::text), 1, 15))
      ::bit(60)::bigint AS id_dim_resumo,
    COALESCE(nr.qtd_nr, 0)::bigint AS qtd_nr,
    COALESCE(f.qtd_colaborador, 0)::bigint AS qtd_colaborador,
    COALESCE(e.qtd_evento, 0)::bigint AS qtd_evento,
    %(start)s::date AS dt_referencia, %(captured_at)s::timestamptz AS dt_criacao
  FROM unidades un
  LEFT JOIN nr_resumo nr ON nr.id_unidade = un.id_unidade
  LEFT JOIN colaboradores_resumo f ON f.unidade_id = un.id_unidade
  LEFT JOIN eventos_resumo e ON e.unidade_id = un.id_unidade
)"""


def virtual_sql(dataset: Dataset) -> str:
    if dataset.name != "fato_historico_geral_unidade":
        raise ApiError(404, "dataset_not_found", "Dataset gold não encontrado.")
    return f"WITH {FACT} SELECT {', '.join(dataset.columns)} FROM fato_virtual"
