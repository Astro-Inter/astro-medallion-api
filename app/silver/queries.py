from app.errors import ApiError
from app.models import Dataset

CALENDAR = """calendario_virtual AS (
  SELECT dia::date AS data_evento,
    EXTRACT(YEAR FROM dia)::integer AS ano,
    EXTRACT(MONTH FROM dia)::integer AS mes,
    EXTRACT(DAY FROM dia)::integer AS dia,
    EXTRACT(QUARTER FROM dia)::integer AS trimestre
  FROM generate_series(%(start)s::date::timestamp, %(end)s::date::timestamp, interval '1 day') AS dia
)"""

POSITIONS = (
    CALENDAR
    + """, posicao_virtual AS (
  SELECT cal.data_evento, u.id_usuario AS id_funcionario,
    c.nome AS cargo, u.unidade_id AS id_unidade
  FROM calendario_virtual cal
  CROSS JOIN public.usuario u
  JOIN public.cargo c ON c.id_cargo = u.cargo_id
  WHERE u.status = 'ATIVO' AND u.tipo = 'COLABORADOR'
    AND cal.data_evento >= u.criado_em::date
)"""
)


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
    raise ApiError(404, "dataset_not_found", "Dataset silver não encontrado.")
