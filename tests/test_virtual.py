import unittest
from datetime import date

from app.catalog import DATASETS
from app.models import QueryOptions
from app.queries import build_query


class VirtualTests(unittest.TestCase):
    def test_queries_use_bound_values_and_history(self):
        options = QueryOptions(date(2026, 10, 6), date(2026, 10, 8), 2, 0)
        for dataset in DATASETS:
            sql, values = build_query(dataset, options)
            self.assertIn("LIMIT %(limit)s OFFSET %(offset)s", sql)
            self.assertEqual(values["limit"], 3)
            self.assertNotIn("2026-10-06", sql)
            if dataset.name in {"colaborador_posicao", "resumo_colaborador_dia"}:
                self.assertIn("astro_api.usuario_history", sql)

    def test_fact_all_units_and_ids(self):
        dataset = next(d for d in DATASETS if d.layer == "gold")
        sql, _ = build_query(dataset, QueryOptions(date(2026, 10, 8), date(2026, 10, 8), 500, 0))
        self.assertNotIn("g.unidade_id = 1", sql)
        self.assertIn("'cancelado'", sql)
        self.assertIn("nextval('astro_api.fact_id_seq')", sql)
        self.assertIn("MD5(", sql)
        self.assertNotIn("ROW_NUMBER", sql)

    def test_summary_keeps_empty_units(self):
        dataset = next(d for d in DATASETS if d.name == "resumo_colaborador_dia")
        sql, _ = build_query(dataset, QueryOptions(date(2026, 10, 8), date(2026, 10, 8), 500, 0))
        self.assertIn("CROSS JOIN public.unidade", sql)
        self.assertIn("LEFT JOIN posicao_virtual", sql)

    def test_bronze_normalizes_and_deduplicates_all_sources(self):
        for dataset in DATASETS:
            if dataset.layer != "bronze":
                continue
            sql, _ = build_query(
                dataset, QueryOptions(date(2026, 10, 8), date(2026, 10, 8), 500, 0)
            )
            self.assertIn("DISTINCT ON", sql)
            self.assertIn("snapshot_date", sql)
            if "string" in dataset.column_types.values():
                self.assertIn("NULLIF(LOWER(BTRIM(", sql)
