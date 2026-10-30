"""Export catalog/SQL from Python at build time; never connect to the database."""

import asyncio
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.catalog import ALIASES, DATASETS  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import QueryOptions  # noqa: E402
from app.queries import source_query  # noqa: E402
from app.snapshots import PostgresSnapshots  # noqa: E402


async def main():
    recorded = []
    now = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
    options = QueryOptions(date(2026, 10, 7), date(2026, 10, 7), 1000, 0)

    async def capture(settings, sql, values):
        recorded.append(sql)
        if sql.startswith("SELECT COUNT(*) AS days"):
            return [{"days": 1}]
        return [
            {
                "snapshot_id": "00000000-0000-0000-0000-000000000001",
                "invalid_count": 0,
                "row_count": 1,
            }
        ]

    store = PostgresSnapshots(Settings(_env_file=None), capture)
    datasets = []
    for dataset in DATASETS:
        source, values = source_query(dataset, options, now)
        await store.save(dataset, source, values, now, store.scope(options))
        source_save = recorded[-1]
        if dataset.layer != "silver":
            await store.materialize(dataset, options, now)
            range_save = recorded[-1]
        else:
            range_save = None
        datasets.append({**dataset.public(), "source_save": source_save, "range_save": range_save})
    document = {
        "datasets": datasets,
        "aliases": ALIASES,
        "openapi": create_app(Settings(_env_file=None)).openapi(),
    }
    path = ROOT / "edge" / "contract.json"
    path.write_text(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    print(f"Exported {len(datasets)} datasets and their SQL templates; no database access.")


asyncio.run(main())
