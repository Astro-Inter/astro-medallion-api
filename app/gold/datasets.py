from app.models import virtual

DATASETS = (
    virtual(
        "fato_historico_geral_unidade",
        "gold",
        "id_fato_historico id_unidade nome_unidade id_dim_nr_catalogo id_dim_resumo qtd_nr qtd_colaborador qtd_evento dt_referencia dt_criacao",
        "dt_referencia id_unidade",
        "current_snapshot_only",
    ),
)
