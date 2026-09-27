"""
Sampling-scheme study for the Greeks: does Latin Hypercube (or another scheme)
reduce the Monte Carlo error of bump-and-reprice sensitivities?

For each sampling method and each of R independent seeds we simulate N
scenarios, reprice, bump (common random numbers within the seed) and compute
the close-out delta of EE, median PFE and PFE99 at the peak date:
  - equity delta: all equities +/-1% (no re-simulation)
  - FX delta: USDJPY +/-1%
  - optional --rates: parallel DV01 (+/-1bp, re-simulation with the same draws)
The spread of each delta ACROSS SEEDS is the sampling error of the sensitivity;
the ratio to pseudo-random is the benefit of the scheme.
"""
import argparse
import json
import os
import sys
import time
from datetime import date

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "processed", "greeks_sampling.json")
CP = ("CPTY_A", "CPTY_B", "CPTY_C", "__portfolio__")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=256)
    ap.add_argument("--repeats", type=int, default=6)
    ap.add_argument("--methods", default="pseudo_random,antithetic,moment_matched,sobol,latin_hypercube")
    ap.add_argument("--rates", action="store_true")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    from run_simulation import load_trades
    from risk_engine.models.calibration import build_calibration
    from risk_engine.simulation.engine import SimulationEngine
    from risk_engine.simulation.parallel import reprice_all_parallel, reprice_bumps_parallel
    from risk_engine.greeks.book import book_greeks
    from risk_engine.greeks.bumps import make_calib
    from risk_engine.greeks.exposure import apply_rows, diff_measures, CloseOut, measures_closeout

    ref = date(2026, 8, 28)
    calib = build_calibration(ref)
    trades = load_trades()
    bg = book_greeks(calib, trades)
    holders = {i: {t for t, x in v["delta"].items() if abs(x) > 1e-6} for i, v in bg["equity"].items()}
    holders = {i: h for i, h in holders.items() if h}
    fx_holders = {t for t, x in bg["fx"]["delta"].items() if abs(x) > 1e-6}
    all_eq = set().union(*holders.values())

    def mk(cal, seed, method):
        return SimulationEngine(cal, trades, method=method, n_scenarios=args.n, seed=seed, mpor_days=10, vm_lag_days=1)

    def measure(e, ids, npv):
        return measures_closeout(ids, e.trade_counterparty, npv, CloseOut(e, ref))

    def pick(d):
        return {c: {m: float(d[c][m][peak]) for m in ("EE", "MED", "PFE")} for c in CP}

    res = {"n": args.n, "repeats": args.repeats, "rates": args.rates, "methods": {}}
    peak = None
    for method in args.methods.split(","):
        rows = []
        for r in range(args.repeats):
            seed = 500 + r
            t0 = time.perf_counter()
            e = mk(calib, seed, method)
            p = e.simulate_paths()
            ids, n0 = reprice_all_parallel(e, p)
            n0 = np.nan_to_num(n0)
            base = measure(e, ids, n0)
            if peak is None:
                g = json.load(open(os.path.join(os.path.dirname(OUT), "greeks_results.json")))
                peak = int(np.argmax(g["base"]["__portfolio__"]["PFE"]))   # peak date of the N=2000 run
                res["node"] = peak
            bumps = [{"eq": {i: m for i in holders}, "fx": 1.0, "trades": all_eq} for m in (1.01, 0.99)]
            bumps += [{"eq": {}, "fx": m, "trades": fx_holders} for m in (1.01, 0.99)]
            rep = reprice_bumps_parallel(e, p, bumps)
            M = [measure(e, ids, apply_rows(n0, rw, arr)) for rw, arr in rep]
            row = {"base": {c: {m: float(base[c][m][peak]) for m in ("EE", "MED", "PFE")} for c in CP},
                   "equity": pick(diff_measures(M[0], M[1], 0.5)),
                   "fx": pick(diff_measures(M[2], M[3], 0.5))}
            if args.rates:
                def resim(b):
                    e2 = mk(make_calib(calib, b), seed, method)
                    p2 = e2.simulate_paths()
                    i2, n2 = reprice_all_parallel(e2, p2)
                    return measure(e2, i2, np.nan_to_num(n2))
                d = diff_measures(resim(("ir_delta", None, 1e-4)), resim(("ir_delta", None, -1e-4)), 0.5)
                row["rate"] = pick(d)
            rows.append(row)
            print("%s seed %d done in %.0fs" % (method, seed, time.perf_counter() - t0), flush=True)
        res["methods"][method] = rows
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w") as f:
            json.dump(res, f)
    print("saved", args.out, flush=True)


if __name__ == "__main__":
    main()
