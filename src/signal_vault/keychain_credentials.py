"""macOS Keychain-backed PAPER DATA credential access for unattended GET-only capture.

Secrets are never accepted through CLI arguments, environment variables,
files, logs, Git, or JSON configuration. Activation asks macOS' own `security`
tool to prompt interactively, then the unattended worker retrieves values by
service/account label. This module has no broker trading/order endpoint.
"""
from __future__ import annotations

import platform
import subprocess

from .paper_credentials import PaperCredentials

KEYCHAIN_ACCOUNT = "signal-vault"
KEY_ID_SERVICE = "com.signalvault.alpaca.paper-data-key-id"
SECRET_SERVICE = "com.signalvault.alpaca.paper-data-secret"


def _require_macos() -> None:
    if platform.system() != "Darwin":
        raise RuntimeError("macOS Keychain integration is available only on macOS")


def _read_item(service: str, *, account: str = KEYCHAIN_ACCOUNT) -> str:
    _require_macos()
    completed = subprocess.run(
        ["security", "find-generic-password", "-w", "-a", account, "-s", service],
        check=False, capture_output=True, text=True, timeout=15,
    )
    if completed.returncode != 0:
        raise RuntimeError("required Signal Vault PAPER DATA credential is missing from macOS Keychain")
    value = completed.stdout.rstrip("\r\n")
    if not value:
        raise RuntimeError("Signal Vault Keychain credential is empty")
    return value


def load_paper_data_credentials() -> PaperCredentials:
    """Read the two dedicated values; return redacting credential object."""
    return PaperCredentials(_read_item(KEY_ID_SERVICE), _read_item(SECRET_SERVICE))


def store_interactively() -> None:
    """Ask Apple's security CLI to prompt, never pass secret values in argv.

    Omitting -w's password operand makes /usr/bin/security request password
    data interactively. -U updates an existing matching service/account item.
    """
    _require_macos()
    prompts = (
        (KEY_ID_SERVICE, "Alpaca PAPER DATA key ID"),
        (SECRET_SERVICE, "Alpaca PAPER DATA secret"),
    )
    for service, label in prompts:
        print(f"macOS Keychain will securely prompt for: {label}")
        completed = subprocess.run(
            ["security", "add-generic-password", "-U", "-a", KEYCHAIN_ACCOUNT,
             "-s", service, "-T", "/usr/bin/security"],
            check=False, timeout=120,
        )
        if completed.returncode != 0:
            raise RuntimeError("macOS Keychain did not save the requested Signal Vault credential")
    # Read once immediately so activation cannot install a schedule with broken items.
    load_paper_data_credentials()


def delete_items() -> None:
    """Best-effort explicit cleanup; never called during ordinary deactivation."""
    _require_macos()
    for service in (KEY_ID_SERVICE, SECRET_SERVICE):
        subprocess.run(
            ["security", "delete-generic-password", "-a", KEYCHAIN_ACCOUNT, "-s", service],
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15,
        )
