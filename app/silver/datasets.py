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
        "colaborador_posicao",
        "silver",
        "data_evento id_colaborador cargo id_unidade",
        "data_evento id_colaborador",
        "scd_type_2_since_installation",
    ),
    virtual(
        "resumo_colaborador_dia",
        "silver",
        "qtd_colaborador data_evento id_unidade",
        "data_evento id_unidade",
        "scd_type_2_since_installation",
    ),
)
