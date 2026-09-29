"""GET-only, one-tick auto scheduler tests use disposable source + fake providers."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch, Mock

from signal_vault.forward_capture import capture_current_window, default_capture_path
from signal_vault.forward_evidence_audit import audit_forward_evidence
from signal_vault.forward_observer import ForwardObservationJournal
from signal_vault.market_data import Bar
from signal_vault.runtime_lock import RuntimeAlreadyLocked, RuntimeFileLock
from signal_vault.unattended_forward_cycle import (
    ACCOUNT, SERVICE_ID, SERVICE_SECRET, load_keychain_paper_data_credentials,
    run_unattended_once, status_unattended,
)

END = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)


def synthetic(closed):
    start=closed-timedelta(hours=72)
    values=[]
    for i in range(72):
        at=start+timedelta(hours=i)
        index=int((at-(END-timedelta(hours=72))).total_seconds()/3600)
        px=D("150")+D(index)/D("10")
        values.append(Bar(at, px, px+D("3"), px-D("2"), px,D("100"),
                          "alpaca_crypto_us"))
    return tuple(values)


class FakeProvider:
    def __init__(self, dataset):
        self.bars=dataset
        self.calls=0
    def fetch(self, *, start,end,as_of):
        self.calls+=1
        return self.bars


class SourceFactory:
    def __init__(self):
        self.calls=0
        self.sources=[]
    def at(self,closed):
        self.sources.append(FakeProvider(synthetic(closed)))
        source=self.sources[-1]
        def build():
            self.calls+=1
            return source
        return build


def tick(root,closed,factory, *, minute=7):
    start=closed+timedelta(minutes=minute)
    return run_unattended_once(
        root=root,now=start,provider_factory=factory,
        after_capture_now=lambda: start+timedelta(minutes=1))


def file_shas(folder):
    return {str(p.relative_to(folder)):sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob("*") if p.is_file()}


class UnattendedForwardTests(unittest.TestCase):
    def test_new_auto_segment_0_then_1_then_2_observations_all_audited(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward"
            root.mkdir(mode=0o700)
            source=SourceFactory()
            first=tick(root,END,source.at(END))
            self.assertEqual(first["decision"],"FIRST_AUTO_SEGMENT_BOOTSTRAPPED")
            self.assertEqual(first["new_forward_observation_count"],0)
            db=root/"observations-auto-20261012T1200Z.sqlite3"
            self.assertTrue(db.is_file())
            self.assertEqual(db.stat().st_mode & 0o777,0o600)
            self.assertFalse((root/"observations.sqlite3").exists())
            second=tick(root,END+HOUR,source.at(END+HOUR))
            self.assertEqual(second["decision"],"ONE_NEW_PROSPECTIVE_CANDLE_RECORDED")
            self.assertEqual(second["new_forward_observation_count"],1)
            third=tick(root,END+2*HOUR,source.at(END+2*HOUR))
            self.assertEqual(third["new_forward_observation_count"],2)
            self.assertEqual(audit_forward_evidence(root=root,db=db)
                             ["prospective_observations_verified"],2)
            self.assertEqual(source.calls,3)
            self.assertEqual([p.calls for p in source.sources],[1,1,1])
            self.assertEqual(status_unattended(root=root)["prospective_observations_verified"],2)
            self.assertEqual(len(list((root/"automation"/"receipts").glob("*.json"))),3)
            self.assertEqual((root/"automation"/"active_segment.json").stat().st_mode & 0o777,0o600)
            self.assertEqual(first["broker_order_submission"],"DISABLED")
            self.assertFalse(first["credentials_written_to_disk_or_logs"])

    def test_same_hour_idempotent_no_keychain_or_provider_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward";root.mkdir(mode=0o700)
            source=SourceFactory()
            tick(root,END,source.at(END))
            old=file_shas(root)
            second=tick(root,END,lambda: self.fail("must not fetch twice"),minute=13)
            self.assertEqual(second["decision"],"ALREADY_PROCESSED_OR_NEXT_HOUR_NOT_CLOSED")
            self.assertEqual(second["network_requests"],"NONE")
            self.assertEqual(source.calls,1)
            # Receipts alone can be added; raw archive and auto journal remain intact.
            self.assertEqual(file_shas(root/"captures"),
                             {key.removeprefix("captures/"):value for key,value in old.items()
                              if key.startswith("captures/")})

    def test_missed_hour_seals_prior_and_bootstraps_separate_zero_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward";root.mkdir(mode=0o700)
            source=SourceFactory()
            tick(root,END,source.at(END))
            tick(root,END+HOUR,source.at(END+HOUR))
            old=root/"observations-auto-20261012T1200Z.sqlite3"
            old_hash=sha256(old.read_bytes()).hexdigest()
            response=tick(root,END+3*HOUR,source.at(END+3*HOUR))
            self.assertEqual(response["decision"],"NEW_AUTO_SEGMENT_AFTER_MISSED_HOUR")
            self.assertEqual(response["new_forward_observation_count"],0)
            self.assertEqual(response["first_missed_prospective_close_utc"],
                             (END+2*HOUR).isoformat())
            self.assertEqual(response["previous_segment_preserved"],str(old))
            self.assertEqual(sha256(old.read_bytes()).hexdigest(),old_hash)
            next_db=root/"observations-auto-20261012T1500Z.sqlite3"
            self.assertTrue(next_db.is_file())
            self.assertEqual(audit_forward_evidence(root=root,db=old)
                             ["prospective_observations_verified"],1)
            self.assertEqual(audit_forward_evidence(root=root,db=next_db)
                             ["prospective_observations_verified"],0)
            again=tick(root,END+4*HOUR,source.at(END+4*HOUR))
            self.assertEqual(again["new_forward_observation_count"],1)
            self.assertEqual(source.calls,4)

    def test_sleep_or_wrong_minute_skips_and_does_not_use_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward";root.mkdir(mode=0o700)
            for minute in (0,2,25,40,59):
                output=tick(root,END,lambda: self.fail("should not request keys"),minute=minute)
                self.assertEqual(output["decision"],"SKIP_OUTSIDE_SAFE_UTC_MINUTE_03_TO_24")
                self.assertEqual(output["market_data_request"],
                                 "NONE_UNLESS_TIME_AND_EVIDENCE_PREFLIGHT_PASSES")
            self.assertFalse((root/"automation"/"active_segment.json").exists())
            self.assertFalse((root/"observations.sqlite3").exists())

    def test_existing_capture_collision_refuses_secret_read_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward";root.mkdir(mode=0o700)
            at=END+timedelta(minutes=7)
            csv=root/"captures"/default_capture_path(at).name
            capture_current_window(FakeProvider(synthetic(END)),
                                   now=at, output_csv=csv)
            before=file_shas(root/"captures")
            failed=tick(root,END,lambda: self.fail("should not request Keychain"))
            self.assertEqual(failed["decision"],"HALT_PRESERVE_ALL_ORIGINAL_EVIDENCE")
            self.assertEqual(failed["failure_class"],"ValueError")
            self.assertEqual(file_shas(root/"captures"),before)
            self.assertFalse((root/"automation"/"active_segment.json").exists())

    def test_broken_prior_segment_blocks_gap_restart_and_preserves_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward";root.mkdir(mode=0o700)
            source=SourceFactory()
            tick(root,END,source.at(END))
            raw=next((root/"captures").glob("*.csv"))
            raw.write_bytes(raw.read_bytes()+b"tamper")
            failed=tick(root,END+3*HOUR,lambda: self.fail("must not fetch"))
            self.assertEqual(failed["decision"],"HALT_PRESERVE_ALL_ORIGINAL_EVIDENCE")
            self.assertFalse((root/"observations-auto-20261012T1500Z.sqlite3").exists())
            self.assertEqual(source.calls,1)

    def test_bad_provider_failure_receipt_redacts_exception_and_no_state_pointer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward";root.mkdir(mode=0o700)
            def bad():
                raise RuntimeError("sensitive-token-should-not-appear")
            result=tick(root,END,bad)
            self.assertEqual(result["decision"],"HALT_PRESERVE_ALL_ORIGINAL_EVIDENCE")
            self.assertNotIn("sensitive-token",json.dumps(result))
            saved=next((root/"automation"/"receipts").glob("*.json")).read_text()
            self.assertNotIn("sensitive-token",saved)
            self.assertNotIn("secret",saved.lower().replace("credentials_written_to_disk_or_logs",""))
            self.assertFalse((root/"automation"/"active_segment.json").exists())

    def test_old_manual_primary_journal_remains_separate_from_auto_segment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward";root.mkdir(mode=0o700)
            old_close=END-timedelta(hours=24)
            at=old_close+timedelta(minutes=7)
            csv=root/"captures"/default_capture_path(at).name
            oldbars=synthetic(old_close)
            receipt=capture_current_window(FakeProvider(oldbars),now=at,output_csv=csv)
            with ForwardObservationJournal(root/"observations.sqlite3",initialize=True) as journal:
                journal.process(oldbars,csv_sha256=receipt.csv_sha256,
                                observed_at=at+timedelta(minutes=1),bootstrap=True)
            old=root/"observations.sqlite3"
            before=sha256(old.read_bytes()).hexdigest()
            response=tick(root,END,SourceFactory().at(END))
            self.assertEqual(response["decision"],"FIRST_AUTO_SEGMENT_BOOTSTRAPPED")
            self.assertEqual(sha256(old.read_bytes()).hexdigest(),before)

    def test_pointer_behind_audited_segment_is_crash_recovered_not_backfilled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward";root.mkdir(mode=0o700)
            source=SourceFactory()
            tick(root,END,source.at(END))
            tick(root,END+HOUR,source.at(END+HOUR))
            ptr=root/"automation"/"active_segment.json"
            data=json.loads(ptr.read_text())
            data["last_successful_close_utc"]=END.isoformat()
            ptr.write_text(json.dumps(data))
            third=tick(root,END+2*HOUR,source.at(END+2*HOUR))
            self.assertEqual(third["decision"],"ONE_NEW_PROSPECTIVE_CANDLE_RECORDED")
            self.assertTrue(third["prior_pointer_reconciled"])
            self.assertEqual(third["new_forward_observation_count"],2)

    def test_clock_rollback_and_invalid_pointer_halt_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward";root.mkdir(mode=0o700)
            tick(root,END,SourceFactory().at(END))
            ptr=root/"automation"/"active_segment.json"
            first=tick(root,END-timedelta(hours=1),
                       lambda: self.fail("rollback must refuse data"))
            self.assertEqual(first["decision"],"HALT_PRESERVE_ALL_ORIGINAL_EVIDENCE")
            data=json.loads(ptr.read_text());data["active_journal"]="../observations.sqlite3"
            ptr.write_text(json.dumps(data))
            second=tick(root,END+HOUR,lambda: self.fail("tampered pointer"))
            self.assertEqual(second["decision"],"HALT_PRESERVE_ALL_ORIGINAL_EVIDENCE")

    def test_tampered_manifest_after_current_capture_keeps_orphan_and_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward";root.mkdir(mode=0o700)
            tick(root,END,SourceFactory().at(END))
            ptr=root/"automation"/"active_segment.json"
            initial=ptr.read_bytes()
            broken=list(synthetic(END+HOUR))
            from dataclasses import replace
            broken[-2]=replace(broken[-2],close=broken[-2].close+D("1"))
            p=FakeProvider(tuple(broken))
            failed=tick(root,END+HOUR,lambda: p)
            self.assertEqual(failed["decision"],"HALT_PRESERVE_ALL_ORIGINAL_EVIDENCE")
            self.assertEqual(ptr.read_bytes(),initial)
            self.assertTrue((root/"captures"/default_capture_path(
                END+HOUR+timedelta(minutes=7)).name).is_file())
            # Future tick may start a distinct new segment, never re-label old one.
            next_step=tick(root,END+2*HOUR,SourceFactory().at(END+2*HOUR))
            self.assertEqual(next_step["decision"],"NEW_AUTO_SEGMENT_AFTER_MISSED_HOUR")

    def test_local_keychain_reader_never_passes_password_as_argv(self):
        observed=[]
        def run(argv, **kwargs):
            observed.append((argv,kwargs))
            password="local-key-id" if SERVICE_ID in argv else "local-secret"
            return Mock(returncode=0,stdout=password+"\n")
        with patch("signal_vault.unattended_forward_cycle.os.environ",{}),patch(
            "signal_vault.unattended_forward_cycle.subprocess.run",side_effect=run),patch(
            "signal_vault.unattended_forward_cycle.Path.is_file",return_value=True):
            credentials=load_keychain_paper_data_credentials()
        self.assertEqual(credentials.key_id,"local-key-id")
        self.assertEqual(credentials.secret_key,"local-secret")
        self.assertEqual(len(observed),2)
        self.assertTrue(all("-w" == args[0][-1] for args in observed))
        self.assertTrue(all(args[1]["stderr"] is __import__("subprocess").DEVNULL
                            for args in observed))
        self.assertFalse(any("local-secret" in json.dumps(argv) for argv,_ in observed))

    def test_generic_live_environment_refused_even_when_keychain_has_items(self):
        with patch("signal_vault.unattended_forward_cycle.os.environ",
                   {"ALPACA_LIVE_KEY_ID":"something"}):
            with self.assertRaisesRegex(ValueError,"LIVE credential"):
                load_keychain_paper_data_credentials()

    def test_offline_health_status_reports_last_safe_receipt_without_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward";root.mkdir(mode=0o700)
            self.assertEqual(status_unattended(root=root)["state"],
                             "NO_AUTO_SEGMENT_STARTED")
            bad=tick(root,END,lambda: (_ for _ in ()).throw(
                RuntimeError("do-not-repeat-this-private-value")))
            self.assertEqual(bad["decision"],"HALT_PRESERVE_ALL_ORIGINAL_EVIDENCE")
            idle=status_unattended(root=root)
            self.assertEqual(idle["latest_tick"]["failure_class"],"RuntimeError")
            self.assertNotIn("do-not-repeat-this-private-value",json.dumps(idle))
            tick(root,END+HOUR,SourceFactory().at(END+HOUR))
            ready=status_unattended(root=root)
            self.assertEqual(ready["latest_tick"]["decision"],
                             "FIRST_AUTO_SEGMENT_BOOTSTRAPPED")
            self.assertEqual(ready["prospective_observations_verified"],0)
            self.assertEqual(ready["network_requests"],"NONE")

    def test_duplicate_worker_lock_refuses_without_get(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"forward";root.mkdir(mode=0o700)
            (root/"automation").mkdir(mode=0o700)
            with RuntimeFileLock(root/"automation"/".unattended_cycle.lock"):
                with self.assertRaises(RuntimeAlreadyLocked):
                    tick(root,END,lambda: self.fail("locked collector cannot fetch"))


if __name__=="__main__":
    unittest.main()
