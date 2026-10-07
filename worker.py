"""Entrypoint FastAPI para Cloudflare Workers Free."""

import re

import asyncpg
from workers import WorkerEntrypoint, asgi

from app.config import Settings
from app.errors import ApiError
from app.main import create_app


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        hd = self.env.HYPERDRIVE

        async def query(settings, sql, values):
            keys = []

            def parameter(match):
                key = match.group(1)
                if key not in keys:
                    keys.append(key)
                return f"${keys.index(key) + 1}"

            statement = re.sub(r"%\((\w+)\)s", parameter, sql)
            connection = None
            try:
                # A origem Aiven é validada em TLS pelo Hyperdrive. O socket
                # entre Worker e binding é interno à plataforma Cloudflare.
                connection = await asyncpg.connect(
                    host=hd.host, port=int(hd.port), user=hd.user,
                    password=hd.password, database=hd.database,
                    ssl=False, timeout=10, statement_cache_size=0,
                )
                async with connection.transaction(readonly=True):
                    await connection.execute("SET LOCAL TIME ZONE 'America/Sao_Paulo'")
                    await connection.execute("SET LOCAL statement_timeout = '10s'")
                    rows = await connection.fetch(statement, *(values[key] for key in keys))
                    return [dict(row) for row in rows]
            except (asyncpg.PostgresError, OSError, TimeoutError):
                raise ApiError(503, "source_unavailable", "A fonte PostgreSQL está indisponível.") from None
            finally:
                if connection is not None:
                    await connection.close()

        application = create_app(
            Settings(_env_file=None, api_token=self.env.API_TOKEN), query=query,
        )
        return await asgi.fetch(application, request, self.env, self.ctx)
