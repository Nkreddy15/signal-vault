"""Keyless OFFLINE GitHub historical ZIP -> complete passive-pair attribution.

Standalone, no GitHub API, no Alpaca endpoint, no OAuth, no Keychain, no
Railway usage, no paper/live orders. Rechecks the artifact's historical
source SHA manifest, six-asset per-window continuity, actual fixed
simulation cost scenarios and previously reported passive-basket P&L.

A GitHub Actions artifact is private but its SHA is NOT an external digital
signature. Comparisons here are integrity/repeatability checks, not claims
about brokerage data authenticity, forward returns, alpha or tradability.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
import zipfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Mapping

from .ci_historical_report import ANALYSIS_FILENAME, SCENARIOS, audit_requested_archives
from .ci_replay_history import _manifest_plan
from .multi_asset_simulation import ExplicitRoundTripCosts
from .multi_asset_research_cli import aware
from .offline_multimarket_pipeline import (
    combine_historical_archives, read_historical_archive,
)
from .universe_attribution import all_pair_passive_diagnostics

SOURCE_ARCHIVE_RE = re.compile(
    r"historical-crypto-\d{8}T\d{4}Z-\d{8}T\d{4}Z-[0-9a-f]{16}\.json\Z"
)
RESEARCH_VERSION = "v2_utc_daily_reset_plus_persistent_peak_drawdown_halt"
MAX_ZIP_BYTES = 20_000_000
MAX_TOTAL_UNCOMPRESSED = 50_000_000
MAX_MEMBER_BYTES = 8_000_000


def _exclusive_write(path: Path, content: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError("destination exists; never overwrite research evidence")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as writer:
        os.fchmod(writer.fileno(), 0o600)
        writer.write(content)
        writer.flush()
        os.fsync(writer.fileno())


def _read_bounded_zip(source: Path) -> dict[str, bytes]:
    if (source.is_symlink() or not source.is_file() or
            not 0 < source.stat().st_size <= MAX_ZIP_BYTES):
        raise ValueError("missing, symlinked or oversized research ZIP")
    result: dict[str, bytes] = {}
    with zipfile.ZipFile(source, mode="r") as archive:
        items = archive.infolist()
        if not 3 <= len(items) <= 36 or len({i.filename for i in items}) != len(items):
            raise ValueError("wrong/duplicate research artifact members")
        if sum(i.file_size for i in items) > MAX_TOTAL_UNCOMPRESSED:
            raise ValueError("compressed research artifact claims excessive total data")
        for member in items:
            name = member.filename
            if (member.is_dir() or not name.isascii() or
                    "/" in name or "\\" in name or name.startswith(".") or
                    not 0 < member.file_size <= MAX_MEMBER_BYTES or
                    stat.S_IFMT(member.external_attr >> 16) == stat.S_IFLNK or
                    not (name == ANALYSIS_FILENAME or
                         SOURCE_ARCHIVE_RE.fullmatch(name) or
                         name in {
                             "cost_assumptions-" + case + ".json"
                             for case in SCENARIOS
                         })):
                raise ValueError("unexpected/non-flat/symlinked research ZIP member")
            blob = archive.read(member)
            if len(blob) != member.file_size:
                raise ValueError("truncated ZIP research content")
            result[name] = blob
    return result


def analyze_six_asset_zip(source: str | Path) -> dict[str, object]:
    """No partial result: verify every source BEFORE computing 15 pair baskets."""
    src = Path(source)
    files = _read_bounded_zip(src)
    if ANALYSIS_FILENAME not in files:
        raise ValueError("original SHA-bound offline research report absent")
    report = json.loads(files[ANALYSIS_FILENAME])
    plan = _manifest_plan(report)
    if (len(plan["symbols"]) != 6 or
            report.get("simulation_accounting_version") != RESEARCH_VERSION or
            set(report.get("scenarios", {})) != set(SCENARIOS)):
        raise ValueError("wrong historical report/version or no multi-asset dataset")
    audits = report["historical_archive_audit"]
    expected_history = {a["filename"] for a in audits}
    expected_costs = {"cost_assumptions-" + name + ".json" for name in SCENARIOS}
    if (len(audits) != len(expected_history) or
            set(files) != expected_history | expected_costs | {ANALYSIS_FILENAME}):
        raise ValueError("unknown/missing historical snapshot or cost assumptions")
    for item in audits:
        name, digest = item["filename"], item["sha256"]
        if (not isinstance(name, str) or
                not SOURCE_ARCHIVE_RE.fullmatch(name) or
                not isinstance(digest, str) or
                not re.fullmatch(r"[0-9a-f]{64}", digest) or
                hashlib.sha256(files[name]).hexdigest() != digest):
            raise ValueError("source historical content hash mismatch")
    for label in SCENARIOS:
        declared = report["scenarios"][label]["assumptions_per_instrument"]
        expected = {sym:dict(SCENARIOS[label]) for sym in plan["symbols"]}
        cost_file = json.loads(files["cost_assumptions-" + label + ".json"])
        if declared != expected or cost_file != expected:
            raise ValueError("original cost scenario and source file do not match")

    with tempfile.TemporaryDirectory(prefix="signal-vault-offline-zip-audit-") as folder:
        private = Path(folder)
        os.chmod(private, 0o700)
        for basename in sorted(expected_history):
            _exclusive_write(private/basename, files[basename])
        paths = audit_requested_archives(private, plan=plan)
        batches = tuple(read_historical_archive(path) for path in paths)
        cutoff = max(aware(item.downloaded_utc) for item in batches)
        datasets, quality = combine_historical_archives(
            batches, as_of=cutoff)
    base_quality = report["scenarios"]["illustrative_base_friction"][
        "offline_report"]["asset_quality_reviews"]
    if (set(datasets) != set(plan["symbols"]) or
            {k:v["content_sha256"] for k,v in quality.items()} !=
            {k:v["content_sha256"] for k,v in base_quality.items()}):
        raise ValueError("recovered six-market data differs from original source report")
    scenario_results = {}
    for label in SCENARIOS:
        assumptions = {
            sym: ExplicitRoundTripCosts(
                Decimal(SCENARIOS[label]["taker_fee_bps"]),
                Decimal(SCENARIOS[label]["full_spread_bps"]),
                Decimal(SCENARIOS[label]["slippage_per_side_bps"]),
            ) for sym in plan["symbols"]
        }
        diagnostic = all_pair_passive_diagnostics(
            datasets, as_of=cutoff, costs=assumptions)
        first = diagnostic["all_pair_scenarios"][0]
        original_passive = report["scenarios"][label]["offline_report"][
            "one_SHARED_100_usd_portfolio_by_fixed_hypothesis"][
            "one-allocation-passive-v1-predeclared"][
            "net_pnl_if_hypothetically_liquidated_usd"]
        # Exact-match accounting validates this diagnostic's first nominal
        # basket against the previously published shared-book passive result.
        if (Decimal(first["unrounded_net_pnl_if_liquidated_usd"]) !=
                Decimal(original_passive)):
            raise ValueError("passive pair attribution disagrees with original simulation")
        scenario_results[label] = {
            "assumptions_are_illustrative_not_provider_executions": True,
            "original_alphabetical_passive_PNL_exactly_reconciled": True,
            "all_pair_diagnostic": diagnostic,
        }
    return {
        "kind": "OFFLINE_SIX_CRYPTO_HISTORY_15_PASSIVE_PAIR_AUDIT_NO_ORDERS",
        "source_zip_sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
        "source_research_report_sha256":
            hashlib.sha256(files[ANALYSIS_FILENAME]).hexdigest(),
        "asset_class": "crypto",
        "assets": list(plan["symbols"]),
        "original_historical_archives_sha256": {
            a["filename"]:a["sha256"] for a in audits
        },
        "per_asset_closed_historical_bars": {
            k:len(v) for k,v in datasets.items()},
        "distinct_clock_hours": len(next(iter(datasets.values()))),
        "all_fifteen_pair_alternative_scenarios": scenario_results,
        "previous_passive_comparator_only_allocated_to_first_two_symbols": True,
        "no_six_coin_portfolio_outperformance_claim": True,
        "no_prospective_observations_proven_by_historical_download": True,
        "model_selected_on_test_performance": False,
        "network_requests": "NONE",
        "credential_access": "NONE",
        "broker_order_submission": "DISABLED",
        "live_trading": "UNAVAILABLE",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="OFFLINE SHA-bound 6-crypto artifact basket attribution, no API keys.")
    parser.add_argument("--source-zip", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = analyze_six_asset_zip(args.source_zip)
    blob = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _exclusive_write(args.output, blob)
    print(json.dumps({
        "status": "OFFLINE_ATTRIBUTION_COMPLETE",
        "assets": result["assets"],
        "original_archives_verified":len(result["original_historical_archives_sha256"]),
        "alternatives_per_scenario":len(
            next(iter(result["all_fifteen_pair_alternative_scenarios"].values()))
            ["all_pair_diagnostic"]["all_pair_scenarios"]),
        "output_basename":args.output.name,
        "output_sha256": hashlib.sha256(blob).hexdigest(),
        "historical_only": True,
        "network_requests": "NONE",
        "broker_order_submission": "DISABLED",
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
