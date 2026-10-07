CREATE OR REPLACE PROCEDURE public.atualizar_fato_historico()
 LANGUAGE plpgsql
AS $procedure$
BEGIN
    WITH resumo_nr AS (
        SELECT
            id_unidade,
            COUNT(DISTINCT codigo_nr) AS qtd_nr,
            MIN(id_dim_nr_catalogo) AS id_dim_nr_catalogo
        FROM dim_nr_catalogo
        GROUP BY id_unidade
    ),
    resumo_funcionario AS (
        SELECT
            unidade_id,
            SUM(qtd_funcionario) AS qtd_funcionario,
            MIN(id_dim_resumo) AS id_dim_resumo
        FROM dim_resumo_funcionario
        GROUP BY 1
    ),
    base_eventos AS (
        SELECT
            id_evento,
            gestor_id,
            nr_id,
            modo_conclusao,
            status
        FROM evento
        WHERE status <> 'CANCELADO'
    ),
    base_gestor AS (
        SELECT
            id_usuario,
            unidade_id
        FROM usuario
        WHERE tipo = 'GESTOR'
          AND status = 'ATIVO'
          AND unidade_id = 1
    ),
    juncao_eventos AS (
        SELECT
            b.id_evento,
            bg.unidade_id
        FROM base_eventos b
        JOIN base_gestor bg ON bg.id_usuario = b.gestor_id
    ),
    resumo_eventos AS (
        SELECT
            unidade_id,
            COUNT(DISTINCT id_evento) AS qtd_evento
        FROM juncao_eventos
        GROUP BY 1
    )
    INSERT INTO fato_historico_geral_unidade (
        id_unidade,
        nome_unidade,
        id_dim_nr_catalogo,
        id_dim_resumo,
        qtd_nr,
        qtd_funcionario,
        qtd_evento,
        dt_referencia
    )
    SELECT
        u.id_unidade,
        u.nome,
        nr.id_dim_nr_catalogo,
        f.id_dim_resumo,
        COALESCE(nr.qtd_nr, 0),
        COALESCE(f.qtd_funcionario, 0),
        COALESCE(re.qtd_evento, 0),
        CURRENT_DATE
    FROM unidade u
    LEFT JOIN resumo_nr nr
        ON nr.id_unidade = u.id_unidade
    LEFT JOIN resumo_funcionario f
        ON f.unidade_id = u.id_unidade
    LEFT JOIN resumo_eventos re
        ON re.unidade_id = u.id_unidade
    ON CONFLICT (id_unidade, dt_referencia)
    DO NOTHING;
END;
$procedure$;
