"""
Complete Greeks for the ESF book (Capitolis project objective 3):

  A. t=0 book Greeks by trade and netting set (delta/gamma per equity, FX,
     rate DV01 parallel + bucketed, rate gamma) -- deterministic.
  B. Sensitivities of EE, median PFE and PFE99 (per netting set and
     portfolio, at every reporting date) to: every equity (delta, gamma),
     all equities, USDJPY (delta, gamma), USD rates (parallel delta/gamma and
     bucketed DV01), and volatilities (rate, FX, equity vega). Common random
     numbers throughout.
  C. Validation: bump-size stability, additivity, common-random-numbers
     versus independent draws, and timing.

    python scripts/run_greeks.py [--scenarios 2000]
"""
import argparse
import json
import os
import sys
import time
from datetime import date

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "processed", "greeks_results.json")
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def tolist(d):
    if isinstance(d, dict):
        return {str(k): tolist(v) for k, v in d.items()}
    if isinstance(d, np.ndarray):
        return d.tolist()
    if isinstance(d, (np.floating, np.integer)):
        return float(d)
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", type=int, default=2000)
    ap.add_argument("--crn-n", type=int, default=300)
    ap.add_argument("--crn-repeats", type=int, default=4)
    args = ap.parse_args()

    from run_simulation import load_trades
    from risk_engine.models.calibration import build_calibration
    from risk_engine.simulation.engine import SimulationEngine
    from risk_engine.simulation.parallel import reprice_all_parallel, reprice_bumps_parallel
    from risk_engine.greeks.book import book_greeks, netting_set_totals
    from risk_engine.greeks.bumps import make_calib, DEFAULT_TENORS
    from risk_engine.greeks.exposure import measures, apply_rows, diff_measures

    ref = date(2026, 8, 28)
    calib = build_calibration(ref)
    trades = load_trades()
    N = args.scenarios
    timing = {}

    # ---------------- A. t=0 book Greeks
    t0 = time.perf_counter()
    bg = book_greeks(calib, trades)
    timing["book_greeks_s"] = time.perf_counter() - t0
    cp = {tid: t.counterparty for tid, t in trades.items()}
    book = {"npv": bg["npv"], "npv_by_set": netting_set_totals(bg["npv"], cp),
            "equity_delta": {i: v["delta"] for i, v in bg["equity"].items() if any(abs(x) > 1e-6 for x in v["delta"].values())},
            "equity_gamma": {i: v["gamma"] for i, v in bg["equity"].items() if any(abs(x) > 1e-3 for x in v["gamma"].values())},
            "fx_delta": bg["fx"]["delta"], "fx_gamma": bg["fx"]["gamma"],
            "rate_parallel": bg["rate"]["parallel"], "rate_gamma": bg["rate"]["gamma"],
            "rate_buckets": {str(k): v for k, v in bg["rate"]["buckets"].items()},
            "counterparty": cp}
    holders = {i: {t for t, x in v["delta"].items() if abs(x) > 1e-6} for i, v in bg["equity"].items()}
    holders = {i: h for i, h in holders.items() if h}
    fx_holders = {t for t, x in bg["fx"]["delta"].items() if abs(x) > 1e-6}
    all_eq_trades = set().union(*holders.values())
    print(f"t=0 Greeks done ({timing['book_greeks_s']:.1f}s); {len(holders)} equities with exposure, "
          f"{len(fx_holders)} FX-sensitive trades", flush=True)

    # ---------------- base simulation
    eng = SimulationEngine(calib, trades, method="latin_hypercube", n_scenarios=N, seed=42)
    t0 = time.perf_counter()
    paths = eng.simulate_paths()
    ids, npv0 = reprice_all_parallel(eng, paths)
    npv0 = np.nan_to_num(npv0)
    timing["base_run_s"] = time.perf_counter() - t0
    node_idx = list(range(len(eng.dates)))
    cpm = eng.trade_counterparty
    base = measures(ids, cpm, npv0, node_idx)
    res = {"n_scenarios": N, "dates": [str(d) for d in eng.dates], "times": list(map(float, eng.times)),
           "base": base, "book_t0": book, "equity": {}, "timing": timing}
    print(f"base run {timing['base_run_s']:.0f}s", flush=True)

    # ---------------- B1. equity / FX: no re-simulation, subset repricing, ONE pool
    bumps, tags = [], []
    for isin, h in holders.items():
        for mult, tag in ((1.01, "up"), (0.99, "dn")):
            bumps.append({"eq": {isin: mult}, "fx": 1.0, "trades": h}); tags.append(("eq", isin, tag))
    for mult, tag in ((1.01, "up"), (0.99, "dn")):
        bumps.append({"eq": {i: mult for i in holders}, "fx": 1.0, "trades": all_eq_trades}); tags.append(("eqall", "ALL", tag))
        bumps.append({"eq": {}, "fx": mult, "trades": fx_holders}); tags.append(("fx", "USDJPY", tag))
    # bump-size stability (all equities): +-0.5% and +-2%
    for mult, tag in ((1.005, "up05"), (0.995, "dn05"), (1.02, "up2"), (0.98, "dn2")):
        bumps.append({"eq": {i: mult for i in holders}, "fx": 1.0, "trades": all_eq_trades}); tags.append(("eqall", "ALL", tag))
    t0 = time.perf_counter()
    rep = reprice_bumps_parallel(eng, paths, bumps)
    timing["equity_fx_bumps_s"] = time.perf_counter() - t0
    timing["n_equity_fx_bumps"] = len(bumps)
    M = {}
    for (kind, name, tag), (rows, arr) in zip(tags, rep):
        M[(kind, name, tag)] = measures(ids, cpm, apply_rows(npv0, rows, arr), node_idx)
    for isin in holders:
        up, dn = M[("eq", isin, "up")], M[("eq", isin, "dn")]
        res["equity"][isin] = {"delta": diff_measures(up, dn, 0.5),
                               "gamma": {c: {m: up[c][m] - 2 * base[c][m] + dn[c][m] for m in base[c]} for c in base}}
    up, dn = M[("eqall", "ALL", "up")], M[("eqall", "ALL", "dn")]
    res["equity_all"] = {"delta": diff_measures(up, dn, 0.5),
                         "gamma": {c: {m: up[c][m] - 2 * base[c][m] + dn[c][m] for m in base[c]} for c in base}}
    up, dn = M[("fx", "USDJPY", "up")], M[("fx", "USDJPY", "dn")]
    res["fx"] = {"delta": diff_measures(up, dn, 0.5),
                 "gamma": {c: {m: up[c][m] - 2 * base[c][m] + dn[c][m] for m in base[c]} for c in base}}
    res["bump_size"] = {tag: diff_measures(M[("eqall", "ALL", u)], M[("eqall", "ALL", d)], 0.5 / h)
                        for tag, u, d, h in (("0.5%", "up05", "dn05", 0.5), ("1%", "up", "dn", 1.0), ("2%", "up2", "dn2", 2.0))}
    print(f"equity/FX bumps ({len(bumps)}) in {timing['equity_fx_bumps_s']:.0f}s", flush=True)

    # ---------------- B2. rates and vols: re-simulation with the same random numbers
    def resim(bump, seed=42, n=N):
        cal = make_calib(calib, bump)
        e2 = SimulationEngine(cal, trades, method="latin_hypercube", n_scenarios=n, seed=seed)
        p2 = e2.simulate_paths()
        i2, n2 = reprice_all_parallel(e2, p2)
        return measures(i2, e2.trade_counterparty, np.nan_to_num(n2), list(range(len(e2.dates))))

    t0 = time.perf_counter()
    up = resim(("ir_delta", None, 1e-4))
    dn = resim(("ir_delta", None, -1e-4))
    res["rate_parallel"] = {"delta": diff_measures(up, dn, 0.5),
                            "gamma": {c: {m: up[c][m] - 2 * base[c][m] + dn[c][m] for m in base[c]} for c in base}}
    res["rate_buckets"] = {}
    for k in DEFAULT_TENORS:
        res["rate_buckets"][str(k)] = diff_measures(resim(("ir_delta", k, 1e-4)), base)
        print(f"  rate bucket {k}y done", flush=True)
    res["vega"] = {"rate": diff_measures(resim(("ir_vega",)), base),
                   "fx": diff_measures(resim(("fx_vega",)), base),
                   "equity": diff_measures(resim(("eq_vega", tuple(holders))), base)}
    timing["rate_vol_resims_s"] = time.perf_counter() - t0
    print(f"rate/vol re-simulations in {timing['rate_vol_resims_s']:.0f}s", flush=True)

    # ---------------- C. common random numbers vs independent draws (small N, repeats)
    peak = int(np.argmax(base["__portfolio__"]["PFE"]))
    crn, ind = [], []
    for r in range(args.crn_repeats):
        seed_a, seed_b = 1000 + r, 2000 + r
        e = SimulationEngine(calib, trades, method="latin_hypercube", n_scenarios=args.crn_n, seed=seed_a)
        p = e.simulate_paths()
        i_, n_ = reprice_all_parallel(e, p)
        n_ = np.nan_to_num(n_)
        b_ = measures(i_, e.trade_counterparty, n_, list(range(len(e.dates))))
        rows_arr = reprice_bumps_parallel(e, p, [{"eq": {i: 1.01 for i in holders}, "fx": 1.0, "trades": all_eq_trades}])[0]
        u_ = measures(i_, e.trade_counterparty, apply_rows(n_, *rows_arr), list(range(len(e.dates))))
        crn.append(u_["__portfolio__"]["EE"][peak] - b_["__portfolio__"]["EE"][peak])
        indep_up = resim(("eq_delta", tuple(holders)), seed=seed_b, n=args.crn_n)
        ind.append(indep_up["__portfolio__"]["EE"][peak] - b_["__portfolio__"]["EE"][peak])
        print(f"  CRN check repeat {r} done", flush=True)
    res["crn_vs_independent"] = {"node": peak, "n": args.crn_n, "crn": crn, "independent": ind,
                                 "crn_std": float(np.std(crn)), "independent_std": float(np.std(ind)),
                                 "mean_crn": float(np.mean(crn)), "mean_independent": float(np.mean(ind))}

    with open(OUT, "w") as f:
        json.dump(tolist(res), f)
    print("saved", OUT, flush=True)


if __name__ == "__main__":
    main()
