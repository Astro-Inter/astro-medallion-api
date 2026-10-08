import unittest

from app.bronze.datasets import DATASETS as BRONZE
from app.bronze.inspect_schema import TABLES
from app.catalog import DATASETS, find_dataset


class SourceSchemaTests(unittest.TestCase):
    def test_inspection_contains_only_bronze_sources(self):
        self.assertEqual(TABLES, [dataset.name for dataset in BRONZE])
        self.assertEqual(len(TABLES), len(set(TABLES)))
        virtual_names = {dataset.name for dataset in DATASETS if dataset.virtual}
        removed_names = {"funcionario_posicao", "resumo_funcionario_dia"}
        self.assertTrue(set(TABLES).isdisjoint(virtual_names | removed_names))

    def test_virtual_contract_uses_colaborador(self):
        position = find_dataset("silver", "colaborador_posicao")
        summary = find_dataset("silver", "resumo_colaborador_dia")
        fact = find_dataset("gold", "fato_historico_geral_unidade")
        self.assertIn("id_colaborador", position.columns)
        self.assertIn("qtd_colaborador", summary.columns)
        self.assertIn("qtd_colaborador", fact.columns)
        for dataset in DATASETS:
            if dataset.virtual:
                self.assertNotIn("funcionario", dataset.name)
                self.assertFalse(any("funcionario" in field for field in dataset.columns))
