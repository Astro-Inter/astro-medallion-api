import unittest
from datetime import date, datetime, timezone

from app.catalog import DATASETS
from app.config import Settings
from app.errors import ApiError
from app.models import QueryOptions
from app.snapshots import PostgresSnapshots

NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)


class SnapshotTests(unittest.IsolatedAsyncioTestCase):
    def store(self, execute):
        return PostgresSnapshots(Settings(_env_file=None), execute)

    async def test_invalid_keys_and_large_sources_are_not_published(self):
        dataset = next(d for d in DATASETS if d.name == "unidade")
        for counts, code in [
            ({"invalid_count": 1, "row_count": 3}, "invalid_source_data"),
            ({"invalid_count": 0, "row_count": 100001}, "snapshot_too_large"),
        ]:

            async def execute(settings, sql, values):
                self.assertIn("WHERE invalid_count = 0", sql)
                self.assertIn("LIMIT %(source_limit)s", sql)
                return [{"snapshot_id": None, **counts}]

            with self.assertRaises(ApiError) as error:
                await self.store(execute).save(dataset, "SELECT 1", {}, NOW, {})
            self.assertEqual(error.exception.code, code)

    async def test_missing_historical_day_is_refused(self):
        dataset = next(d for d in DATASETS if d.layer == "gold")

        async def execute(*args):
            return [{"days": 0}]

        with self.assertRaises(ApiError) as error:
            await self.store(execute).materialize(
                dataset, QueryOptions(date(2026, 10, 7), date(2026, 10, 7), 500, 0), NOW
            )
        self.assertEqual(error.exception.code, "historical_snapshot_unavailable")

    async def test_page_requires_exact_scope_and_valid_ttl(self):
        dataset = next(d for d in DATASETS if d.name == "unidade")

        async def execute(settings, sql, values):
            self.assertIn("scope = %(scope)s::jsonb", sql)
            self.assertIn("expires_at > %(now)s", sql)
            return []

        with self.assertRaises(ApiError) as error:
            await self.store(execute).page(
                dataset,
                QueryOptions(date(2026, 10, 8), date(2026, 10, 8), 500, 0),
                "00000000-0000-0000-0000-000000000001",
                NOW,
            )
        self.assertEqual(error.exception.code, "snapshot_unavailable")

    async def test_json_string_payload_is_decoded_for_asyncpg(self):
        dataset = next(d for d in DATASETS if d.name == "unidade")
        calls = 0

        async def execute(*args):
            nonlocal calls
            calls += 1
            if calls == 1:
                return [{"captured_at": NOW, "total_rows": 1}]
            return [{"row_data": '{"id_unidade": 9007199254740993, "nome": "a"}'}]

        rows, at = await self.store(execute).page(
            dataset,
            QueryOptions(date(2026, 10, 8), date(2026, 10, 8), 500, 0),
            "00000000-0000-0000-0000-000000000001",
            NOW,
        )
        self.assertEqual(rows[0]["id_unidade"], 9007199254740993)
        self.assertEqual(at, NOW)
