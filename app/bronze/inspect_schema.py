"""Consult the live schema without reading employee data or running procedures."""

import json
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from app.bronze.datasets import DATASETS
from app.config import Settings
from app.database import ssl_options
from app.errors import ApiError

# Inspecionar somente as fontes físicas do catálogo Bronze.
# Estruturas virtuais Silver/Gold são geradas por SELECT e não são fontes.
TABLES = [dataset.name for dataset in DATASETS]


def inspect():
    settings = Settings()
    with (
        ssl_options(settings) as options,
        psycopg.connect(**options, row_factory=dict_row, autocommit=True) as connection,
    ):
        with connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            connection.execute("SET LOCAL statement_timeout = '15s'")
            cursor = connection.execute(
                """
                SELECT table_name, column_name, data_type, udt_name, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = ANY(%s)
                ORDER BY table_name, ordinal_position
            """,
                (TABLES,),
            )
            columns = cursor.fetchall()
            cursor = connection.execute(
                """
                SELECT rel.relname AS table_name, con.conname AS name,
                       pg_get_constraintdef(con.oid) AS definition
                FROM pg_constraint con JOIN pg_class rel ON rel.oid = con.conrelid
                JOIN pg_namespace ns ON ns.oid = rel.relnamespace
                WHERE ns.nspname = 'public' AND rel.relname = ANY(%s)
                ORDER BY rel.relname, con.conname
            """,
                (TABLES,),
            )
            constraints = cursor.fetchall()
    path = Path("tmp/source-schema.json")
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "inspected_at": datetime.now(timezone.utc).isoformat(),
                "schema": "public",
                "columns": columns,
                "constraints": constraints,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Schema salvo: {len(columns)} colunas; {len(constraints)} constraints.")


if __name__ == "__main__":
    try:
        inspect()
    except (psycopg.Error, ApiError, OSError, ValueError):
        raise SystemExit(
            "Inspeção indisponível. Confira conexão e certificado CA; banco não alterado."
        ) from None
