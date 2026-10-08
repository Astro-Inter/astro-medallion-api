import inspect
import json
from datetime import date, datetime, timedelta
from uuid import uuid4

from app.errors import ApiError
from app.models import Dataset, QueryOptions
from app.params import TIMEZONE
from app.queries import source_query


class PostgresSnapshots:
    """Immutable, shared snapshots: works across Worker instances and restarts."""

    def __init__(self, settings, query):
        self.settings = settings
        self.query = query

    async def execute(self, sql, values):
        if inspect.iscoroutinefunction(self.query):
            return await self.query(self.settings, sql, values)
        from starlette.concurrency import run_in_threadpool

        return await run_in_threadpool(self.query, self.settings, sql, values)

    async def available_from(self):
        rows = await self.execute(
            "SELECT (installed_at AT TIME ZONE 'America/Sao_Paulo')::date AS first_date "
            "FROM astro_api.history_control WHERE singleton",
            {},
        )
        if not rows:
            raise ApiError(503, "migration_required", "Migração de histórico não instalada.")
        value = rows[0]["first_date"]
        return date.fromisoformat(value) if isinstance(value, str) else value

    async def rate_limit(self, key, now):
        bucket = now.replace(second=0, microsecond=0)
        rows = await self.execute(
            "INSERT INTO astro_api.rate_buckets (client_key, bucket, requests) "
            "VALUES (%(key)s, %(bucket)s, 1) ON CONFLICT (client_key, bucket) "
            "DO UPDATE SET requests = astro_api.rate_buckets.requests + 1 RETURNING requests",
            {"key": key, "bucket": bucket},
        )
        used = rows[0]["requests"]
        reset = bucket + timedelta(minutes=1)
        limit = self.settings.rate_limit_per_minute
        return {
            "limit": limit,
            "remaining": max(0, limit - used),
            "retry_after": max(1, int((reset - now).total_seconds()) + 1),
            "reset": int(reset.timestamp()),
            "allowed": used <= limit,
        }

    @staticmethod
    def scope(options):
        return {
            "from": str(options.start),
            "to": str(options.end),
            "id_unidade": options.id_unidade,
        }

    async def save(self, dataset, source, values, now, scope, retained=False, row_json=False):
        snapshot_id = str(uuid4())
        columns = ", ".join(f"source.{column}" for column in dataset.columns)
        row = "source.row_data" if row_json else f"to_jsonb((SELECT r FROM (SELECT {columns}) r))"
        invalid = (
            "false"
            if row_json
            else " OR ".join(f"source.{column} IS NULL" for column in dataset.key)
        )
        order = "source.sort_key" if row_json else ", ".join(f"source.{c}" for c in dataset.key)
        sql = (
            f"WITH source AS MATERIALIZED (SELECT * FROM ({source}) bounded "
            "LIMIT %(source_limit)s), summary AS ("
            f"SELECT COUNT(*) AS row_count, COUNT(*) FILTER (WHERE {invalid}) AS invalid_count, "
            f"COALESCE(jsonb_agg({row} ORDER BY {order}), '[]'::jsonb) AS payload FROM source), "
            "saved AS (INSERT INTO astro_api.snapshots "
            "(snapshot_id, layer, dataset, scope, payload, captured_at, expires_at, retained) "
            "SELECT %(snapshot_id)s::uuid, %(layer)s, %(dataset)s, %(scope)s::jsonb, payload, "
            "%(captured_at)s, %(expires_at)s, %(retained)s FROM summary "
            "WHERE invalid_count = 0 AND row_count <= %(max_rows)s "
            "ON CONFLICT (layer, dataset, scope) WHERE retained DO NOTHING RETURNING snapshot_id) "
            "SELECT saved.snapshot_id, summary.invalid_count, summary.row_count "
            "FROM summary LEFT JOIN saved ON true"
        )
        result = (
            await self.execute(
                sql,
                {
                    **values,
                    "snapshot_id": snapshot_id,
                    "layer": dataset.layer,
                    "dataset": dataset.name,
                    "scope": json.dumps(scope),
                    "captured_at": now,
                    "expires_at": None
                    if retained
                    else now + timedelta(seconds=self.settings.snapshot_ttl_seconds),
                    "retained": retained,
                    "max_rows": self.settings.max_snapshot_rows,
                    "source_limit": self.settings.max_snapshot_rows + 1,
                },
            )
        )[0]
        if result["invalid_count"]:
            raise ApiError(503, "invalid_source_data", "A fonte contém chaves obrigatórias nulas.")
        if result["row_count"] > self.settings.max_snapshot_rows:
            raise ApiError(
                503, "snapshot_too_large", "Extração excede o limite configurado de linhas."
            )
        if result["snapshot_id"] is None:
            existing = await self.execute(
                "SELECT snapshot_id FROM astro_api.snapshots WHERE layer = %(layer)s "
                "AND dataset = %(dataset)s AND scope = %(scope)s::jsonb AND retained",
                {"layer": dataset.layer, "dataset": dataset.name, "scope": json.dumps(scope)},
            )
            return str(existing[0]["snapshot_id"])
        return str(result["snapshot_id"])

    async def capture_daily(self, dataset, now):
        today = now.astimezone(TIMEZONE).date()
        scope = {"date": str(today)}
        existing = await self.execute(
            "SELECT snapshot_id FROM astro_api.snapshots WHERE layer = %(layer)s "
            "AND dataset = %(dataset)s AND scope = %(scope)s::jsonb AND retained",
            {"layer": dataset.layer, "dataset": dataset.name, "scope": json.dumps(scope)},
        )
        if existing:
            return str(existing[0]["snapshot_id"])
        options = QueryOptions(today, today, 1000, 0)
        source, values = source_query(dataset, options, now)
        return await self.save(dataset, source, values, now, scope, retained=True)

    async def materialize(self, dataset: Dataset, options: QueryOptions, now: datetime):
        scope = self.scope(options)
        if options.snapshot:
            return options.snapshot
        if dataset.layer == "silver":
            source, values = source_query(dataset, options, now)
            return await self.save(dataset, source, values, now, scope)

        today = now.astimezone(TIMEZONE).date()
        if options.start <= today <= options.end:
            await self.capture_daily(dataset, now)
        args = {
            "layer": dataset.layer,
            "dataset": dataset.name,
            "start": options.start,
            "end": options.end,
            "unit": options.id_unidade,
        }
        dates = await self.execute(
            "SELECT COUNT(*) AS days FROM astro_api.snapshots WHERE layer = %(layer)s "
            "AND dataset = %(dataset)s AND retained "
            "AND (scope->>'date')::date BETWEEN %(start)s AND %(end)s",
            args,
        )
        if dates[0]["days"] != (options.end - options.start).days + 1:
            raise ApiError(
                409,
                "historical_snapshot_unavailable",
                "Não há snapshots para todos os dias solicitados; não reconstruir passado.",
            )
        # Sort keys use typed PostgreSQL row keys, not lexicographical numeric IDs.
        keys = []
        for column in dataset.key:
            kind = dataset.column_types.get(column, "integer")
            value = f"(item->>'{column}')"
            keys.append(value + ("::numeric" if kind == "integer" else ""))
        sort = ", ".join(["(s.scope->>'date')::date", *keys])
        source = (
            "SELECT item AS row_data, ROW_NUMBER() OVER (ORDER BY " + sort + ") AS sort_key "
            "FROM astro_api.snapshots s CROSS JOIN LATERAL jsonb_array_elements(s.payload) item "
            "WHERE s.layer = %(layer)s AND s.dataset = %(dataset)s AND s.retained "
            "AND (s.scope->>'date')::date BETWEEN %(start)s AND %(end)s "
            "AND (%(unit)s::bigint IS NULL OR (item->>'id_unidade')::bigint = %(unit)s)"
        )
        # conformidade's internal key is absent in public payloads; the retained
        # payload is already ordered, so use array ordinality as its stable tie-breaker.
        if any(key not in dataset.columns for key in dataset.key):
            source = (
                "SELECT item AS row_data, ROW_NUMBER() OVER (ORDER BY "
                "(s.scope->>'date')::date, ordinal) AS sort_key FROM astro_api.snapshots s "
                "CROSS JOIN LATERAL jsonb_array_elements(s.payload) WITH ORDINALITY a(item, ordinal) "
                "WHERE s.layer = %(layer)s AND s.dataset = %(dataset)s AND s.retained "
                "AND (s.scope->>'date')::date BETWEEN %(start)s AND %(end)s"
            )
        return await self.save(dataset, source, args, now, scope, row_json=True)

    async def page(self, dataset, options, snapshot_id, now):
        values = {
            "id": snapshot_id,
            "now": now,
            "layer": dataset.layer,
            "dataset": dataset.name,
            "scope": json.dumps(self.scope(options)),
        }
        snapshots = await self.execute(
            "SELECT captured_at, jsonb_array_length(payload) AS total_rows "
            "FROM astro_api.snapshots WHERE snapshot_id = %(id)s::uuid "
            "AND layer = %(layer)s AND dataset = %(dataset)s AND scope = %(scope)s::jsonb "
            "AND NOT retained AND expires_at > %(now)s",
            values,
        )
        if not snapshots:
            raise ApiError(
                409, "snapshot_unavailable", "Snapshot expirado ou incompatível; reinicie a carga."
            )
        page = await self.execute(
            "SELECT item AS row_data FROM astro_api.snapshots "
            "CROSS JOIN LATERAL jsonb_array_elements(payload) WITH ORDINALITY a(item, ordinal) "
            "WHERE snapshot_id = %(id)s::uuid ORDER BY ordinal LIMIT %(limit)s OFFSET %(offset)s",
            {**values, "limit": options.limit + 1, "offset": options.offset},
        )
        data = [
            json.loads(row["row_data"]) if isinstance(row["row_data"], str) else row["row_data"]
            for row in page
        ]
        return data, snapshots[0]["captured_at"]

    async def cleanup(self, now):
        await self.execute(
            "DELETE FROM astro_api.snapshots WHERE NOT retained AND expires_at <= %(now)s",
            {"now": now},
        )
        await self.execute(
            "DELETE FROM astro_api.rate_buckets WHERE bucket < %(before)s",
            {"before": now - timedelta(days=1)},
        )
