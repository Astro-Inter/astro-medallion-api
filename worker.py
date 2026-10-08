"""FastAPI and daily capture for Cloudflare Workers."""

import re
from datetime import datetime, timezone

import asyncpg
from workers import WorkerEntrypoint, asgi

from app.catalog import DATASETS
from app.config import Settings
from app.errors import ApiError
from app.main import create_app
from app.snapshots import PostgresSnapshots


class Default(WorkerEntrypoint):
    def services(self):
        hd = self.env.HYPERDRIVE

        async def execute(settings, sql, values, readonly=True):
            keys = []

            def parameter(match):
                key = match.group(1)
                if key not in keys:
                    keys.append(key)
                return f"${keys.index(key) + 1}"

            statement = re.sub(r"%\((\w+)\)s", parameter, sql)
            connection = None
            try:
                connection = await asyncpg.connect(
                    host=hd.host,
                    port=int(hd.port),
                    user=hd.user,
                    password=hd.password,
                    database=hd.database,
                    ssl=False,
                    timeout=10,
                    statement_cache_size=0,
                )
                async with connection.transaction(readonly=readonly):
                    await connection.execute("SET LOCAL TIME ZONE 'America/Sao_Paulo'")
                    await connection.execute("SET LOCAL statement_timeout = '10s'")
                    rows = await connection.fetch(statement, *(values[key] for key in keys))
                    return [dict(row) for row in rows]
            except (asyncpg.PostgresError, OSError, TimeoutError):
                raise ApiError(
                    503, "source_unavailable", "A fonte PostgreSQL está indisponível."
                ) from None
            finally:
                if connection is not None:
                    await connection.close()

        async def read_query(settings, sql, values):
            return await execute(settings, sql, values, readonly=True)

        async def write_query(settings, sql, values):
            return await execute(settings, sql, values, readonly=False)

        settings = Settings(
            _env_file=None,
            api_token=self.env.API_TOKEN,
            snapshot_ttl_seconds=getattr(self.env, "SNAPSHOT_TTL_SECONDS", 3600),
            max_snapshot_rows=getattr(self.env, "MAX_SNAPSHOT_ROWS", 100000),
            rate_limit_per_minute=getattr(self.env, "RATE_LIMIT_PER_MINUTE", 120),
            retry_after_seconds=getattr(self.env, "RETRY_AFTER_SECONDS", 5),
        )
        return settings, read_query, PostgresSnapshots(settings, write_query)

    async def fetch(self, request):
        settings, query, store = self.services()
        application = create_app(settings, query=query, store=store)
        return await asgi.fetch(application, request, self.env, self.ctx)

    async def scheduled(self, controller, env, ctx):
        # Four handler arguments are required by the Python Workers runtime.
        _, _, store = self.services()
        now = datetime.now(timezone.utc)
        await store.available_from()
        failures = []
        for dataset in DATASETS:
            if dataset.layer in {"bronze", "gold"}:
                try:
                    await store.capture_daily(dataset, now)
                except Exception:
                    failures.append(dataset.name)
        await store.cleanup(now)
        if failures:
            # No credentials or source records in logs.
            raise RuntimeError("Daily capture failed for: " + ", ".join(failures))
