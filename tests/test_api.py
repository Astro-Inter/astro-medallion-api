import copy
import unittest
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import Settings
from app.errors import ApiError
from app.main import create_app

SETTINGS = Settings(_env_file=None, api_token="test-token-not-a-real-secret")
NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
HEADERS = {"Authorization": "Bearer test-token-not-a-real-secret"}


class FakeSnapshots:
    def __init__(self, rows=None, settings=SETTINGS):
        self.rows = rows or []
        self.settings = settings
        self.snapshots = {}
        self.requests = 0
        self.failure = None

    async def available_from(self):
        return date(2026, 10, 1)

    async def rate_limit(self, key, now):
        self.requests += 1
        limit = self.settings.rate_limit_per_minute
        return {
            "limit": limit,
            "remaining": max(0, limit - self.requests),
            "retry_after": 60,
            "reset": int(now.timestamp()) + 60,
            "allowed": self.requests <= limit,
        }

    async def materialize(self, dataset, options, now):
        if self.failure:
            raise self.failure
        if options.snapshot:
            return options.snapshot
        if dataset.layer == "gold" and options.start < date(2026, 10, 7):
            raise ApiError(409, "historical_snapshot_unavailable", "Snapshot não capturado.")
        identity = str(uuid4())
        scope = (dataset.name, options.start, options.end, options.id_unidade)
        self.snapshots[identity] = (scope, copy.deepcopy(self.rows), now)
        return identity

    async def page(self, dataset, options, identity, now):
        item = self.snapshots.get(identity)
        scope = (dataset.name, options.start, options.end, options.id_unidade)
        if item is None or item[0] != scope or item[2] + timedelta(seconds=3600) <= now:
            raise ApiError(409, "snapshot_unavailable", "Snapshot incompatível ou expirado.")
        return item[1][options.offset : options.offset + options.limit + 1], item[2]


