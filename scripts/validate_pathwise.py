"""
Validate the pathwise equity/FX deltas of the close-out exposure
(greeks/pathwise.py) against bump-and-reprice deltas computed on the SAME
simulated paths and NPVs, and record what each costs.

Both estimators are computed inside one run so they see identical market
inputs and random numbers (an earlier version compared against a Greeks run
made hours earlier on a slightly different market snapshot, which made
near-zero deltas disagree). Differences are measured as a fraction of the
largest single-name delta of the same netting set and measure.

    python scripts/validate_pathwise.py [--scenarios 1000]

Writes data/processed/pathwise_validation.json.
"""
import argparse
import json
import os
import sys
import time
from datetime import date

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
OUT = os.path.join(ROOT, "data", "processed", "pathwise_validation.json")
CP = ("CPTY_A", "CPTY_B", "CPTY_C")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", type=int, default=1000)
    args = ap.parse_args()
    N = args.scenarios

    from run_simulation import load_trades
    from risk_engine.models.calibration import build_calibration
    from risk_engine.simulation.engine import SimulationEngine
    from risk_engine.simulation.parallel import reprice_all_parallel, reprice_bumps_parallel
    from risk_engine.greeks.exposure import CloseOut, measures_closeout, apply_rows
    from risk_engine.greeks.pathwise import pathwise_deltas

    ref = date(2026, 8, 28)
    calib = build_calibration(ref)
    trades = load_trades()
    eng = SimulationEngine(calib, trades, method="latin_hypercube", n_scenarios=N, seed=42, mpor_days=10, vm_lag_days=1)
    paths = eng.simulate_paths()
    t0 = time.perf_counter()
    ids, npv = reprice_all_parallel(eng, paths)
    base_s = time.perf_counter() - t0
    npv = np.nan_to_num(npv)
    ctx = CloseOut(eng, ref)

    t0 = time.perf_counter()
    pw = pathwise_deltas(eng, paths, ids, npv, ctx.keep, window=0.02)
    pw_s = time.perf_counter() - t0

    holders = {}
    for t, tr in trades.items():
        if hasattr(tr, "positions"):
            for p in tr.positions:
                holders.setdefault(p.isin, set()).add(t)
    fx_trades = {t for t, tr in trades.items() if hasattr(tr, "positions") and any(p.currency == "JPY" for p in tr.positions)}
    specs, tags = [], []
    for isin, h in holders.items():
        for mult, tag in ((1.01, "up"), (0.99, "dn")):
            specs.append({"eq": {isin: mult}, "fx": 1.0, "trades": h})
            tags.append(("eq", isin, tag))
    for mult, tag in ((1.01, "up"), (0.99, "dn")):
        specs.append({"eq": {}, "fx": mult, "trades": fx_trades})
        tags.append(("fx", "USDJPY", tag))
    t0 = time.perf_counter()
    rep = reprice_bumps_parallel(eng, paths, specs)
    bump_reprice_s = time.perf_counter() - t0
    M = {tg: measures_closeout(ids, eng.trade_counterparty, apply_rows(npv, rows, arr), ctx) for tg, (rows, arr) in zip(tags, rep)}
    print(f"base reprice {base_s:.0f}s; {len(specs)} bumps {bump_reprice_s:.0f}s; pathwise {pw_s:.2f}s", flush=True)

    res = {"n_scenarios": N, "pathwise_seconds": pw_s, "bump_seconds": bump_reprice_s, "n_bumps": len(specs), "base_reprice_seconds": base_s,
           "equity": {m: [] for m in ("EE", "MED", "PFE")}, "fx": {m: [] for m in ("EE", "MED", "PFE")}}
    for c in CP:
        for m in ("EE", "MED", "PFE"):
            bumps = {}
            for isin in holders:
                if isin in pw["equity"][c]:
                    bumps[isin] = 0.5 * (M[("eq", isin, "up")][c][m] - M[("eq", isin, "dn")][c][m])
            scale = max([np.abs(b).max() for b in bumps.values()] + [1.0])
            for isin, b in bumps.items():
                a = pw["equity"][c][isin][m]
                res["equity"][m].append({"cpty": c, "isin": isin, "scale": float(scale), "own_peak": float(np.abs(b).max()),
                                         "max_abs_diff_over_scale": float(np.abs(a - b).max() / scale),
                                         "rms_diff_over_scale": float(np.sqrt(np.mean((a - b) ** 2)) / scale)})
            bfx = 0.5 * (M[("fx", "USDJPY", "up")][c][m] - M[("fx", "USDJPY", "dn")][c][m])
            if np.abs(bfx).max() >= 1.0:
                a = pw["fx"][c][m]
                res["fx"][m].append({"cpty": c, "scale": float(np.abs(bfx).max()),
                                     "max_abs_diff_over_scale": float(np.abs(a - bfx).max() / np.abs(bfx).max()),
                                     "rms_diff_over_scale": float(np.sqrt(np.mean((a - bfx) ** 2)) / np.abs(bfx).max())})
    for m in ("EE", "MED", "PFE"):
        for kind in ("equity", "fx"):
            xs = res[kind][m]
            if xs:
                res[f"{kind}_{m}_summary"] = {"n": len(xs), "median_max_abs": float(np.median([x["max_abs_diff_over_scale"] for x in xs])),
                                              "worst_max_abs": float(max(x["max_abs_diff_over_scale"] for x in xs)),
                                              "median_rms": float(np.median([x["rms_diff_over_scale"] for x in xs]))}
                print(kind, m, res[f"{kind}_{m}_summary"], flush=True)
    json.dump(res, open(OUT, "w"), indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
