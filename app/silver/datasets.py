from app.models import virtual

DATASETS = (
    virtual(
        "calendario",
        "silver",
        "data_evento ano mes dia trimestre",
        "data_evento",
        "generated_dates",
    ),
    virtual(
        "funcionario_posicao",
        "silver",
        "data_evento id_funcionario cargo id_unidade",
        "data_evento id_funcionario",
        "current_users_projected_over_dates",
    ),
    virtual(
        "resumo_funcionario_dia",
        "silver",
        "qtd_funcionario data_evento id_unidade",
        "data_evento id_unidade",
        "current_users_projected_over_dates",
    ),
)
