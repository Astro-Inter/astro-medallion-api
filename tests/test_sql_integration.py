"""Optional integration test against a disposable PostgreSQL test database.

Set TEST_DATABASE_URL explicitly. All tables are created in a unique schema
inside a transaction which is rolled back, leaving the database untouched.
"""

import os
import unittest
import uuid
from datetime import date

import psycopg
from psycopg.rows import dict_row

from app.catalog import DATASETS
from app.params import QueryOptions
from app.queries import build_query

DDL = """
CREATE TABLE unidade(id_unidade bigint PRIMARY KEY, nome text);
CREATE TABLE cargo(id_cargo bigint PRIMARY KEY, nome text);
CREATE TABLE usuario(id_usuario bigint PRIMARY KEY, nome text, tipo text,
  status text, unidade_id bigint, cargo_id bigint, criado_em timestamp);
CREATE TABLE dim_nr_catalogo(id_dim_nr_catalogo bigint, codigo_nr integer, id_unidade bigint);
CREATE TABLE evento(id_evento bigint, gestor_id bigint, status text);
INSERT INTO unidade VALUES (1, 'A'), (2, 'B'), (3, 'Sem funcionários');
INSERT INTO cargo VALUES (1, 'Analista'), (2, 'Operador');
INSERT INTO usuario VALUES
  (1, 'A', 'COLABORADOR', 'ATIVO', 1, 1, '2024-02-28'),
  (2, 'B', 'COLABORADOR', 'ATIVO', 1, 2, '2024-02-29'),
  (3, 'C', 'COLABORADOR', 'ATIVO', 2, 1, '2024-03-01'),
  (4, 'D', 'COLABORADOR', 'DESATIVADO', 1, 1, '2024-01-01'),
  (5, 'GA', 'GESTOR', 'ATIVO', 1, 1, '2024-01-01'),
  (6, 'GB', 'GESTOR', 'ATIVO', 2, 1, '2024-01-01'),
  (7, 'GD', 'GESTOR', 'DESATIVADO', 1, 1, '2024-01-01');
INSERT INTO dim_nr_catalogo VALUES (1, 10, 1), (2, 10, 1), (3, 35, 1), (4, 6, 2);
INSERT INTO evento VALUES (1, 5, 'ATIVO'), (2, 5, 'CONCLUIDO'),
  (3, 5, 'CANCELADO'), (4, 6, 'ATIVO'), (5, 7, 'ATIVO');
"""


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"), "Defina TEST_DATABASE_URL para teste PostgreSQL"
)
class SqlIntegrationTests(unittest.TestCase):
    def test_virtual_data(self):
        schema = "test_medallion_" + uuid.uuid4().hex
        with psycopg.connect(os.environ["TEST_DATABASE_URL"], row_factory=dict_row) as connection:
            try:
                connection.execute(
                    psycopg.sql.SQL("CREATE SCHEMA {}").format(psycopg.sql.Identifier(schema))
                )
                connection.execute(
                    psycopg.sql.SQL("SET LOCAL search_path TO {}").format(
                        psycopg.sql.Identifier(schema)
                    )
                )
                connection.execute(DDL)

                def read(name, start=date(2024, 2, 28), end=date(2024, 3, 1)):
                    dataset = next(d for d in DATASETS if d.name == name)
                    sql, values = build_query(dataset, QueryOptions(start, end, 1000, 0))
                    return connection.execute(
                        sql.replace("public.", schema + "."), values
                    ).fetchall()

                calendar = read("calendario")
                self.assertEqual(
                    [r["data_evento"] for r in calendar],
                    [date(2024, 2, 28), date(2024, 2, 29), date(2024, 3, 1)],
                )
                self.assertEqual(len(read("funcionario_posicao")), 6)
                self.assertEqual(
                    [r["qtd_funcionario"] for r in read("resumo_funcionario_dia")], [1, 2, 2, 1]
                )
                fact = read("fato_historico_geral_unidade", date(2024, 3, 1), date(2024, 3, 1))
                self.assertEqual(
                    [(r["qtd_nr"], r["qtd_funcionario"], r["qtd_evento"]) for r in fact],
                    [(2, 2, 2), (1, 1, 0), (0, 0, 0)],
                )
                self.assertIsNone(fact[0]["id_fato_historico"])
                self.assertIsNone(fact[0]["dt_criacao"])
                self.assertEqual(
                    read("fato_historico_geral_unidade", date(2024, 3, 1), date(2024, 3, 1)), fact
                )
            finally:
                connection.rollback()
