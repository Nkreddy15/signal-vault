"""Static design guard only; this DOES NOT substitute for PostgreSQL tests."""
from pathlib import Path
import unittest

SQL = Path(__file__).resolve().parents[1] / "db" / "migrations" / "0002_critical_paper.sql"


class PostgresPaperSchemaDesignTests(unittest.TestCase):
    def test_migration_is_explicitly_paper_only_and_halted_first_boot(self):
        ddl = SQL.read_text()
        self.assertIn("CHECK(mode = 'paper')", ddl)
        self.assertIn("operator_halted BOOLEAN NOT NULL DEFAULT TRUE", ddl)
        self.assertIn("ON CONFLICT (singleton) DO NOTHING", ddl)
        self.assertNotIn("DEFAULT 'live'", ddl)

    def test_unique_unknown_order_guard_and_external_order_identity(self):
        ddl = SQL.read_text()
        self.assertIn("ux_sv_paper_one_unresolved_order", ddl)
        self.assertIn("WHERE stage <> 'reconciled'", ddl)
        self.assertIn("client_order_id TEXT PRIMARY KEY", ddl)
        self.assertIn("broker_order_id TEXT UNIQUE", ddl)
        self.assertIn("provider_fill_id TEXT PRIMARY KEY", ddl)
        self.assertIn("'unknown_result'", ddl)

    def test_exact_currency_and_immutable_history_constraints(self):
        ddl = SQL.read_text()
        self.assertIn("NUMERIC(28,12)", ddl)
        self.assertIn("NUMERIC(32,18)", ddl)
        self.assertNotIn("DOUBLE PRECISION", ddl)
        self.assertIn("BEFORE UPDATE OR DELETE", ddl)
        self.assertIn("SIGNAL VAULT", ddl.upper())

    def test_design_explicitly_unapplied_until_integration(self):
        guide = (SQL.parent.parent.parent / "docs" / "POSTGRES_PAPER_LEDGER.md").read_text()
        self.assertIn("unapplied design", guide)
        self.assertIn("actual PostgreSQL instance", guide)


if __name__ == "__main__":
    unittest.main()
