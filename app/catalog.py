from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Dataset:
    name: str
    layer: str
    columns: tuple[str, ...]
    key: tuple[str, ...]
    virtual: bool = False
    dateFilter: bool = False
    history: str = "current_source"

    def public(self) -> dict:
        return asdict(self)


def physical(name, columns, key):
    return Dataset(name, "bronze", tuple(columns.split()), tuple(key.split()))


def virtual(name, layer, columns, key, history):
    return Dataset(name, layer, tuple(columns.split()), tuple(key.split()), True, True, history)


DATASETS = (
    physical("unidade", "nome id_unidade", "id_unidade"),
    physical("usuario", "id_usuario unidade_id tipo status nome", "id_usuario"),
    physical("dim_nr_catalogo", "codigo_nr id_unidade", "id_unidade codigo_nr"),
    physical(
        "turma_funcionario", "usuario_id turma_id id_turma_funcionario", "id_turma_funcionario"
    ),
    physical("turma", "id_turma data_inicial evento_id", "id_turma"),
    physical(
        "conclusao_evento",
        "status turma_funcionario_id id_conclusao_evento data_conclusao data_validacao",
        "id_conclusao_evento",
    ),
    physical("conformidade", "nr_id conclusao_evento_id", "id_conformidade"),
    physical("evento", "status id_evento gestor_id nr_id modo_conclusao", "id_evento"),
    physical("cargo_nr", "nr_id cargo_id", "cargo_id nr_id"),
    physical("cargo", "id_cargo nome", "id_cargo"),
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
    virtual(
        "fato_historico_geral_unidade",
        "gold",
        "id_fato_historico id_unidade nome_unidade id_dim_nr_catalogo id_dim_resumo qtd_nr qtd_funcionario qtd_evento dt_referencia dt_criacao",
        "dt_referencia id_unidade",
        "current_snapshot_only",
    ),
)
ALIASES = {
    "Calendario": "calendario",
    "Func_posicao": "funcionario_posicao",
    "Resumo_func_dia": "resumo_funcionario_dia",
}


def find_dataset(layer: str, name: str) -> Dataset | None:
    return next(
        (d for d in DATASETS if d.layer == layer and d.name == ALIASES.get(name, name)), None
    )
