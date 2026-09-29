"""Independently audit PRIVATE historical six-stock IEX ZIP and re-run offline P&L.

Strict bounded ZIP reader: never extracts untrusted member paths, never opens
GitHub/Alpaca, imports account/order executors, accesses secrets, or changes
the original dataset. Independent XNYS calendar read-back is required BEFORE
the first retrospective equity bar is described as exchange-session data.

Matching reported historical after-cost P&L against source data is a
reproducibility check, not a source signature, market-data warranty, proof of
future edge, or authority to buy fractional shares / place stock orders.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
import zipfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Mapping

from .ci_historical_equities import (
    EQUITY_ESTIMATED_COST_SCENARIOS, SYMBOLS,
)
from .equity_session_grid import conservative_core_hour_plan
from .multi_asset_simulation import (
    ExplicitRoundTripCosts, HYPOTHESES,
)
from .offline_multimarket_pipeline import (
    combine_historical_archives, describe_multi_asset_research,
    read_historical_archive,
)
from .research_universe import AssetClass

SOURCE_NAME = re.compile(
    r"historical-us_equity-\d{8}T\d{4}Z-\d{8}T\d{4}Z-[0-9a-f]{16}\.json\Z"
)
REPORT = "offline_equity_research.json"
MAX_ZIP_SIZE = 10_000_000
MAX_MEMBER_SIZE = 4_000_000
MAX_TOTAL_UNCOMPRESSED = 30_000_000
MAX_SESSIONS = 25


def _read_safe_zip(path: Path) -> dict[str, bytes]:
    if (path.is_symlink() or not path.is_file()
            or not 0 < path.stat().st_size <= MAX_ZIP_SIZE):
        raise ValueError("private stock research ZIP missing, unsafe or oversized")
    items: dict[str, bytes] = {}
    with zipfile.ZipFile(path) as z:
        members = z.infolist()
        if (not 2 <= len(members) <= MAX_SESSIONS + 1
                or len({m.filename for m in members}) != len(members)
                or sum(m.file_size for m in members) > MAX_TOTAL_UNCOMPRESSED):
            raise ValueError("stock ZIP contains excess or duplicate data")
        for member in members:
            name = member.filename
            if (member.is_dir() or not name.isascii() or "/" in name or
                    "\\" in name or name.startswith(".") or
                    not 0 < member.file_size <= MAX_MEMBER_SIZE or
                    stat.S_IFMT(member.external_attr >> 16) == stat.S_IFLNK or
                    not (name == REPORT or SOURCE_NAME.fullmatch(name))):
                raise ValueError("stock ZIP member/path is not allowlisted")
            content = z.read(member)
            if len(content) != member.file_size:
                raise ValueError("truncated stock ZIP source")
            items[name] = content
    return items


def _write_exclusive(path: Path, content: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError("offline stock audit destination must not exist")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as target:
        os.fchmod(target.fileno(), 0o600)
        target.write(content)
        target.flush()
        os.fsync(target.fileno())


def audit_equity_history_zip(source_zip: str | Path) -> dict[str, object]:
    """Every advertised XNYS session and six IEX symbols must be reproduced."""
    path = Path(source_zip)
    contents = _read_safe_zip(path)
    if REPORT not in contents:
        raise ValueError("offline stock provider report is missing")
    report = json.loads(contents[REPORT])
    if (not isinstance(report, dict) or
            report.get("kind") !=
                "MANUAL_HISTORICAL_XNYS_IEX_CORE_HOUR_MULTIMARKET_RESEARCH" or
            report.get("schema_version") != 1 or
            report.get("symbols") != list(SYMBOLS) or
            report.get("market") != "us_equity" or
            report.get("feed") != "alpaca_equity_iex" or
            report.get("stock_adjustment") != "all" or
            report.get("broker_order_submission") != "DISABLED" or
            report.get("strategy_validated") is not False or
            report.get("no_claim_to_consolidated_SIP_data") is not True or
            report.get("regular_opening_partial_bucket_omitted") is not True or
            report.get("historical_no_prospective_forward_observations") is not True):
        raise ValueError("invalid historical-only stock report contract")
    provenance = report.get("source_sha256")
    calendar = report.get("exchange_calendar_session_plan")
    if (not isinstance(provenance, list) or
            not 1 <= len(provenance) <= MAX_SESSIONS or
            not isinstance(calendar, dict) or
            calendar.get("kind") !=
                "OFFLINE_MANUAL_XNYS_CORE_HOURLY_IEX_DATA_ONLY_PLAN" or
            calendar.get("feed") != "iex" or
            calendar.get("symbols") != list(SYMBOLS) or
            calendar.get("sip_entitlement_assumed") is not False or
            calendar.get("credentials_accessed") != "NONE" or
            calendar.get("network_requests") != 0):
        raise ValueError("inconsistent stock XNYS session plan")
    names = [obj["filename"] for obj in provenance]
    if (len(set(names)) != len(names) or
            set(contents) != set(names) | {REPORT} or
            not all(isinstance(n, str) and SOURCE_NAME.fullmatch(n)
                    for n in names)):
        raise ValueError("missing, duplicated or unexpected IEX history source")
    for item in provenance:
        digest = item.get("sha256")
        basename = item["filename"]
        if (not isinstance(digest, str) or
                not re.fullmatch(r"[0-9a-f]{64}", digest) or
                hashlib.sha256(contents[basename]).hexdigest() != digest):
            raise ValueError("immutable stock history SHA does not match original manifest")

    # No extraction of arbitrary archive paths: write exact SHA-audited names
    # into an ephemeral private folder, then apply the SAME strict full
    # canonical archive re-reader used in first-party historical capture.
    with tempfile.TemporaryDirectory(prefix="signal-vault-offline-iex-") as directory:
        root = Path(directory)
        root.chmod(0o700)
        for name in names:
            _write_exclusive(root/name, contents[name])
        batches = tuple(read_historical_archive(root/name) for name in names)
        observed_at = max(
            datetime.fromisoformat(x.downloaded_utc).astimezone(timezone.utc)
            for x in batches)
        source_sessions = calendar.get("sessions")
        if (not isinstance(source_sessions, list)
                or len(source_sessions) != len(batches) or
                calendar.get("session_count") != len(batches)):
            raise ValueError("missing independently recorded XNYS session metadata")
        dates = [date.fromisoformat(x["trading_date"]) for x in source_sessions]
        if dates != sorted(set(dates)):
            raise ValueError("stock source market sessions must be chronological")
        independent = conservative_core_hour_plan(
            start_date=dates[0],
            end_date_exclusive=dates[-1] + timedelta(days=1),
            as_of=observed_at)
        if len(independent) != len(source_sessions):
            raise ValueError("XNYS calendar session dates changed")
        for original, derived, bundle in zip(source_sessions, independent, batches):
            again = derived.as_dict()
            # Historical provenance retains the ORIGINAL calendar version.
            # Recomputing with a newer same-major package must produce the
            # same exchange session boundaries and exact conservative bars.
            original_version = original.get("exchange_calendar_package_version")
            if (not isinstance(original_version, str)
                    or not original_version.startswith("4.")):
                raise ValueError("unsupported original XNYS calendar provenance")
            again["exchange_calendar_package_version"] = original_version
            if original != again:
                raise ValueError("exchange market hours/holiday/partial-session mismatch")
            if (bundle.asset_class != AssetClass.US_EQUITY.value or
                    bundle.symbols != tuple(SYMBOLS) or
                    bundle.feed != "alpaca_equity_iex" or
                    bundle.adjustment != "all" or
                    bundle.start_utc != derived.query_start.isoformat() or
                    bundle.end_utc != derived.query_end.isoformat()):
                raise ValueError("source IEX bundle does not match independently verified session")
            for sym in SYMBOLS:
                if (tuple(bar.start_utc for bar in bundle.bars[sym]) !=
                        derived.expected_opens or
                        any(bar.prospective for bar in bundle.bars[sym])):
                    raise ValueError("missing IEX core-hour bar; no interpolation permitted")
        common_grid = tuple(
            stamp for session in independent for stamp in session.expected_opens
        )
        if (not common_grid or len(common_grid) !=
                calendar.get("expected_complete_core_hours_per_symbol")):
            raise ValueError("incomplete stock timestamp grid")
        equities, reviews = combine_historical_archives(
            batches, as_of=observed_at,
            equity_calendars={sym: common_grid for sym in SYMBOLS})

    if report.get("quality_reviews") != reviews:
        raise ValueError("source OHLCV, timestamp or dataset SHA differs from stock report")
    scenario_reports = report.get("three_estimated_cost_scenarios")
    if (not isinstance(scenario_reports, dict)
            or set(scenario_reports) != set(EQUITY_ESTIMATED_COST_SCENARIOS)):
        raise ValueError("expected all three original stock cost assumptions")
    summaries = {}
    fractional_fill_count = 0
    for label, params in EQUITY_ESTIMATED_COST_SCENARIOS.items():
        from_source = scenario_reports[label]
        explicit = {sym:dict(params) for sym in SYMBOLS}
        if (not isinstance(from_source, dict) or
                from_source.get("explicit_assumptions_by_symbol") != explicit or
                from_source.get(
                    "assumptions_are_illustrative_not_measured_IEX_quotes") is not True):
            raise ValueError("stock execution assumptions changed after capture")
        model = ExplicitRoundTripCosts(
            Decimal(params["taker_fee_bps"]),
            Decimal(params["full_spread_bps"]),
            Decimal(params["slippage_per_side_bps"]))
        recalculated = describe_multi_asset_research(
            equities, as_of=observed_at,
            costs={sym:model for sym in SYMBOLS},
            equity_calendars={sym:common_grid for sym in SYMBOLS})
        if recalculated != from_source.get("offline_report"):
            raise ValueError("published after-cost stock result fails source-data replay")
        books = recalculated["all_predeclared_shared_bankroll_research_books"]
        summaries[label] = {
            "assumptions_per_instrument": explicit,
            "fixed_hypothesis_results": {
                version: {
                    "net_pnl_if_hypothetically_liquidated_usd":
                        item["net_pnl_if_hypothetically_liquidated_usd"],
                    "synthetic_fill_count":len(item["synthetic_fills"]),
                    "initial_shared_bankroll_usd":item["initial_bankroll_usd"],
                    "maximum_combined_long_exposure_usd":
                        item["max_total_long_exposure_usd"],
                    "research_risk_gate_semantics_version":
                        item["research_risk_gate_semantics_version"],
                } for version,item in books.items()
            },
        }
        for book in books.values():
            fractional_fill_count += sum(
                1 for fill in book["synthetic_fills"]
                if fill["side"] == "buy" and
                   Decimal(fill["quantity"]) < Decimal("1")
            )
    first_symbol = SYMBOLS[0]
    fold = report["three_estimated_cost_scenarios"][
        "illustrative_base_equity_friction"]["offline_report"][
            "per_asset_chronological_folds"][first_symbol][
                "generic-ema12x26-v1-predeclared"]
    # A 60-bar / ten-session example leaves just 32 post-warmup bars,
    # split 16 / 8 / 8. This must never be advertised as strategy proof.
    fold_note = {
        "development_evaluated_bars": 16,
        "validation_evaluated_bars": 8,
        "untouched_test_evaluated_bars": 8,
        "interpretation": "TOO_SHORT_FOR_STRATEGY_VALIDATION",
    }
    if (len(common_grid) != 60 or len(independent) != 10):
        # Reusable audit still accepts other bounded sets but does not
        # invent fold-size claims for differently sized samples.
        fold_note = {
            "interpretation":"SHORT_EXPLORATORY_DESCRIPTIVE_HISTORY_NOT_STRATEGY_PROOF",
            "fold_start_end_utc": fold,
        }
    return {
        "kind":"INDEPENDENT_OFFLINE_SIX_STOCK_IEX_HISTORY_REPRODUCIBILITY_AUDIT",
        "original_zip_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
        "original_stock_report_sha256":
            hashlib.sha256(contents[REPORT]).hexdigest(),
        "original_session_sha256_by_name":{
            x["filename"]:x["sha256"] for x in provenance},
        "symbols":list(SYMBOLS),
        "feed":"alpaca_equity_iex",
        "regular_core_hourly_bars_per_symbol":len(common_grid),
        "total_historical_asset_hour_records":
            len(common_grid)*len(SYMBOLS),
        "distinct_common_regular_core_utc_opens":
            [t.isoformat() for t in common_grid],
        "calendar_version_in_original":source_sessions[0][
            "exchange_calendar_package_version"],
        "source_archive_SHA_manifest_verified":True,
        "original_dataset_quality_sha_reproduced":True,
        "original_three_cost_scenarios_and_all_four_strategies_reproduced":True,
        "scenario_results":summaries,
        "sample_adequacy":fold_note,
        "fractional_stock_buy_fills_in_hypothetical_books":fractional_fill_count,
        "fractional_share_tradability_or_minimums_not_provider_verified":True,
        "IEX_single_exchange_not_SIP":True,
        "opening_partial_hour_and_extended_hours_excluded":True,
        "all_history_retrospective_prospective_observations_verified":0,
        "execution_costs_are_illustrative_not_observed":True,
        "strategy_selected_on_test_period":False,
        "strategy_promoted":False,
        "external_source_digitally_signed":False,
        "network_requests":"NONE",
        "credentials_accessed":"NONE",
        "broker_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="Offline independent ZIP/source/session/stock-PnL audit; no keys.")
    parser.add_argument("--source-zip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    audited = audit_equity_history_zip(args.source_zip)
    blob = (json.dumps(audited,sort_keys=True,indent=2) + "\n").encode("utf-8")
    _write_exclusive(args.output,blob)
    print(json.dumps({
        "status":"STOCK_IEX_SOURCE_AND_HISTORICAL_MODEL_REPRODUCED",
        "assets":audited["symbols"],
        "source_day_hashes_verified":len(audited["original_session_sha256_by_name"]),
        "rows_per_symbol":audited["regular_core_hourly_bars_per_symbol"],
        "fractional_share_fills_not_execution_certified":
            audited["fractional_stock_buy_fills_in_hypothetical_books"],
        "output_sha256":hashlib.sha256(blob).hexdigest(),
        "network_requests":"NONE",
        "broker_order_submission":"DISABLED",
    },sort_keys=True,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
