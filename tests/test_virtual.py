import unittest
from datetime import date

from app.catalog import DATASETS
from app.params import QueryOptions
from app.queries import build_query


class VirtualTests(unittest.TestCase):
    def test_derived_queries_use_operational_sources_and_bound_values(self):
        options = QueryOptions(date(2024, 2, 28), date(2024, 3, 1), 2, 1)
        for dataset in DATASETS:
            if not dataset.virtual:
                continue
            with self.subTest(dataset=dataset.name):
                sql, values = build_query(dataset, options)
                for forbidden in (
                    "public.calendario",
                    "public.funcionario_posicao",
                    "public.resumo_funcionario_dia",
                    "public.fato_historico_geral_unidade",
                ):
                    self.assertNotIn(forbidden, sql)
                self.assertIn("LIMIT %(limit)s OFFSET %(offset)s", sql)
                self.assertEqual(values["limit"], 3)
                self.assertEqual(values["offset"], 1)
                self.assertEqual(values["start"], date(2024, 2, 28))
                self.assertNotIn("2024-02-28", sql)

    def test_fact_keeps_documented_rules(self):
        dataset = next(d for d in DATASETS if d.layer == "gold")
        sql, _ = build_query(dataset, QueryOptions(date(2026, 10, 6), date(2026, 10, 6), 500, 0))
        self.assertIn("g.unidade_id = 1", sql)
        self.assertIn("e.status <> 'CANCELADO'", sql)
        self.assertIn("NULL::bigint AS id_fato_historico", sql)
        self.assertIn("NULL::timestamp AS dt_criacao", sql)
