import unittest
from unittest.mock import MagicMock, patch

import psycopg

from app.config import Settings
from app.database import connection_options, run_query, run_snapshot_query, ssl_options
from app.errors import ApiError


class DatabaseTests(unittest.TestCase):
    def settings(self, **kwargs):
        return Settings(
            _env_file=None,
            database_url="postgresql://test:test@example.test/db?sslmode=require",
            **kwargs,
        )

    def test_tls_enforced_and_inline_ca_cleaned_up(self):
        self.assertEqual(connection_options(self.settings())["sslmode"], "verify-full")
        from pathlib import Path

        with ssl_options(self.settings(database_ssl_ca="TEST\\nCA")) as options:
            path = Path(options["sslrootcert"])
            self.assertEqual(path.read_text(), "TEST\nCA")
        self.assertFalse(path.exists())

    def test_read_only_and_timeouts_before_select(self):
        connection = MagicMock()
        connection.execute.return_value.fetchall.return_value = [{"id": 1}]
        with patch("app.database.psycopg.connect") as connect:
            connect.return_value.__enter__.return_value = connection
            rows = run_query(self.settings(), "SELECT id FROM public.unidade", {})
        self.assertEqual(rows, [{"id": 1}])
        self.assertEqual(
            [call.args[0] for call in connection.execute.call_args_list],
            [
                "SET TRANSACTION READ ONLY",
                "SET LOCAL TIME ZONE 'America/Sao_Paulo'",
                "SET LOCAL statement_timeout = '10s'",
                "SELECT id FROM public.unidade",
            ],
        )

    def test_control_writer_does_not_open_a_readonly_transaction(self):
        connection = MagicMock()
        connection.execute.return_value.fetchall.return_value = [{"requests": 1}]
        with patch("app.database.psycopg.connect") as connect:
            connect.return_value.__enter__.return_value = connection
            run_snapshot_query(self.settings(), "SELECT 1", {})
        statements = [call.args[0] for call in connection.execute.call_args_list]
        self.assertNotIn("SET TRANSACTION READ ONLY", statements)
        self.assertIn("SET LOCAL statement_timeout = '10s'", statements)

    def test_failure_sanitized(self):
        with patch(
            "app.database.psycopg.connect", side_effect=psycopg.OperationalError("password=secret")
        ):
            with self.assertRaises(ApiError) as error:
                run_query(self.settings(), "SELECT 1", {})
        self.assertEqual(error.exception.status, 503)
        self.assertNotIn("secret", str(error.exception))
