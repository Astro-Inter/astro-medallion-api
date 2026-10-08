from app.errors import ApiError
from app.models import Dataset

CALENDAR = """calendario_virtual AS (
  SELECT dia::date AS data_evento,
    EXTRACT(YEAR FROM dia)::integer AS ano,
    EXTRACT(MONTH FROM dia)::integer AS mes,
    EXTRACT(DAY FROM dia)::integer AS dia,
    EXTRACT(QUARTER FROM dia)::integer AS trimestre
  FROM generate_series(%(start)s::date::timestamp, %(end)s::date::timestamp,
    interval '1 day') AS dia
)"""

POSITIONS = (
    CALENDAR
    + """, posicao_virtual AS (
  SELECT cal.data_evento, h.id_usuario AS id_colaborador,
    h.cargo AS cargo, h.id_unidade
  FROM calendario_virtual cal
  JOIN astro_api.usuario_history h ON
    h.valid_from <= LEAST(
      %(captured_at)s::timestamptz,
      ((cal.data_evento + 1)::timestamp AT TIME ZONE 'America/Sao_Paulo')
        - interval '1 microsecond'
    )
    AND (h.valid_to IS NULL OR h.valid_to > LEAST(
      %(captured_at)s::timestamptz,
      ((cal.data_evento + 1)::timestamp AT TIME ZONE 'America/Sao_Paulo')
        - interval '1 microsecond'
    ))
  WHERE h.status = 'ativo' AND h.tipo = 'colaborador'
    AND cal.data_evento >= h.criado_em::date
)"""
)


def virtual_sql(dataset: Dataset) -> str:
    fields = ", ".join(dataset.columns)
    if dataset.name == "calendario":
        return f"WITH {CALENDAR} SELECT {fields} FROM calendario_virtual"
    if dataset.name == "colaborador_posicao":
        return f"WITH {POSITIONS} SELECT {fields} FROM posicao_virtual"
    if dataset.name == "resumo_colaborador_dia":
        return (
            f"WITH {POSITIONS} SELECT COUNT(DISTINCT p.id_colaborador) AS qtd_colaborador, "
            "cal.data_evento, un.id_unidade FROM calendario_virtual cal "
            "CROSS JOIN public.unidade un LEFT JOIN posicao_virtual p "
            "ON p.data_evento = cal.data_evento AND p.id_unidade = un.id_unidade "
            "GROUP BY cal.data_evento, un.id_unidade"
        )
    raise ApiError(404, "dataset_not_found", "Dataset silver não encontrado.")
