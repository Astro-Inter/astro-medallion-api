import unittest
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

SETTINGS = Settings(_env_file=None, api_token="test-token-not-a-real-secret")
NOW = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)
HEADERS = {"Authorization": "Bearer test-token-not-a-real-secret"}


class ApiTests(unittest.TestCase):
    def client(self, query=None, now=NOW, settings=SETTINGS):
        async def empty(*args):
            return []

        return TestClient(create_app(settings, query or empty, lambda: now))

    def test_auth_before_database(self):
        async def fail(*args):
            self.fail("Não consultar banco sem autenticação")

        with self.client(fail) as client:
            for path in ("/health", "/v1/datasets", "/v1/bronze/usuario"):
                self.assertEqual(client.get(path).status_code, 401)
                self.assertEqual(
                    client.get(path, headers={"Authorization": "Bearer wrong"}).status_code, 401
                )
            self.assertEqual(client.get("/health", headers=HEADERS).status_code, 200)

    def test_page_precision_dates_and_next(self):
        async def query(settings, sql, values):
            self.assertIn("ORDER BY id_unidade LIMIT %(limit)s OFFSET %(offset)s", sql)
            self.assertEqual(values, {"limit": 2, "offset": 0})
            return [{"id_unidade": 9007199254740993, "nome": "A"}, {"id_unidade": 2, "nome": "B"}]

        with self.client(query) as client:
            response = client.get("/v1/bronze/unidade?limit=1", headers=HEADERS)
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["data"], [{"id_unidade": "9007199254740993", "nome": "A"}])
            self.assertEqual(body["pagination"]["next"], "/v1/bronze/unidade?limit=1&offset=1")
            self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_validation_before_database(self):
        async def fail(*args):
            self.fail("Consulta não deveria ocorrer")

        cases = [
            ("/v1/bronze/usuario?limit=1001", 400),
            ("/v1/bronze/usuario?offset=-1", 400),
            ("/v1/bronze/usuario?limit=1&limit=2", 400),
            ("/v1/bronze/usuario?sql=DROP", 400),
            ("/v1/bronze/usuario?from=2026-01-01", 400),
            ("/v1/silver/calendario?from=2026-02-30", 400),
            ("/v1/silver/calendario?to=2027-01-01", 400),
            ("/v1/silver/calendario?from=2024-01-01", 400),
            ("/v1/gold/fato_historico_geral_unidade?from=2026-10-05", 409),
            ("/v1/bronze/usuario;DROP_TABLE", 404),
        ]
        with self.client(fail) as client:
            for path, status in cases:
                with self.subTest(path=path):
                    self.assertEqual(client.get(path, headers=HEADERS).status_code, status)

    def test_sao_paulo_date(self):
        with self.client(now=datetime(2026, 10, 7, 2, tzinfo=timezone.utc)) as client:
            response = client.get(
                "/v1/gold/fato_historico_geral_unidade?from=2026-10-07&to=2026-10-07",
                headers=HEADERS,
            )
            self.assertEqual(response.status_code, 400)

    def test_errors_do_not_leak_secrets(self):
        async def fail(*args):
            raise RuntimeError("postgres://secret DROP TABLE")

        with self.client(fail) as client:
            response = client.get("/v1/bronze/unidade", headers=HEADERS)
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("secret", response.text)
            self.assertNotIn("DROP", response.text)

    def test_catalog_openapi_and_method(self):
        with self.client() as client:
            self.assertEqual(
                len(client.get("/v1/datasets", headers=HEADERS).json()["datasets"]), 14
            )
            schema = client.get("/openapi.json", headers=HEADERS).json()
            self.assertIn("HTTPBearer", schema["components"]["securitySchemes"])
            self.assertEqual(client.post("/health", headers=HEADERS).status_code, 405)
            self.assertEqual(client.get("/invalid", headers=HEADERS).status_code, 404)

    def test_swagger_can_load_before_authorization(self):
        async def fail(*args):
            self.fail("A documentação não deve consultar fontes")

        with self.client(fail) as client:
            response = client.get("/docs")
            self.assertEqual(response.status_code, 200)
            self.assertIn("SwaggerUIBundle", response.text)
            self.assertIn("/openapi.json", response.text)
            response = client.get("/openapi.json")
            self.assertEqual(response.status_code, 200)
            schema = response.json()
            self.assertEqual(
                schema["paths"]["/v1/{layer}/{dataset_name}"]["get"]["security"],
                [{"HTTPBearer": []}],
            )
            self.assertEqual(client.get("/health").status_code, 401)
            self.assertEqual(client.get("/health", headers=HEADERS).status_code, 200)


if __name__ == "__main__":
    unittest.main()
