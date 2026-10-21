from app.models import physical

DATASETS = (
    physical("unidade", "nome id_unidade", "id_unidade"),
    physical("usuario", "id_usuario unidade_id cargo_id tipo status nome", "id_usuario"),
    physical("dim_nr_catalogo", "codigo_nr id_unidade", "id_unidade codigo_nr"),
    physical(
        "turma_funcionario", "usuario_id turma_id id_turma_funcionario", "id_turma_funcionario"
    ),
    physical("turma", "id_turma data_inicial evento_id", "id_turma"),
    physical(
        "conclusao_evento",
        "status turma_funcionario_id turma_colaborador_id "
        "id_conclusao_evento data_conclusao data_validacao",
        "id_conclusao_evento",
    ),
    physical("conformidade", "id_conformidade nr_id conclusao_evento_id", "id_conformidade"),
    physical("evento", "status id_evento gestor_id nr_id modo_conclusao", "id_evento"),
    physical(
        "eventos_astro",
        "id_evento firebase_uid cliente_ip tipo_evento nome_botao nome_tela contexto_tela "
        "nome_dialog dialog_clicado showcase_click nome_showcase criado_em",
        "id_evento",
    ),
    physical("cargo_nr", "nr_id cargo_id", "cargo_id nr_id"),
    physical("cargo", "id_cargo nome", "id_cargo"),
)
