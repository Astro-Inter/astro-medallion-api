"""Optional entry point for the isolated SQL integration suite.

Set RUN_SQL_INTEGRATION=1 after npm ci; no production DB credentials are used.
"""

import os
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(os.getenv("RUN_SQL_INTEGRATION") == "1", "SQL suite: npm run test:sql")
class SqlIntegrationTests(unittest.TestCase):
    def test_sql_contract_in_isolated_postgresql(self):
        result = subprocess.run(
            ["node", "tests/sql_contract.mjs"],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            capture_output=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
