"""
Runs the full pipeline once at the reporting settings and dumps everything
scripts/build_report.py needs (exposure arrays, paths, trade metadata,
calibration details) to data/processed/report/. Kept separate from the PDF
builder so the ~10 min simulation is not repeated on every layout tweak.

    python scripts/generate_report_data.py [--scenarios N]
"""
import argparse
import json
import os
import pickle
import time
from datetime import date

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "processed", "report")


def run(calib, trades, n, mpor_days, corr_mode="full", k=5, method="latin_hypercube"):
    from risk_engine.simulation.engine import SimulationEngine
    from risk_engine.simulation.parallel import reprice_all_parallel
    eng = SimulationEngine(calib, trades, method=method, n_scenarios=n, seed=42,
                           mpor_days=mpor_days, corr_mode=corr_mode, n_pca_factors=k)
    t0 = time.perf_counter()
    paths = eng.simulate_paths()
    t1 = time.perf_counter()
    ids, npv = reprice_all_parallel(eng, paths)
    t2 = time.perf_counter()
    print(f"  [{corr_mode}] paths {t1-t0:.1f}s reprice {t2-t1:.1f}s", flush=True)
    return eng, paths, ids, npv, {"paths_s": t1 - t0, "reprice_s": t2 - t1}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", type=int, default=3000)
    ap.add_argument("--compare-n", type=int, default=1500)
    args = ap.parse_args()

    from run_simulation import load_trades
    from risk_engine.models.calibration import build_calibration
    os.makedirs(OUT, exist_ok=True)

    calib = build_calibration(date(2026, 8, 28))
    trades = load_trades()

    eng, paths, ids, npv, timing = run(calib, trades, args.scenarios, 10)
    meta = {
        "dates": [str(d) for d in eng.dates], "times": list(eng.times),
        "node_map": {int(i): m for i, m in eng.node_map.items()},
        "trade_ids": ids, "trade_counterparty": eng.trade_counterparty,
        "trade_type": {t: type(tr).__name__ for t, tr in trades.items()},
        "trade_expiry": {t: str(e) for t, e in eng.trade_expiries.items()},
        "n_scenarios": args.scenarios, "timing": timing,
        "factor_order": eng.factor_order,
        "hw_a": calib["hw"].a, "hw_sigma": calib["hw"].sigma,
        "hw_r0": calib["hw"].short_rate0(),
        "hw_jpy": (None if calib["hw_jpy"] is None else
                   {"a": calib["hw_jpy"].a, "sigma": calib["hw_jpy"].sigma,
                    "r0": calib["hw_jpy"].short_rate0(),
                    "detail": {k: v for k, v in (calib["hw_jpy_detail"] or {}).items()
                               if k != "calibration_detail"}}),
        "usd_jpy_corr": calib["usd_jpy_rate_factor_corr"],
        "usd_jpy_corr_detail": calib["usd_jpy_rate_factor_corr_detail"],
        "jpy_usd_rate_diff": calib["jpy_usd_rate_diff"],
        "fx_spot": calib["fx_spot"],
        "hw_calibration_detail": calib["hw_calibration_detail"],
        "equity_spots": calib["equity_spots"], "dividends": calib["dividends"],
        "currencies": calib["gbm"].currencies, "vols": calib["gbm"].vols,
    }
    with open(os.path.join(OUT, "meta.json"), "w") as f:
        json.dump(meta, f, indent=1, default=str)
    np.savez_compressed(os.path.join(OUT, "main_run.npz"), npv=npv,
                        x_rate=paths["x_rate"], ln_fx=paths["ln_fx"],
                        **{"ln_spot_" + k: v for k, v in paths["ln_spot"].items()})
    # trade-level t0 detail
    with open(os.path.join(OUT, "trades.pkl"), "wb") as f:
        pickle.dump({t: {k: v for k, v in vars(tr).items()
                         if isinstance(v, (int, float, str, date))}
                     for t, tr in trades.items()}, f)
    print("main run saved", flush=True)

    # full-rank vs PCA factor-model comparison (same seed/method)
    n = args.compare_n
    out = {}
    for mode, k in (("full", 5), ("factor", 3), ("factor", 5), ("factor", 10)):
        e2, p2, i2, n2, _ = run(calib, trades, n, None, corr_mode=mode, k=k)
        out[f"{mode}_{k}" if mode == "factor" else "full"] = n2
        np.savez_compressed(os.path.join(OUT, f"cmp_{mode}_{k}.npz"), npv=n2)
    with open(os.path.join(OUT, "cmp_meta.json"), "w") as f:
        json.dump({"n": n, "dates": [str(d) for d in e2.dates], "trade_ids": i2,
                   "trade_counterparty": e2.trade_counterparty}, f)
    print("DONE", flush=True)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    main()