class ApiTests(unittest.TestCase):
    def client(self, query=None, now=NOW, settings=SETTINGS, store=None):
        async def healthy(*args):
            return [{"available": 1}]

        return TestClient(
            create_app(
                settings,
                query or healthy,
                lambda: now,
                store=store or FakeSnapshots(settings=settings),
            )
        )

    def test_auth_before_storage_and_database(self):
        store = FakeSnapshots()

        async def fail(*args):
            self.fail("Não consultar banco sem autenticação")

        with self.client(fail, store=store) as client:
            for path in ("/health", "/health/db", "/v1/datasets", "/v1/bronze/usuario"):
                self.assertEqual(client.get(path).status_code, 401)
                self.assertEqual(
                    client.get(path, headers={"Authorization": "Bearer wrong"}).status_code, 401
                )
            self.assertEqual(store.requests, 0)
            self.assertEqual(client.get("/health", headers=HEADERS).status_code, 200)

    def test_precision_dates_and_next_freeze_source(self):
        store = FakeSnapshots(
            [{"id_unidade": 9007199254740993, "nome": "a"}, {"id_unidade": 2, "nome": "b"}]
        )
        with self.client(store=store) as client:
            first = client.get("/v1/bronze/unidade?limit=1", headers=HEADERS)
            self.assertEqual(first.status_code, 200)
            body = first.json()
            self.assertEqual(body["api_version"], "2.0")
            self.assertEqual(body["data"], [{"id_unidade": "9007199254740993", "nome": "a"}])
            self.assertIn("snapshot=", body["pagination"]["next"])
            store.rows = [{"id_unidade": 99, "nome": "changed"}]
            second = client.get(body["pagination"]["next"], headers=HEADERS)
            self.assertEqual(second.json()["data"], [{"id_unidade": "2", "nome": "b"}])
            self.assertEqual(second.json()["extracted_at"], body["extracted_at"])
            self.assertFalse(second.json()["pagination"]["has_more"])
            self.assertEqual(first.headers["Cache-Control"], "no-store")

    def test_validation(self):
        cases = [
            ("/v1/bronze/usuario?limit=1001", 400),
            ("/v1/bronze/usuario?offset=-1", 400),
            ("/v1/bronze/usuario?offset=1", 400),
            ("/v1/bronze/usuario?limit=1&limit=2", 400),
            ("/v1/bronze/usuario?sql=DROP", 400),
            ("/v1/silver/calendario?from=2026-02-30", 400),
            ("/v1/silver/calendario?to=2027-01-01", 400),
            ("/v1/silver/calendario?from=2024-01-01", 400),
            ("/v1/silver/colaborador_posicao?from=2026-09-30", 409),
            ("/v1/gold/fato_historico_geral_unidade?date=2026-10-05", 409),
            ("/v1/gold/fato_historico_geral_unidade?date=2026-10-07&from=2026-10-07", 400),
            ("/v1/bronze/usuario?snapshot=invalid", 400),
            ("/v1/bronze/usuario;DROP_TABLE", 404),
        ]
        with self.client() as client:
            for path, status in cases:
                with self.subTest(path=path):
                    self.assertEqual(client.get(path, headers=HEADERS).status_code, status)

    def test_historical_gold_and_bronze_filters(self):
        with self.client() as client:
            for path in (
                "/v1/gold/fato_historico_geral_unidade?date=2026-10-07&id_unidade=2",
                "/v1/bronze/usuario?from=2026-10-01&to=2026-10-08",
            ):
                response = client.get(path, headers=HEADERS)
                self.assertEqual(response.status_code, 200)

    def test_sao_paulo_date(self):
        with self.client(now=datetime(2026, 10, 9, 2, tzinfo=timezone.utc)) as client:
            response = client.get(
                "/v1/gold/fato_historico_geral_unidade?date=2026-10-09", headers=HEADERS
            )
            self.assertEqual(response.status_code, 400)

    def test_errors_do_not_leak_secrets_and_have_retry(self):
        store = FakeSnapshots()
        store.failure = RuntimeError("postgres://secret DROP TABLE")
        with self.client(store=store) as client:
            response = client.get("/v1/bronze/unidade", headers=HEADERS)
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.headers["Retry-After"], "5")
            self.assertEqual(response.json()["api_version"], "2.0")
            self.assertNotIn("secret", response.text)
            self.assertNotIn("DROP", response.text)

    def test_catalog_types_and_public_docs(self):
        with self.client() as client:
            body = client.get("/v1/datasets", headers=HEADERS).json()
            self.assertEqual(len(body["datasets"]), 14)
            for dataset in body["datasets"]:
                self.assertEqual(set(dataset["columns"]), set(dataset["column_types"]))
            self.assertEqual(client.get("/docs").status_code, 200)
            schema = client.get("/openapi.json").json()
            self.assertIn("HTTPBearer", schema["components"]["securitySchemes"])
            self.assertIn("/health/db", schema["paths"])
            self.assertEqual(client.post("/health", headers=HEADERS).status_code, 405)

    def test_db_health_queries_source(self):
        calls = []

        async def query(settings, sql, values):
            calls.append(sql)
            return [{"available": 1}]

        with self.client(query) as client:
            self.assertEqual(client.get("/health", headers=HEADERS).status_code, 200)
            self.assertEqual(calls, [])
            self.assertEqual(client.get("/health/db", headers=HEADERS).status_code, 200)
            self.assertEqual(calls, ["SELECT 1 AS available"])

    def test_rate_limit_headers_and_429(self):
        settings = Settings(
            _env_file=None, api_token="test-token-not-a-real-secret", rate_limit_per_minute=2
        )
        with self.client(settings=settings) as client:
            one = client.get("/v1/datasets", headers=HEADERS)
            two = client.get("/v1/datasets", headers=HEADERS)
            three = client.get("/v1/datasets", headers=HEADERS)
            self.assertEqual(one.headers["X-RateLimit-Remaining"], "1")
            self.assertEqual(two.headers["X-RateLimit-Remaining"], "0")
            self.assertEqual(three.status_code, 429)
            self.assertEqual(three.headers["Retry-After"], "60")

    def test_snapshot_binding_and_expiry(self):
        store = FakeSnapshots([{"id_unidade": 1}])
        with self.client(store=store) as client:
            body = client.get("/v1/bronze/unidade", headers=HEADERS).json()
            identity = body["pagination"]["snapshot"]
            wrong = client.get(f"/v1/bronze/usuario?snapshot={identity}", headers=HEADERS)
            self.assertEqual(wrong.status_code, 409)
        with self.client(store=store, now=NOW + timedelta(hours=2)) as client:
            expired = client.get(f"/v1/bronze/unidade?snapshot={identity}", headers=HEADERS)
            self.assertEqual(expired.status_code, 409)


if __name__ == "__main__":
    unittest.main()
