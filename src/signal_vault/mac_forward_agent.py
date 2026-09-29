"""Explicit one-time macOS per-user LaunchAgent activation for GET-only observations.

The plist contains no PAPER credentials, secrets, API URLs, shell scripts,
network requests or permissions to trade. Owner must add two generic-password
Keychain items interactively BEFORE an explicit --install command.
Nothing is installed, activated, charged or scheduled by importing this module.
"""
from __future__ import annotations

import argparse
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path

from .unattended_forward_cycle import (
    ACCOUNT, SERVICE_ID, SERVICE_SECRET, _private_automation_dir,
    load_keychain_paper_data_credentials,
)

LABEL = "com.signalvault.forwardobserver"
MINUTE = 7


def project_root() -> Path:
    """Only use the directory containing this source; never guess a user path."""
    return Path(__file__).absolute().parents[2]


def agent_path(home: str | Path) -> Path:
    return Path(home).expanduser()/"Library"/"LaunchAgents"/(LABEL+".plist")


def _validate_repo(repo: Path, python_bin: Path) -> tuple[Path, Path]:
    if repo.is_symlink() or not repo.is_dir():
        raise ValueError("repository must be a real local folder")
    repo = repo.resolve()
    if not (repo/"src"/"signal_vault"/"unattended_forward_cycle.py").is_file():
        raise ValueError("checked-out Signal Vault source is missing")
    if python_bin.is_symlink() and not python_bin.is_file():
        raise ValueError("Python venv interpreter symlink is broken")
    intended = repo/".venv"/"bin"/"python"
    if (not intended.is_file() or python_bin.absolute() != intended.absolute()):
        raise ValueError("install must use this project's .venv/bin/python (activate .venv first)")
    return repo, intended


def agent_configuration(*, repo: Path, home: Path, python_bin: Path) -> dict:
    """Portable, deterministic plist construction, independently unit tested."""
    repo, executable = _validate_repo(repo, python_bin)
    output = repo/"data"/"forward"/"automation"
    return {
        "Label": LABEL,
        "ProgramArguments": [
            str(executable), "-m", "signal_vault.unattended_forward_cycle", "--once",
        ],
        "WorkingDirectory": str(repo),
        "EnvironmentVariables": {"PYTHONPATH": str(repo/"src")},
        "StartCalendarInterval": {"Minute": MINUTE},
        "RunAtLoad": False,
        "KeepAlive": False,
        "ProcessType": "Background",
        "Umask": 0o077,
        "StandardOutPath": str(output/"launch-agent.out.log"),
        "StandardErrorPath": str(output/"launch-agent.err.log"),
    }


def _mac_only() -> None:
    if sys.platform != "darwin" or not Path("/usr/bin/launchctl").is_file():
        raise RuntimeError("this activation command can run only in a macOS user session")


def _launchctl(*args: str) -> bool:
    # No password, token, shell expansion or secret-bearing environment args.
    result = subprocess.run(["/usr/bin/launchctl", *args],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            timeout=15, check=False)
    return result.returncode == 0


def _agent_folder(home: Path) -> Path:
    folder = home/"Library"/"LaunchAgents"
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        raise ValueError("LaunchAgents must be an actual directory, not a symlink")
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    return folder


