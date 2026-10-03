"""Purged monthly forecasting research; no profit ceiling and no activation.

Forecasts estimate single-trade after-cost barrier payoffs. All preprocessing,
model fitting and threshold calibration precede the tested calendar month.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

import multi_strategy_lab as m

VERSION = "FORECAST-EDGE-LAB-1.1"
ARRANGEMENTS = ("forecast_ridge", "forecast_boosted", "forecast_consensus")
FEATURES = ("r4", "r16", "r96", "r288", "atr", "adx", "rsi", "ema_gap",
    "distance200", "z96", "volume", "hour_sin", "hour_cos")
HOLD = 192
MILESTONES = (250, 500, 1000, 2500, 5000, 10000)
LIMITS = [
    "No profit ceiling: milestones are measurements. Stops, targets, time exits and drawdown triggers still govern individual positions.",
    "Q1/Q2 are reused development archives. Chronological folds do not turn reused data into unseen validation.",
    "Forecast labels are independent single-trade trigger payoffs; portfolio cash limits and halts can change actual exits.",
    "Hourly decision rows have overlapping 48h labels. Calibration thins each asset's selected events to nonoverlapping horizons; cross-asset dependence remains.",
    "Four fixed threshold choices are calibrated on past data. Model and threshold selection can still overfit.",
    "Alpaca rate sensitivity applies its published taker rates to Kraken candles and simplified cash-fee accounting. It does not validate Alpaca quotes, fills, credited-asset fee accounting, or asset eligibility.",
    "Universe liquidity is measured before testing; published archive coverage can still have survivorship omissions.",
    "Trigger and extrema fills approximate intrabar execution. Missing data and adverse gaps can exceed risk triggers.",
    "Long-only, full cash collateral, no leverage. This release sends no orders and preserves paused paper state.",
]


def engineered(raw):
    f = m.features(raw)
    block = (f.ts.diff().fillna(m.BAR) != m.BAR).cumsum()
    f["r4"] = f.groupby(block).close.pct_change(4, fill_method=None)
    f["r16"], f["r96"] = f.ret16, f.ret96
    f["r288"] = f.groupby(block).close.pct_change(288, fill_method=None)
    f["ema_gap"] = f.ema60/f.ema200-1
    f["distance200"] = f.close/f.ema200-1
    f["actual_volume"] = f.volume
    f["volume"] = np.log1p(f.vol_ratio)
    angle = 2*np.pi*(f.ts % m.DAY)/m.DAY
    f["hour_sin"], f["hour_cos"] = np.sin(angle), np.cos(angle)
    f["stop"] = (3*f.atr).clip(lower=.02, upper=.08)
    f["target"] = (3*f.stop).clip(lower=.06, upper=.24)
    return f


def barrier_labels(f, fee_rate, hold=HOLD, spread_bps=15, slippage=.001):
    """Fixed-stop/target long labels, including entry and actual exit notionals.

    Worst-case label availability is the time-exit opening quote. A label never
    crosses a missing candle. Vectorization uses bounded chunks, not a huge
    all-universe future-price matrix.
    """
    result = np.full(len(f), np.nan)
    available = np.full(len(f), np.nan)
    if len(f) <= hold+1:
        return result, available
    ts, opening, high, low = [f[c].to_numpy(dtype=float) for c in ("ts", "open", "high", "low")]
    indices = np.arange(len(f)-hold-1)
    indices = indices[(ts[indices] % (4*m.BAR) == 3*m.BAR) &
        (ts[indices+hold+1]-ts[indices] == (hold+1)*m.BAR)]
    drift = np.abs(opening[indices+1]/f.close.to_numpy()[indices]-1)
    indices = indices[drift <= np.maximum(.01, 3*f.atr.to_numpy()[indices])+1e-12]
    stop_pct, target_pct = f.stop.to_numpy(), f.target.to_numpy()
    bid_factor = 1-spread_bps/20_000
    for begin in range(0, len(indices), 512):
        idx = indices[begin:begin+512]
        future = idx[:, None]+1+np.arange(hold)
        entry = opening[idx+1]*(1+spread_bps/20_000)*(1+slippage)
        stop, target = entry*(1-stop_pct[idx]), entry*(1+target_pct[idx])
        stop_hits = low[future]*bid_factor <= stop[:, None]
        target_hits = high[future]*bid_factor >= target[:, None]
        hit = stop_hits | target_hits
        touched = hit.any(axis=1)
        first = hit.argmax(axis=1)
        row = np.arange(len(idx))
        first_open = opening[future[row, first]]*bid_factor
        gap_stop, gap_target = first_open <= stop, first_open >= target
        chosen = np.where(gap_stop, first_open, np.where(gap_target, first_open,
            np.where(stop_hits[row, first], stop, target)))
        raw_exit = np.where(touched, chosen, opening[idx+hold+1]*bid_factor)
        exit_fill = raw_exit*(1-slippage)
        ratio = exit_fill/entry
        result[idx] = ratio-1-fee_rate*(1+ratio)
        available[idx] = ts[idx+hold+1]
    return result, available


def pooled_table(frames, fee_profile, formation_end, hold=HOLD):
    parts, prepared = [], {}
    rate = m.FEE_PROFILES[fee_profile][0][1]
    for pair, raw in frames.items():
        f = engineered(raw)
        prepared[pair] = f
        y, label_end = barrier_labels(f, rate, hold)
        f["y"], f["label_end_ms"], f["pair"] = y, label_end, pair
        good = ((f.age >= 300) & (f.ts >= formation_end) &
            (f.ts % (4*m.BAR) == 3*m.BAR) & f.atr.between(.0007, .04) & (f.actual_volume > 0))
        good &= np.isfinite(f[list(FEATURES)].to_numpy(dtype=float)).all(axis=1)
        parts.append(f.loc[good, ["pair", "ts", "close", "atr", "stop", "target", "y", "label_end_ms", *FEATURES]])
    table = pd.concat(parts, ignore_index=True).sort_values(["ts", "pair"]).reset_index(drop=True)
    # 'atr' is both a price-control field and feature: keep one column.
    table = table.loc[:, ~table.columns.duplicated()].copy()
    return table, prepared


def purged_splits(table, test_start, validation_days=14):
    validation_start = test_start-validation_days*m.DAY
    train = table[(table.label_end_ms < validation_start) &
        (table.ts >= test_start-90*m.DAY) & table.y.notna()]
    validation = table[(table.ts >= validation_start) &
        (table.label_end_ms < test_start) & table.y.notna()]
    return train, validation, validation_start


def distribution(values):
    """Descriptive values, not a portfolio return or independent sample count."""
    values = np.asarray(values, dtype=float)
    finite = values[np.isfinite(values)]
    if not len(finite):
        return dict(rows=len(values), finite_rows=0, positive_rows=0,
            mean=None, minimum=None, p05=None, median=None, p95=None, maximum=None)
    return dict(rows=len(values), finite_rows=len(finite), positive_rows=int((finite > 0).sum()),
        mean=float(finite.mean()), minimum=float(finite.min()),
        p05=float(np.quantile(finite, .05)), median=float(np.median(finite)),
        p95=float(np.quantile(finite, .95)), maximum=float(finite.max()))


def calibration_details(validation, predictions, hold=HOLD, min_events=30):
    """Retain every fixed threshold and the exact reasons for rejecting it."""
    if len(validation) != len(predictions):
        raise ValueError("Calibration rows and predictions must align")
    candidates, records = [], []
    for threshold in (.003, .006, .01, .02):
        chosen, by_asset = [], {}
        next_allowed, raw_events = {}, 0
        for pair, ts, y, pred in zip(validation.pair, validation.ts, validation.y, predictions):
            if not np.isfinite(pred) or not np.isfinite(y) or pred < threshold:
                continue
            raw_events += 1
            if ts < next_allowed.get(pair, -1):
                continue
            chosen.append(float(y))
            by_asset[pair] = by_asset.get(pair, 0)+1
            next_allowed[pair] = ts+(hold+1)*m.BAR
        profit, loss = sum(x for x in chosen if x > 0), -sum(x for x in chosen if x < 0)
        factor = profit/loss if loss else None
        mean = float(np.mean(chosen)) if chosen else None
        record = dict(threshold=threshold, nonoverlapping_asset_events=len(chosen),
            mean_net_return=mean, profit_factor=factor)
        reasons = []
        if not raw_events:
            reasons.append("NO_PREDICTIONS_ABOVE_THRESHOLD")
        if len(chosen) < min_events:
            reasons.append("TOO_FEW_NONOVERLAPPING_EVENTS")
        if mean is None:
            reasons.append("NO_COMPLETED_SELECTED_OUTCOMES")
        elif mean < .003:
            reasons.append("MEAN_NET_RETURN_BELOW_0.3_PERCENT")
        if loss and factor < 1.1:
            reasons.append("PROFIT_FACTOR_BELOW_1.1")
        passed = not reasons
        records.append(dict(**record, raw_events=raw_events, asset_events=by_asset,
            accepted=passed, rejection_reasons=reasons))
        if passed:
            candidates.append(record)
    return dict(selection=max(candidates, key=lambda r:r["mean_net_return"]) if candidates else None,
        thresholds=records, prediction_distribution=distribution(predictions),
        minimum_events=min_events,
        overlap_note="Events are spaced within each asset. Cross-asset dependence remains.")


def calibration(validation, predictions, hold=HOLD, min_events=30):
    """Backward-compatible selection; diagnostics do not relax any threshold."""
    return calibration_details(validation, predictions, hold, min_events)["selection"]


def predictive_diagnostics(actual, predicted, training_mean):
    actual, predicted = np.asarray(actual, float), np.asarray(predicted, float)
    mse = float(np.mean((actual-predicted)**2))
    baseline = float(np.mean((actual-training_mean)**2))
    return dict(actual_distribution=distribution(actual),
        predicted_distribution=distribution(predicted), mean_absolute_error=float(np.mean(np.abs(actual-predicted))),
        mse=mse, past_training_mean_baseline_mse=baseline,
        mse_skill_vs_past_mean=None if not baseline else 1-mse/baseline,
        note="Earlier calibration outcomes only; overlapping labels are not independent portfolio trades.")


def monthly_predictions(frames, fee_profile, formation_end, progress=None,
        min_train=500, min_events=30, hold=HOLD):
    table, prepared = pooled_table(frames, fee_profile, formation_end, hold)
    if table.empty:
        raise ValueError("No usable hourly forecast rows")
    first = pd.Timestamp(int(table.ts.min()), unit="ms", tz="UTC")
    cursor = pd.Timestamp(year=first.year, month=first.month, day=1, tz="UTC")+pd.offsets.MonthBegin(1)
    end = max(int(f.ts.iloc[-1])+m.BAR for f in prepared.values())
    signals = {family:{} for family in ARRANGEMENTS}
    folds = []
    while cursor.value//1_000_000 < end:
        start = int(cursor.value//1_000_000)
        following = cursor+pd.offsets.MonthBegin(1)
        finish = min(end, int(following.value//1_000_000))
        train, validation, val_start = purged_splits(table, start)
        test = table[(table.ts >= start) & (table.ts < finish)]
        receipt = dict(month=cursor.strftime("%Y-%m"), test_start_ms=start, test_end_ms=finish,
            train_rows=len(train), calibration_rows=len(validation), test_rows=len(test),
            validation_start_ms=val_start, fee_profile=fee_profile)
        insufficient = []
        if len(train) < min_train:
            insufficient.append("TRAINING_ROWS_BELOW_MINIMUM")
        if len(validation) < 100:
            insufficient.append("CALIBRATION_ROWS_BELOW_100")
        if train.empty or train.ts.max()-train.ts.min() < 14*m.DAY:
            insufficient.append("TRAINING_HISTORY_SPANS_LESS_THAN_14_DAYS")
        if test.empty:
            insufficient.append("NO_USABLE_TEST_ROWS")
        if insufficient:
            receipt["status"] = "INSUFFICIENT_PAST_DATA"
            receipt["insufficient_history_reasons"] = insufficient
            folds.append(receipt)
            cursor = following
            continue
        assert train.label_end_ms.max() < val_start
        assert validation.label_end_ms.max() < start
        receipt.update(train_max_label_end_ms=int(train.label_end_ms.max()),
            calibration_max_label_end_ms=int(validation.label_end_ms.max()), status="PAST_ONLY_FIT")
        receipt["training_label_distribution"] = distribution(train.y)
        hashed = pd.util.hash_pandas_object(train[["pair", "ts", "y", *FEATURES]], index=False).to_numpy().tobytes()
        receipt["training_data_sha256"] = hashlib.sha256(hashed).hexdigest()
        if progress:
            progress(f"{fee_profile}: train/calibrate before {receipt['month']}; {len(train):,} train rows")
        models = {
            "forecast_ridge":make_pipeline(StandardScaler(), Ridge(alpha=100)),
            "forecast_boosted":HistGradientBoostingRegressor(max_iter=80, max_leaf_nodes=7,
                min_samples_leaf=100, l2_regularization=10, learning_rate=.05,
                early_stopping=False, random_state=17),
        }
        val_pred, test_pred = {}, {}
        with threadpool_limits(limits=2):
            for family, model in models.items():
                model.fit(train[list(FEATURES)], train.y)
                val_pred[family] = model.predict(validation[list(FEATURES)])
                test_pred[family] = model.predict(test[list(FEATURES)])
        val_pred["forecast_consensus"] = np.minimum(val_pred["forecast_ridge"], val_pred["forecast_boosted"])
        test_pred["forecast_consensus"] = np.minimum(test_pred["forecast_ridge"], test_pred["forecast_boosted"])
        receipt["calibration"], receipt["calibration_diagnostics"] = {}, {}
        receipt["past_validation_predictive_diagnostics"] = {}
        receipt["test_prediction_distributions"] = {}
        receipt["first_test_forecasts"] = {family:float(pred[0]) for family, pred in test_pred.items()}
        for family in ARRANGEMENTS:
            details = calibration_details(validation, val_pred[family], hold, min_events)
            selection = details["selection"]
            receipt["calibration"][family] = selection
            receipt["calibration_diagnostics"][family] = details
            receipt["past_validation_predictive_diagnostics"][family] = predictive_diagnostics(
                validation.y, val_pred[family], float(train.y.mean()))
            receipt["test_prediction_distributions"][family] = distribution(test_pred[family])
            if progress:
                why = "ACCEPTED" if selection else ", ".join(sorted({reason
                    for row in details["thresholds"] for reason in row["rejection_reasons"]}))
                progress(f"  {receipt['month']} {family}: {why}")
            if selection is None:
                continue
            for r, pred in zip(test.itertuples(index=False), test_pred[family]):
                if pred < selection["threshold"]:
                    continue
                sig = m.Signal(family, 1, float(pred/r.stop), float(r.stop), float(r.target), hold,
                    int(r.ts), float(r.close), float(r.atr), False)
                signals[family][(int(r.ts)+m.BAR, r.pair)] = sig
        folds.append(receipt)
        cursor = following
    return signals, folds, prepared


def forecasting_market(prepared, candidates):
    compiled = {}
    for pair, f in prepared.items():
        for row in f[["ts", "open", "high", "low", "close", "atr"]].itertuples(index=False, name=None):
            now = int(row[0])
            sig = candidates.get((now, pair))
            compiled.setdefault(now, {})[pair] = (tuple(float(v) for v in row[1:]), [sig] if sig else [])
    return sorted(compiled.items())


def save_fit_diagnostics(out, folds, receipt, manifest):
    payload = dict(version=VERSION, status="FORECAST_FIT_DIAGNOSTICS_NO_ACTIVATION",
        folds=folds, universe=receipt, input_manifest=manifest,
        sklearn_version=sklearn.__version__,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        policy_changed=False, limitations=LIMITS)
    m.save_json(out/"forecast-diagnostics.json", payload)
    lines = ["# Forecast calibration diagnostics", "",
        "Trading thresholds are unchanged. These describe earlier calibration rows, not portfolio profits.", "",
        "| Fees | Test month | Model | Threshold | Raw events | Spaced events | Mean net | PF | Decision |",
        "|---|---|---|---:|---:|---:|---:|---:|---|"]
    for fee, receipts in folds.items():
        for fold in receipts:
            if fold["status"] != "PAST_ONLY_FIT":
                lines.append(f"| {fee} | {fold['month']} | — | — | — | — | — | — | {fold['status']} |")
                continue
            for family, details in fold["calibration_diagnostics"].items():
                for row in details["thresholds"]:
                    mean = "n/a" if row["mean_net_return"] is None else f"{100*row['mean_net_return']:.3f}%"
                    factor = "n/a (no losses)" if row["profit_factor"] is None else f"{row['profit_factor']:.3f}"
                    if not row["nonoverlapping_asset_events"]:
                        factor = "n/a (no events)"
                    why = "ACCEPTED" if row["accepted"] else ", ".join(row["rejection_reasons"])
                    lines.append(f"| {fee} | {fold['month']} | {family} | {100*row['threshold']:.1f}% | {row['raw_events']} | {row['nonoverlapping_asset_events']} | {mean} | {factor} | {why} |")
    lines.extend(["", "JSON includes full prediction distributions, earlier validation errors versus a past-mean baseline, per-asset selected counts, and chronology receipts."])
    (out/"forecast-diagnostics.md").write_text("\n".join(lines)+"\n")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--daily-operating-cost-usd", type=float, default=0)
    p.add_argument("--diagnostics-only", action="store_true",
        help="Fit/calibrate on cached candles and explain every threshold; skip the 48 portfolio replays")
    a = p.parse_args()
    root, out = Path(a.data_dir), Path(a.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    receipt = json.loads((root/"universe.json").read_text())
    frames, manifest = {}, []
    for asset in receipt["selected"]:
        pair = asset["pair"]
        path = root/(pair.replace("/", "_")+"-15m.feather")
        frames[pair] = m.normalized(pd.read_feather(path))
        manifest.append(dict(pair=pair, bars=len(frames[pair]),
            gaps=int((frames[pair].ts.diff().dropna() != m.BAR).sum()),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    reports, fold_receipts, baselines = [], {}, {}
    for fee_profile in m.FEE_PROFILES:
        candidates, folds, prepared = monthly_predictions(frames, fee_profile,
            receipt["formation_end_ms"], progress=lambda s:print(s, flush=True))
        fold_receipts[fee_profile] = folds
        eligible = [f for f in folds if f["status"] == "PAST_ONLY_FIT"]
        if a.diagnostics_only:
            continue
        if not eligible:
            raise ValueError("No chronological test months after past-only training")
        start = min(f["test_start_ms"] for f in eligible)
        for family in ARRANGEMENTS:
            market = [(ts, rows) for ts, rows in forecasting_market(prepared, candidates[family]) if ts >= start]
            for risk in ("balanced", "aggressive"):
                for spread in (5, 15):
                    for execution in ("trigger", "extrema"):
                        cfg = m.Config(family=family, risk=risk, mode="long_only", spread_bps=spread,
                            execution=execution, fee_profile=fee_profile,
                            daily_operating_cost_usd=a.daily_operating_cost_usd)
                        name = f"{family}-{risk}-{fee_profile}-{spread}bps-{execution}"
                        print("Replaying "+name, flush=True)
                        result = m.simulate(market, cfg, allowed_families=ARRANGEMENTS)
                        months = []
                        for month, lo, hi, partial in m.month_windows(market):
                            r = m.simulate(market, cfg, lo, hi, allowed_families=ARRANGEMENTS)
                            months.append(dict(month=month, partial=partial, **r["summary"]))
                        full = [r for r in months if not r["partial"]]
                        stats = dict(name=name, config=m.asdict(cfg), **result["summary"],
                            complete_months=len(full), positive_months=sum(r["return_pct"] > 0 for r in full),
                            median_month_return_pct=float(np.median([r["return_pct"] for r in full])) if full else None,
                            monthly_best_equity=max(r["ending_equity"] for r in full) if full else None,
                            monthly_worst_equity=min(r["ending_equity"] for r in full) if full else None,
                            milestone_month_counts={str(goal):sum(r["ending_equity"] >= goal for r in full) for goal in MILESTONES})
                        stats["development_screen_pass"] = bool(len(full) >= 3 and stats["trades"] >= 20 and
                            stats["return_pct"] > 0 and stats["median_month_return_pct"] > 0 and
                            stats["positive_months"] >= math.ceil(.6*len(full)) and
                            stats["profit_factor"] is not None and stats["profit_factor"] >= 1.1 and
                            stats["max_drawdown_pct"] <= 100*cfg.drawdown_limit and not stats["pending_positions"])
                        result.update(monthly_independent_100=months, limitations=LIMITS,
                            universe=receipt, input_manifest=manifest, folds=folds)
                        m.save_json(out/(name+".json"), result)
                        if result["trades"]:
                            pd.DataFrame(result["trades"]).to_csv(out/(name+"-trades.csv"), index=False)
                        reports.append(stats)
                        print(f"  End ${stats['ending_equity']:.2f}; trades {stats['trades']}; DD {stats['max_drawdown_pct']:.2f}%", flush=True)
                        m.save_json(out/"forecast-progress.json", dict(version=VERSION, completed=len(reports), expected=48, reports=reports))
            for spread in (5, 15):
                key = f"{fee_profile}-{spread}bps"
                if key not in baselines:
                    baselines[key] = m.buy_and_hold(market, m.Config(spread_bps=spread, fee_profile=fee_profile))
    save_fit_diagnostics(out, fold_receipts, receipt, manifest)
    if a.diagnostics_only:
        print("Saved forecast-diagnostics.json and forecast-diagnostics.md. No portfolio replays or activation.", flush=True)
        return
    robust = []
    for family in ARRANGEMENTS:
        for risk in ("balanced", "aggressive"):
            group = [r for r in reports if r["config"]["family"] == family and r["config"]["risk"] == risk and
                r["config"]["fee_profile"] == "kraken_spot"]
            if len(group) == 4 and all(r["development_screen_pass"] for r in group):
                robust.append(f"{family}-{risk}-kraken_spot")
    summary = dict(version=VERSION, status="DEVELOPMENT_ONLY_NO_ACTIVATION", profit_ceiling=None,
        milestones=list(MILESTONES), reports=reports, robust_kraken_development_candidates=robust,
        fee_rate_sensitivity_only=[r["name"] for r in reports if r["config"]["fee_profile"] != "kraken_spot" and r["development_screen_pass"]],
        folds=fold_receipts, universe=receipt, input_manifest=manifest, buy_and_hold_baselines=baselines,
        sklearn_version=sklearn.__version__, source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        limitations=LIMITS, sources={"forecasting":"https://arxiv.org/abs/2606.00060",
            "temporal_splits":"https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html",
            "alpaca_rates":"https://docs.alpaca.markets/us/docs/crypto-fees", **m.SOURCES})
    m.save_json(out/"forecast-summary.json", summary)
    lines = ["# Forecast edge development results", "", "Profit ceiling: NONE. Reused data; no activation.", "",
        "| Configuration | End equity | Peak | Trades | Recorded-fill gross | Fees | Max DD | Median month |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in reports:
        median = "n/a" if r["median_month_return_pct"] is None else f"{r['median_month_return_pct']:.2f}%"
        lines.append(f"| {r['name']} | ${r['ending_equity']:.2f} | ${r['peak_equity']:.2f} | {r['trades']} | ${r['recorded_fill_gross_pnl']:.2f} | ${r['fees']:.2f} | {r['max_drawdown_pct']:.2f}% | {median} |")
    lines.extend(["", "Robust Kraken development candidates: "+(", ".join(robust) if robust else "NONE"), "", *LIMITS])
    (out/"forecast-results.md").write_text("\n".join(lines)+"\n")
    print("Saved forecast-summary.json and forecast-results.md. No paper activation.", flush=True)


if __name__ == "__main__":
    main()
