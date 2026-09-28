import json
import tempfile
import unittest
from pathlib import Path

from signal_vault.health import build_health_snapshot, write_health_snapshot
from signal_vault.owner_api import OwnerApiConfig, OwnerService
from signal_vault.paper_runtime import PaperCycleResult
from signal_vault.paper_store import PersistentPaperOrderStore
from datetime import datetime, timezone


TOKEN="x"*40


class OwnerApiTests(unittest.TestCase):
    def config(self, root):
        return OwnerApiConfig(root/"paper.db", root/"health.json", TOKEN)

    def test_config_rejects_remote_bind_and_short_token(self):
        base={"SIGNAL_VAULT_OWNER_TOKEN":TOKEN,"SIGNAL_VAULT_OWNER_HOST":"0.0.0.0"}
        with self.assertRaises(ValueError): OwnerApiConfig.from_environment(base)
        with self.assertRaises(ValueError): OwnerApiConfig.from_environment({"SIGNAL_VAULT_OWNER_TOKEN":"short"})

    def test_constant_time_style_bearer_gate_and_safe_status(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); cfg=self.config(root)
            with PersistentPaperOrderStore(cfg.db_path): pass
            service=OwnerService(cfg)
            self.assertFalse(service.authorized(None))
            self.assertFalse(service.authorized("Bearer wrong"))
            self.assertTrue(service.authorized("Bearer "+TOKEN))
            status=service.status()
            self.assertEqual(status["mode"],"ALPACA_PAPER_ONLY")
            self.assertEqual(status["logical"]["cash_usd"],"100")
            self.assertNotIn("account_id",json.dumps(status).lower())

    def test_halt_and_resume_persist(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); cfg=self.config(root)
            with PersistentPaperOrderStore(cfg.db_path): pass
            service=OwnerService(cfg)
            self.assertTrue(service.halt("manual review")["operator_halted"])
            self.assertFalse(service.resume()["operator_halted"])

    def test_health_allowlists_fields_even_if_file_contains_extra(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); cfg=self.config(root)
            with PersistentPaperOrderStore(cfg.db_path) as store:
                logical=store.logical_account()
            payload=build_health_snapshot(result=PaperCycleResult("HOLD","x"), logical=logical,
                                          operator_halted=False,
                                          at=datetime(2026,9,28,tzinfo=timezone.utc))
            payload["provider_secret"]="NOPE"
            write_health_snapshot(cfg.health_path,payload)
            result=OwnerService(cfg).health()
            self.assertNotIn("provider_secret",result)

class OwnerReadOnlySafetyTests(unittest.TestCase):
    def test_read_only_status_does_not_create_missing_database(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            cfg=OwnerApiConfig(root/'missing-paper.db', root/'health.json', TOKEN)
            service=OwnerService(cfg)
            with self.assertRaises(ValueError):
                service.status()
            self.assertFalse(cfg.db_path.exists())
            with self.assertRaises(ValueError):
                service.resume()
            self.assertFalse(cfg.db_path.exists())

    def test_last_mark_is_labelled_historical_not_current_equity(self):
        from decimal import Decimal
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            cfg=OwnerApiConfig(root/'paper.db', root/'health.json', TOKEN)
            with PersistentPaperOrderStore(cfg.db_path) as book:
                book.mark_portfolio(mark_price=Decimal('65000'), at=datetime.now(timezone.utc))
            status=OwnerService(cfg).status()
            self.assertEqual(status['last_mark']['source'], 'LAST_PERSISTED_PAPER_MARK_NOT_LIVE')
            self.assertEqual(status['last_mark']['btc_usd'], '65000')