def install_agent(*, repo: Path | None = None,
                  home: Path | None = None,
                  python_bin: Path | None = None) -> dict:
    """Only this EXPLICIT operator command installs + activates a user agent."""
    _mac_only()
    source = project_root() if repo is None else Path(repo)
    userhome = Path.home() if home is None else Path(home)
    interpreter = Path(sys.executable) if python_bin is None else Path(python_bin)
    data = agent_configuration(repo=source, home=userhome, python_bin=interpreter)
    target = agent_path(userhome)
    if target.exists() or target.is_symlink():
        raise FileExistsError("LaunchAgent already exists; inspect before any reinstallation")
    # Verify both local Keychain items are actually accessible and well-formed.
    # Never echo, write to plist, transmit, or log credential contents.
    load_keychain_paper_data_credentials()
    _private_automation_dir(source/"data"/"forward")
    _agent_folder(userhome)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os,"O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(target, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(),0o600)
            plistlib.dump(data, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    domain = "gui/"+str(os.getuid())
    loaded = _launchctl("bootstrap", domain, str(target))
    return {
        "kind": "EXPLICIT_USER_MAC_GET_ONLY_LAUNCH_AGENT_INSTALL",
        "installed_plist_path": str(target),
        "launch_agent_loaded": loaded,
        "first_run": "NEXT_MAC_LOCAL_CLOCK_MINUTE_07_NOT_IMMEDIATE",
        "runs_every_hour_minute": MINUTE,
        "credentials_location": "OWNER_MACOS_KEYCHAIN_ONLY",
        "credentials_in_plist": False,
        "broker_order_submission": "DISABLED",
        "automatic_paper_orders": "DISABLED",
        "warning": ("User must remain logged in; sleep/shutdown/locked Keychain can skip a cycle. "
                    "If launchctl bootstrap failed, do not claim activation; inspect local macOS job permissions."),
    }


def agent_status(*, home: Path | None = None) -> dict:
    _mac_only()
    userhome = Path.home() if home is None else Path(home)
    target = agent_path(userhome)
    if target.is_symlink():
        raise ValueError("LaunchAgent path cannot be a symbolic link")
    loaded = _launchctl("print", "gui/"+str(os.getuid())+"/"+LABEL)
    return {
        "kind": "LOCAL_MAC_GET_ONLY_LAUNCH_AGENT_STATUS",
        "plist_exists": target.is_file(),
        "launch_agent_loaded": loaded,
        "runs_every_hour_minute": MINUTE,
        "broker_order_submission": "DISABLED",
        "note": "A loaded LaunchAgent alone does not prove successful provider capture; inspect offline receipts.",
    }


def uninstall_agent(*, home: Path | None = None) -> dict:
    """Operator-only disable; preserves archived source, active segments and Keychain."""
    _mac_only()
    userhome = Path.home() if home is None else Path(home)
    target = agent_path(userhome)
    if target.is_symlink():
        raise ValueError("refusing a symlinked LaunchAgent path")
    if not target.is_file():
        raise FileNotFoundError("no installed Signal Vault LaunchAgent at expected path")
    if target.stat().st_mode & 0o077:
        raise PermissionError("LaunchAgent file is not owner-only")
    with target.open("rb") as stream:
        data = plistlib.load(stream)
    if data.get("Label") != LABEL:
        raise ValueError("unexpected LaunchAgent label; refusing to delete")
    domain = "gui/"+str(os.getuid())
    _launchctl("bootout", domain+"/"+LABEL)
    if _launchctl("print", domain+"/"+LABEL):
        raise RuntimeError("LaunchAgent still loaded; refusing to remove installed plist")
    target.unlink()
    return {
        "kind": "EXPLICIT_USER_MAC_GET_ONLY_LAUNCH_AGENT_DISABLED",
        "launch_agent_loaded": False,
        "plist_removed": True,
        "original_observations_and_backups_preserved": True,
        "keychain_items_unchanged": True,
        "broker_order_submission": "DISABLED",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="One-time USER macOS launchd setup for read-only BTC/USD observation only")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preview", action="store_true", help="Display sanitized scheduling facts, no changes.")
    group.add_argument("--install", action="store_true", help="Explicitly install and activate the local per-user LaunchAgent.")
    group.add_argument("--status", action="store_true", help="Inspect local user LaunchAgent status, no credentials.")
    group.add_argument("--uninstall", action="store_true", help="Stop and remove the LaunchAgent, preserve all saved data.")
    args = parser.parse_args()
    try:
        if args.preview:
            result = {
                "kind": "LOCAL_LAUNCH_AGENT_PREVIEW_NO_INSTALL",
                "label": LABEL,
                "schedule": "EVERY_HOUR_AT_LOCAL_MINUTE_07",
                "run_at_load": False,
                "broker_order_submission": "DISABLED",
                "keychain_services_to_configure_interACTIVELY": [SERVICE_ID, SERVICE_SECRET],
                "keychain_account": ACCOUNT,
                "plist_contains_secrets": False,
                "authorization": "NEEDS_EXPLICIT_LOCAL_OWNER_INSTALL",
            }
        elif args.install:
            result = install_agent()
        elif args.status:
            result = agent_status()
        else:
            result = uninstall_agent()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        # A Keychain/launchctl exception must never leak values from stdout.
        result = {
            "kind": "LOCAL_LAUNCH_AGENT_ACTIVATION_BLOCKED",
            "reason_class": type(exc).__name__,
            "broker_order_submission": "DISABLED",
            "note": "Inspect local Keychain access, repo .venv and launchctl service state; no credentials belong in chat or logs.",
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if args.install and not result.get("launch_agent_loaded",False) else 0


if __name__ == "__main__":
    raise SystemExit(main())
