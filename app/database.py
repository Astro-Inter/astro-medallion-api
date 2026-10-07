import os
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from app.config import Settings
from app.errors import ApiError


def connection_options(settings: Settings) -> dict:
    url = settings.database_url.get_secret_value()
    if not url:
        raise ApiError(503, "database_not_configured", "Conexão com a fonte não configurada.")
    options = conninfo_to_dict(url)
    # libpq's sslmode=require does not validate the server identity. Always
    # enforce verification, including when the supplied URL says require.
    options["sslmode"] = "verify-full"
    options["connect_timeout"] = 10
    if settings.database_ssl_ca_file:
        options["sslrootcert"] = str(settings.database_ssl_ca_file)
    return options


@contextmanager
def ssl_options(settings: Settings):
    options = connection_options(settings)
    pem = settings.database_ssl_ca.get_secret_value()
    if not pem:
        yield options
        return
    # libpq accepts a CA file, not PEM text. Keep it outside the repository
    # and remove it after closing this connection.
    path = None
    try:
        with NamedTemporaryFile(mode="w", suffix=".pem", encoding="utf-8", delete=False) as ca:
            ca.write(pem.replace("\\n", "\n"))
            path = Path(ca.name)
        os.chmod(path, 0o600)
        options["sslrootcert"] = str(path)
        yield options
    finally:
        if path:
            path.unlink(missing_ok=True)


def run_query(settings: Settings, sql: str, values: dict) -> list[dict]:
    try:
        with ssl_options(settings) as options:
            with psycopg.connect(**options, row_factory=dict_row, autocommit=True) as connection:
                with connection.transaction():
                    connection.execute("SET TRANSACTION READ ONLY")
                    connection.execute("SET LOCAL TIME ZONE 'America/Sao_Paulo'")
                    connection.execute("SET LOCAL statement_timeout = '10s'")
                    cursor = connection.execute(sql, values)
                    return cursor.fetchall()
    except ApiError:
        raise
    except (psycopg.Error, OSError, ValueError):
        raise ApiError(503, "source_unavailable", "A fonte PostgreSQL está indisponível.") from None
