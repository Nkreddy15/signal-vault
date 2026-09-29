"""Offline plist construction / explicit-install tests; never invoke real launchctl/Keychain."""
import os
import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from signal_vault.mac_forward_agent import (
    LABEL, agent_configuration, agent_path, agent_status, install_agent,
    uninstall_agent,
)


def dummy_checkout(tmp):
    repo=Path(tmp)/"signal-vault"
    module=repo/"src"/"signal_vault"/"unattended_forward_cycle.py"
    module.parent.mkdir(parents=True)
    module.write_text("# fake code location")
    python=repo/".venv"/"bin"/"python"
    python.parent.mkdir(parents=True)
    python.write_text("#! fake interpreter")
    python.chmod(0o700)
    home=Path(tmp)/"home"
    home.mkdir()
    (repo/"data"/"forward").mkdir(parents=True)
    return repo,python,home


class MacAgentTests(unittest.TestCase):
    def test_hourly_calendar_plist_no_secrets_no_run_at_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo,python,home=dummy_checkout(tmp)
            data=agent_configuration(repo=repo,home=home,python_bin=python)
            self.assertEqual(data["Label"],LABEL)
            self.assertEqual(data["StartCalendarInterval"],{"Minute":7})
            self.assertFalse(data["RunAtLoad"])
            self.assertFalse(data["KeepAlive"])
            self.assertEqual(data["Umask"],0o077)
            self.assertEqual(data["ProgramArguments"],
                             [str(python),"-m","signal_vault.unattended_forward_cycle","--once"])
            self.assertEqual(data["EnvironmentVariables"],{"PYTHONPATH":str(repo/"src")})
            encoded=plistlib.dumps(data)
            self.assertEqual(plistlib.loads(encoded),data)
            for token in (b"local-key-id",b"local-secret",b"APCA-API",b"ALPACA_SECRET"):
                self.assertNotIn(token,encoded)

    def test_install_is_explicit_keychain_prechecked_and_no_auto_run_at_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo,python,home=dummy_checkout(tmp)
            invocations=[]
            with patch("signal_vault.mac_forward_agent._mac_only"),patch(
                    "signal_vault.mac_forward_agent.load_keychain_paper_data_credentials",
                    return_value=object()) as creds,patch(
                    "signal_vault.mac_forward_agent._launchctl",
                    side_effect=lambda *args: invocations.append(args) or True):
                response=install_agent(repo=repo,home=home,python_bin=python)
            self.assertTrue(response["launch_agent_loaded"])
            self.assertFalse(response["credentials_in_plist"])
            self.assertEqual(response["first_run"],"NEXT_MAC_LOCAL_CLOCK_MINUTE_07_NOT_IMMEDIATE")
            creds.assert_called_once()
            self.assertEqual(len(invocations),1)
            self.assertEqual(invocations[0][0],"bootstrap")
            path=agent_path(home)
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            self.assertEqual(plistlib.loads(path.read_bytes())["StartCalendarInterval"]["Minute"],7)
            self.assertFalse(plistlib.loads(path.read_bytes())["RunAtLoad"])
            self.assertTrue((repo/"data"/"forward"/"automation").is_dir())
            self.assertEqual((repo/"data"/"forward"/"automation").stat().st_mode & 0o777,0o700)
            with patch("signal_vault.mac_forward_agent._mac_only"),patch(
                    "signal_vault.mac_forward_agent.load_keychain_paper_data_credentials",
                    side_effect=AssertionError("must not query Keychain on duplicate")):
                with self.assertRaises(FileExistsError):
                    install_agent(repo=repo,home=home,python_bin=python)

    def test_missing_or_locked_keychain_blocks_creation_without_schedule(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo,python,home=dummy_checkout(tmp)
            with patch("signal_vault.mac_forward_agent._mac_only"),patch(
                    "signal_vault.mac_forward_agent.load_keychain_paper_data_credentials",
                    side_effect=RuntimeError("unavailable")),patch(
                    "signal_vault.mac_forward_agent._launchctl") as launch:
                with self.assertRaisesRegex(RuntimeError,"unavailable"):
                    install_agent(repo=repo,home=home,python_bin=python)
                launch.assert_not_called()
                self.assertFalse(agent_path(home).exists())

    def test_no_corrupted_python_or_outside_project_interpreter(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo,python,home=dummy_checkout(tmp)
            with self.assertRaisesRegex(ValueError,".venv/bin/python"):
                agent_configuration(repo=repo,home=home,python_bin=Path(tmp)/"other-python")
            python.unlink()
            with self.assertRaisesRegex(ValueError,".venv/bin/python"):
                agent_configuration(repo=repo,home=home,python_bin=python)

    def test_uninstall_only_after_matching_label_and_stop_preserves_data_keychain(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo,python,home=dummy_checkout(tmp)
            with patch("signal_vault.mac_forward_agent._mac_only"),patch(
                "signal_vault.mac_forward_agent.load_keychain_paper_data_credentials",
                return_value=object()),patch("signal_vault.mac_forward_agent._launchctl",return_value=True):
                install_agent(repo=repo,home=home,python_bin=python)
            active=["bootout","print"]
            def action(*args):
                invoked=active.pop(0)
                assert args[0]==invoked
                return invoked=="bootout"
            with patch("signal_vault.mac_forward_agent._mac_only"),patch(
                "signal_vault.mac_forward_agent._launchctl",side_effect=action),patch(
                "signal_vault.mac_forward_agent.load_keychain_paper_data_credentials",
                side_effect=AssertionError("no reason to fetch credentials for uninstall")):
                result=uninstall_agent(home=home)
            self.assertTrue(result["plist_removed"])
            self.assertFalse(agent_path(home).exists())
            self.assertTrue((repo/"data"/"forward"/"automation").exists())
            self.assertTrue(result["original_observations_and_backups_preserved"])
            self.assertTrue(result["keychain_items_unchanged"])

    def test_wrong_label_or_still_loaded_never_removes_plist(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo,python,home=dummy_checkout(tmp)
            with patch("signal_vault.mac_forward_agent._mac_only"),patch(
                "signal_vault.mac_forward_agent.load_keychain_paper_data_credentials",
                return_value=object()),patch("signal_vault.mac_forward_agent._launchctl",return_value=True):
                install_agent(repo=repo,home=home,python_bin=python)
            path=agent_path(home)
            data=plistlib.loads(path.read_bytes())
            data["Label"]="not-the-same-service"
            path.write_bytes(plistlib.dumps(data))
            with patch("signal_vault.mac_forward_agent._mac_only"),patch(
                "signal_vault.mac_forward_agent._launchctl") as launch:
                with self.assertRaisesRegex(ValueError,"unexpected"):
                    uninstall_agent(home=home)
                launch.assert_not_called()
                self.assertTrue(path.exists())
            data["Label"]=LABEL
            path.write_bytes(plistlib.dumps(data))
            with patch("signal_vault.mac_forward_agent._mac_only"),patch(
                "signal_vault.mac_forward_agent._launchctl",return_value=True):
                with self.assertRaisesRegex(RuntimeError,"still loaded"):
                    uninstall_agent(home=home)
                self.assertTrue(path.exists())

    def test_status_does_not_request_creds_or_touch_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            _,_,home=dummy_checkout(tmp)
            with patch("signal_vault.mac_forward_agent._mac_only"),patch(
                "signal_vault.mac_forward_agent._launchctl",return_value=False),patch(
                "signal_vault.mac_forward_agent.load_keychain_paper_data_credentials",
                side_effect=AssertionError("status must not call Keychain")):
                status=agent_status(home=home)
            self.assertFalse(status["plist_exists"])
            self.assertFalse(status["launch_agent_loaded"])
            self.assertEqual(status["broker_order_submission"],"DISABLED")


if __name__=="__main__":
    unittest.main()
