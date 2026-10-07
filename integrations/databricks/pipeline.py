"""Lakeflow declarative pipeline: raw API pages → typed data → daily fact.

Configure catalog + schema in the pipeline UI, create bronze/silver/gold schemas
there, and set astro.landing_root to the ingestion job's Volume path.
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F
from pyspark.sql.window import Window

LANDING = spark.conf.get("astro.landing_root").rstrip("/")

# These schemas match the API projection. JSON string IDs are cast to BIGINT
# in Silver; _raw preserves the exact payload received in Bronze.
SCHEMAS = {
    "unidade": "nome STRING, id_unidade BIGINT",
    "usuario": "id_usuario BIGINT, unidade_id BIGINT, tipo STRING, status STRING, nome STRING",
    "dim_nr_catalogo": "codigo_nr INT, id_unidade BIGINT",
    "turma_funcionario": "usuario_id BIGINT, turma_id BIGINT, id_turma_funcionario BIGINT",
    "turma": "id_turma BIGINT, data_inicial TIMESTAMP_NTZ, evento_id BIGINT",
    "conclusao_evento": "status STRING, turma_funcionario_id BIGINT, id_conclusao_evento BIGINT, data_conclusao TIMESTAMP_NTZ, data_validacao TIMESTAMP_NTZ",
    "conformidade": "nr_id INT, conclusao_evento_id BIGINT",
    "evento": "status STRING, id_evento BIGINT, gestor_id BIGINT, nr_id INT, modo_conclusao STRING",
    "cargo_nr": "nr_id INT, cargo_id BIGINT",
    "cargo": "id_cargo BIGINT, nome STRING",
    "calendario": "data_evento DATE, ano INT, mes INT, dia INT, trimestre INT",
    "funcionario_posicao": "data_evento DATE, id_funcionario BIGINT, cargo STRING, id_unidade BIGINT",
    "resumo_funcionario_dia": "qtd_funcionario BIGINT, data_evento DATE, id_unidade BIGINT",
    "fato_historico_geral_unidade": "id_fato_historico BIGINT, id_unidade BIGINT, nome_unidade STRING, id_dim_nr_catalogo BIGINT, id_dim_resumo BIGINT, qtd_nr BIGINT, qtd_funcionario BIGINT, qtd_evento BIGINT, dt_referencia DATE, dt_criacao TIMESTAMP_NTZ",
}


def register(name, schema):
    fields = [field.strip().split()[0] for field in schema.split(",")]
    raw_fields = ", ".join(field + ": STRING" for field in fields)
    envelope = f"data ARRAY<STRUCT<{raw_fields}>>, extracted_at STRING, batch_id STRING"

    @dp.materialized_view(name=f"bronze.{name}")
    def bronze():
        pages = (
            spark.read.format("json")
            .schema(envelope)
            .option("multiLine", True)
            .load(f"{LANDING}/{name}/*/*.json")
        )
        return pages.select(
            F.explode_outer("data").alias("record"),
            F.to_timestamp("extracted_at").alias("_extracted_at"),
            F.col("batch_id").alias("_batch_id"),
        ).select(F.to_json("record").alias("_raw"), "_extracted_at", "_batch_id")

    def parsed(raw):
        # pg serializes BIGINT as a JSON string. Parse strings first, then cast
        # explicitly; directly parsing quoted IDs as JSON BIGINT can fail.
        typed = [(part.strip().split()[0], part.strip().split()[1]) for part in schema.split(",")]
        return raw.withColumn(
            "record", F.from_json("_raw", f"STRUCT<{raw_fields}>", {"mode": "FAILFAST"})
        ).select(
            *[F.col(f"record.{field}").cast(dtype).alias(field) for field, dtype in typed],
            "_extracted_at",
            "_batch_id",
        )

    if name == "fato_historico_geral_unidade":

        @dp.materialized_view(name="gold.fato_historico_geral_unidade")
        @dp.expect_or_fail("unidade_presente", "id_unidade IS NOT NULL")
        @dp.expect_or_fail("referencia_presente", "dt_referencia IS NOT NULL")
        def gold():
            raw = spark.read.table(f"bronze.{name}").filter("_raw IS NOT NULL")
            # Preserve the first observed snapshot of each day, matching the
            # procedure's ON CONFLICT DO NOTHING semantics across reruns.
            window = Window.partitionBy("dt_referencia", "id_unidade").orderBy(
                "_batch_id", "_extracted_at"
            )
            return (
                parsed(raw)
                .withColumn("_rank", F.row_number().over(window))
                .filter("_rank = 1")
                .drop("_rank")
            )
    else:

        @dp.materialized_view(name=f"silver.{name}")
        def silver():
            raw = spark.read.table(f"bronze.{name}")
            latest = raw.agg(F.max("_batch_id").alias("_latest"))
            # The empty-page marker ensures that a deleted or empty source
            # clears the current Silver dataset instead of reviving old rows.
            current = raw.crossJoin(latest).filter(
                (F.col("_batch_id") == F.col("_latest")) & F.col("_raw").isNotNull()
            )
            return parsed(current)


for dataset_name, dataset_schema in SCHEMAS.items():
    register(dataset_name, dataset_schema)
