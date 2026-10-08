"""Export actual API statements for the isolated PostgreSQL contract test."""

import asyncio
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.catalog import DATASETS
from app.config import Settings
from app.models import QueryOptions
from app.queries import source_query
from app.snapshots import PostgresSnapshots

NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
options = QueryOptions(date(2026, 10, 8), date(2026, 10, 8), 1, 0)
exports = {"source": {}, "retained": {}, "temporary": {}}


async def main():
    recorded = []

    async def query(settings, sql, values):
        recorded.append({"sql": sql, "values": values})
        if sql.startswith("SELECT captured_at"):
            return [{"captured_at": NOW, "total_rows": 3}]
        if sql.startswith("SELECT item AS row_data"):
            return []
        if sql.startswith("INSERT INTO astro_api.rate_buckets"):
            return [{"requests": 1}]
        if sql.startswith("SELECT COUNT(*) AS days"):
            return [{"days": 1}]
        return [{"snapshot_id": values.get("snapshot_id"), "invalid_count": 0, "row_count": 3}]

    store = PostgresSnapshots(Settings(_env_file=None), query)
    for dataset in DATASETS:
        source, values = source_query(dataset, options, NOW)
        exports["source"][dataset.name] = {"sql": source, "values": values}
        await store.save(dataset, source, values, NOW, store.scope(options))
        exports["temporary"][dataset.name] = recorded[-1]
        if dataset.layer in {"bronze", "gold"}:
            await store.save(dataset, source, values, NOW, {"date": "2026-10-08"}, retained=True)
            exports["retained"][dataset.name] = recorded[-1]
    dataset = next(d for d in DATASETS if d.name == "unidade")
    await store.page(dataset, options, "00000000-0000-0000-0000-000000000001", NOW)
    exports["page_metadata"], exports["page_rows"] = recorded[-2:]
    await store.rate_limit("test-client", NOW)
    exports["rate"] = recorded[-1]
    yesterday = QueryOptions(date(2026, 10, 7), date(2026, 10, 7), 1, 0)
    await store.materialize(dataset, yesterday, NOW)
    exports["historical"] = recorded[-1]
    gold = next(d for d in DATASETS if d.layer == "gold")
    await store.materialize(
        gold, QueryOptions(date(2026, 10, 7), date(2026, 10, 7), 1, 0, id_unidade=2), NOW
    )
    exports["gold_historical"] = recorded[-1]


asyncio.run(main())
print(json.dumps(exports, default=lambda value: value.isoformat()))
