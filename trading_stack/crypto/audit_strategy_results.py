"""Read existing reports; attribute recorded results without replaying or orders."""
import argparse
import json
from collections import Counter
from pathlib import Path
import numpy as np


def audit(directory):
    root = Path(directory)
    source = root/"multi-strategy-summary.json"
    if not source.exists():
        return dict(status="NO_EXISTING_REPORT", reports=[], note="No results were invented.")
    summary = json.loads(source.read_text())
    rows = []
    for row in summary["reports"]:
        path = root/(row["name"]+".json")
        detail = json.loads(path.read_text()) if path.exists() else None
        trades = detail["trades"] if detail else None
        gross = sum(t["gross_pnl"] for t in trades) if trades is not None else None
        fees = row["fees"]
        carry, operating = row.get("short_carry", 0), row.get("operating_cost_usd", 0)
        reconciled = None if gross is None else abs(gross-fees-carry-operating-row["realized_pnl"]) < 1e-7
        if row.get("pending_positions"):
            reconciled = None  # realized and unrealized costs cannot be conflated
        rows.append(dict(name=row["name"], trades=row["trades"], ending_equity=row["ending_equity"],
            net_realized_pnl=row["realized_pnl"], recorded_fill_gross_pnl=gross,
            fees=fees, short_carry=carry, operating_cost=operating,
            pnl_before_fees_and_carry_on_recorded_path=row["realized_pnl"]+fees+carry+operating,
            reconciliation_pass=reconciled, details_available=detail is not None,
            exit_reasons=dict(Counter(t["reason"] for t in trades)) if trades is not None else None,
            median_hold_hours=float(np.median([(t["exit_ms"]-t["entry_ms"])/3_600_000 for t in trades])) if trades else None))
    return dict(status="EXISTING_RESULTS_AUDIT", reports=rows,
        benchmarks=summary.get("buy_and_hold_baselines"),
        selectors=summary.get("past_month_selectors"),
        caveats=["Adding costs back to recorded fills is attribution, not a zero-cost backtest: removing costs changes sizing, tiers and halts.",
                 "Recorded-fill gross already includes modeled bid/ask and slippage."])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    result = audit(args.results_dir)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out/"prior-strategy-audit.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    lines = ["# Recorded strategy cost audit", "", result["status"], "",
        "| Configuration | Recorded-fill gross | Fees | Carry | Net realized | Reconciles |",
        "|---|---:|---:|---:|---:|---|"]
    for r in result["reports"]:
        gross = "n/a" if r["recorded_fill_gross_pnl"] is None else f"${r['recorded_fill_gross_pnl']:.2f}"
        lines.append(f"| {r['name']} | {gross} | ${r['fees']:.2f} | ${r['short_carry']:.2f} | ${r['net_realized_pnl']:.2f} | {r['reconciliation_pass']} |")
    lines.extend(["", "## Existing buy-and-hold benchmarks", "", "```json", json.dumps(result.get("benchmarks"), indent=2), "```",
        "", "## Existing past-month selectors", "", "| Selector | End equity | Trades | Max DD |", "|---|---:|---:|---:|"])
    for r in result.get("selectors") or []:
        lines.append(f"| {r['name']} | ${r['ending_equity']:.2f} | {r['trades']} | {r['max_drawdown_pct']:.2f}% |")
    lines.extend(["", *(result.get("caveats") or [])])
    (out/"prior-strategy-audit.md").write_text("\n".join(lines)+"\n")
    print(f"Read {len(result['reports'])} existing configurations. Saved attribution and benchmarks.", flush=True)


if __name__ == "__main__":
    main()
