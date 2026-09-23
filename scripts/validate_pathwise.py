"""
Validate the pathwise equity/FX deltas of the close-out exposure
(greeks/pathwise.py) against the bump-and-reprice deltas of run_greeks.py,
on the real book, same scenarios, and record what each costs.

    python scripts/validate_pathwise.py

Reads data/processed/greeks_results.json (close-out convention) and writes
data/processed/pathwise_validation.json.
"""
import json
import os
import sys
import time
from datetime import date

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
OUT = os.path.join(ROOT, "data", "processed", "pathwise_validation.json")
GREEKS = os.path.join(ROOT, "data", "processed", "greeks_results.json")


def main():
    from run_simulation import load_trades
    from risk_engine.models.calibration import build_calibration
    from risk_engine.simulation.engine import SimulationEngine
    from risk_engine.simulation.parallel import reprice_all_parallel
    from risk_engine.greeks.exposure import CloseOut
    from risk_engine.greeks.pathwise import pathwise_deltas

    g = json.load(open(GREEKS))
    assert g.get("convention") == "closeout", "run_greeks.py must have been run with the close-out convention"
    N = g["n_scenarios"]
    ref = date(2026, 8, 28)
    calib = build_calibration(ref)
    trades = load_trades()
    eng = SimulationEngine(calib, trades, method="latin_hypercube", n_scenarios=N, seed=42, mpor_days=10, vm_lag_days=1)
    paths = eng.simulate_paths()
    ids, npv = reprice_all_parallel(eng, paths)
    ctx = CloseOut(eng, ref)
    assert [str(d) for d in ctx.report_dates()] == g["dates"], "grid differs from the Greeks run"

    t0 = time.perf_counter()
    pw = pathwise_deltas(eng, paths, ids, npv, ctx.keep, window=0.02)
    pw_s = time.perf_counter() - t0
    print(f"pathwise equity+FX deltas for every name and netting set: {pw_s:.2f}s", flush=True)

    def compare(a, b):
        a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
        scale = max(np.abs(b).max(), 1.0)
        return {"max_abs_diff_over_scale": float(np.abs(a - b).max() / scale),
                "rms_diff_over_scale": float(np.sqrt(np.mean((a - b) ** 2)) / scale),
                "scale": float(scale), "n_dates": int(len(a))}

    res = {"n_scenarios": N, "pathwise_seconds": pw_s, "bump_seconds": {k: g["timing"].get(k) for k in
                                                                       ("equity_fx_bumps_s", "n_equity_fx_bumps", "base_run_s", "rate_vol_resims_s")},
           "equity": {}, "fx": {}}
    for m in ("EE", "MED", "PFE"):
        res["equity"][m], res["fx"][m] = [], []
    for c in ("CPTY_A", "CPTY_B", "CPTY_C", "__portfolio__"):
        for isin, v in g["equity"].items():
            if c == "__portfolio__":
                continue
            if isin not in pw["equity"].get(c, {}):
                continue
            for m in ("EE", "MED", "PFE"):
                bump = v["delta"][c][m]
                if np.abs(bump).max() < 1.0:
                    continue
                r = compare(pw["equity"][c][isin][m], bump)
                r.update(cpty=c, isin=isin)
                res["equity"][m].append(r)
        for m in ("EE", "MED", "PFE"):
            bump = g["fx"]["delta"][c][m]
            if c != "__portfolio__" and np.abs(bump).max() >= 1.0:
                r = compare(pw["fx"][c][m], bump)
                r.update(cpty=c)
                res["fx"][m].append(r)
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
