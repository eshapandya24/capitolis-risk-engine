"""
Par-instrument (Jacobian) DV01 buckets, computed EXACTLY without resimulation.

Two upgrades over the exposure Greeks' existing rate buckets
(greeks/bumps.py's bump_curve(), Report 9.3):

  1. The bump is applied to the curve's own NATIVE construction pillars
     (SOFR-futures-implied + Bloomberg-spliced points), grouped into the
     report's 8 key tenors, instead of a hand-chosen triangular zero-rate
     grid -- see greeks/rate_jacobian.py for why this matters most in the
     20-30y region where BF_0003 (the dominant bond forward) lives.
  2. Each bucket's exposure delta is computed with greeks/rate_shift.py's
     EXACT analytic path-shift (validated against true resimulation to
     1e-15 relative precision, tests/test_rate_shift.py): the same simulated
     Latin Hypercube draws are reused, unchanged, with only the deterministic
     drift offset applied. This skips the path-simulation cost of a
     resimulated bump entirely (no new random draws, no SDE stepping); each
     bucket still needs a full reprice of every trade (the curve bump changes
     discounting book-wide, so it cannot use the equity/FX bump's
     subset-repricing shortcut), which is the actual timing measured below.

    python scripts/run_dv01_jacobian.py [--scenarios 5000]

Writes data/processed/dv01_jacobian.json.
"""
import argparse
import json
import os
import time
from datetime import date

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "processed", "dv01_jacobian.json")
REPORT_TENORS = (0.25, 0.5, 1, 2, 3, 5, 10, 30)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", type=int, default=5000)
    args = ap.parse_args()
    N = args.scenarios

    from run_simulation import load_trades
    from risk_engine.models.calibration import build_calibration, _isin_currency
    from risk_engine.models.rates import HullWhite1F
    from risk_engine.simulation.engine import SimulationEngine
    from risk_engine.simulation.parallel import reprice_all_parallel
    from risk_engine.greeks.exposure import measures_closeout, diff_measures, CloseOut
    from risk_engine.greeks.rate_jacobian import bucket_native_pillars, bump_curve_native_pillars, jacobian_zero_to_pillar
    from risk_engine.greeks.rate_shift import fast_rate_bump_paths

    ref = date(2026, 8, 28)
    calib = build_calibration(ref)
    trades = load_trades()
    curve = calib["usd_curve"]
    currencies = _isin_currency()

    J = jacobian_zero_to_pillar(curve, REPORT_TENORS)
    buckets = bucket_native_pillars(curve, REPORT_TENORS)

    eng = SimulationEngine(calib, trades, method="latin_hypercube", n_scenarios=N, seed=42, mpor_days=10, vm_lag_days=1)
    t0 = time.perf_counter()
    paths = eng.simulate_paths()
    ids, npv0 = reprice_all_parallel(eng, paths)
    npv0 = np.nan_to_num(npv0)
    print(f"base run {time.perf_counter() - t0:.0f}s", flush=True)
    base = measures_closeout(ids, eng.trade_counterparty, npv0, CloseOut(eng, ref))
    peak = int(np.argmax(base["__portfolio__"]["PFE"]))
    paths_t = dict(paths, _times=eng.times)

    shift = 1e-4  # +1bp
    res = {"n_scenarios": N, "shift_bp": 1.0, "report_tenors": list(REPORT_TENORS),
          "jacobian_zero_to_pillar": J.tolist(), "native_pillar_times": list(curve._t),
          "bucket_pillar_indices": {str(t): idxs for t, idxs in buckets.items()},
          "par_bucket_dv01": {}, "peak_node": peak, "method": "exact analytic path-shift, no resimulation"}

    def bumped_engine(bumped_curve):
        cal2 = dict(calib, usd_curve=bumped_curve, hw=HullWhite1F(bumped_curve, calib["hw"].sigma, calib["hw"].a))
        return SimulationEngine(cal2, trades, method="latin_hypercube", n_scenarios=N, seed=42, mpor_days=10, vm_lag_days=1)

    t0 = time.perf_counter()
    for t in REPORT_TENORS:
        idxs = buckets[t]
        bumped_curve = bump_curve_native_pillars(curve, idxs, shift)
        e2 = bumped_engine(bumped_curve)
        fast_paths = fast_rate_bump_paths(paths_t, eng.hw, e2.hw, currencies)
        ids2, npv2 = reprice_all_parallel(e2, fast_paths)
        up = measures_closeout(ids2, e2.trade_counterparty, np.nan_to_num(npv2), CloseOut(e2, ref))
        d = diff_measures(up, base)
        res["par_bucket_dv01"][str(t)] = {c: {m: float(d[c][m][peak]) for m in ("EE", "MED", "PFE")} for c in base}

    parallel_curve = bump_curve_native_pillars(curve, range(len(curve._t)), shift)
    e_par = bumped_engine(parallel_curve)
    fast_par = fast_rate_bump_paths(paths_t, eng.hw, e_par.hw, currencies)
    ids_p, npv_p = reprice_all_parallel(e_par, fast_par)
    up_par = measures_closeout(ids_p, e_par.trade_counterparty, np.nan_to_num(npv_p), CloseOut(e_par, ref))
    d_par = diff_measures(up_par, base)
    res["parallel_dv01"] = {c: {m: float(d_par[c][m][peak]) for m in ("EE", "MED", "PFE")} for c in base}
    print(f"all 8 buckets + parallel (exact, no resim) done in {time.perf_counter() - t0:.0f}s", flush=True)

    sum_buckets = {c: {m: sum(res["par_bucket_dv01"][str(t)][c][m] for t in REPORT_TENORS) for m in ("EE", "MED", "PFE")} for c in base}
    res["sum_of_par_buckets"] = sum_buckets
    print("\nPortfolio PFE99 DV01 per +1bp, by report tenor bucket (par-instrument / Jacobian method):")
    for t in REPORT_TENORS:
        print(f"  {t:>5}y: {res['par_bucket_dv01'][str(t)]['__portfolio__']['PFE']:>12,.0f}")
    print(f"  sum:    {sum_buckets['__portfolio__']['PFE']:>12,.0f}")
    print(f"  parallel: {res['parallel_dv01']['__portfolio__']['PFE']:>12,.0f}")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(res, f)
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
