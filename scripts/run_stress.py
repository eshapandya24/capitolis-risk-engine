"""
Stress test of the exposure engine: 8 hypothetical and 3 historical-replay
scenarios (risk_engine/stress/scenarios.py), each an instantaneous shock to
today's market state followed by the full Monte Carlo exposure from the
shocked state, on the same random numbers as the base case.

Reported per scenario: close-out exposure (the brief's definition) and level
(uncollateralized) exposure - EE, median PFE, PFE99, MPE - by counterparty,
portfolio and TRADE, at every reporting date, so sensitivity can be read along
the whole time path and product by product.

    python scripts/run_stress.py [--scenarios 1000]

Equity/FX shocks rescale the simulated paths exactly and reprice only the
trades that hold the shocked factor; any scenario with a rate shift rebuilds
the Hull-White curve and re-simulates (same seed).
"""
import argparse
import json
import os
import sys
import time
from datetime import date

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
OUT = os.path.join(ROOT, "data", "processed", "stress_results.json")
CPTYS = ("CPTY_A", "CPTY_B", "CPTY_C")


def measure(eng, ids, npv, ref):
    """Everything reported for one scenario, from an (n_trades, n_nodes, N) NPV array."""
    from risk_engine.exposure import spec_exposure as spec
    npv = np.nan_to_num(npv)
    nm = eng.node_map
    prev = {i: (m["prev"] if m["prev"] is not None else m["reporting"]) for i, m in nm.items()}
    ridx = [nm[i]["reporting"] for i in range(len(nm))]
    dates = [eng.dates[r] for r in ridx]
    one_year = np.array([(d - ref).days <= 365 for d in dates])
    kw = dict(prev_node=prev, trade_expiry=dict(eng.trade_expiries), exclude_maturing=True, dates=eng.dates)
    cpm = eng.trade_counterparty
    co = spec.exposure_by_counterparty(ids, cpm, npv, nm, **kw)
    co["__portfolio__"] = sum(co[c] for c in CPTYS)
    per_trade = spec.exposure_by_trade(ids, npv, nm, **kw)
    lvl = {}
    for c in CPTYS:
        idx = [i for i, t in enumerate(ids) if cpm[t] == c]
        lvl[c] = np.maximum(npv[idx].sum(axis=0)[ridx, :], 0.0)
    lvl["__portfolio__"] = sum(lvl[c] for c in CPTYS)

    def summ(a):
        s = spec.summarize(a, 0.99, one_year)
        return {"EE": s["EE"].tolist(), "MED": s["MedianExposure"].tolist(), "PFE": s["PFE"].tolist(),
                "MPE": s["MPE"], "EE_max": s["EE_max"]}

    return {"dates": [str(d) for d in dates], "one_year": one_year.tolist(),
            "closeout": {e: summ(a) for e, a in co.items()},
            "level": {e: summ(a) for e, a in lvl.items()},
            "per_trade": {t: {"counterparty": cpm[t], "MPE": spec.summarize(a, 0.99, one_year)["MPE"],
                              "EE_max": spec.summarize(a, 0.99, one_year)["EE_max"],
                              "mtm0": float(npv[i, 0, 0])} for i, (t, a) in enumerate(per_trade.items())},
            "mtm0": {c: float(sum(npv[i, 0, 0] for i, t in enumerate(ids) if cpm[t] == c)) for c in CPTYS}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", type=int, default=1000)
    args = ap.parse_args()
    N = args.scenarios

    from run_simulation import load_trades
    from risk_engine.models.calibration import build_calibration, _isin_currency
    from risk_engine.models.rates import HullWhite1F
    from risk_engine.simulation.engine import SimulationEngine
    from risk_engine.simulation.parallel import reprice_all_parallel, reprice_bumps_parallel
    from risk_engine.greeks.exposure import apply_rows
    from risk_engine.market import treasury
    from risk_engine.stress import scenarios as S

    ref = date(2026, 8, 28)
    calib = build_calibration(ref)
    trades = load_trades()
    cur = _isin_currency()
    isins = sorted(calib["equity_spots"])
    eq_trades = {t for t, tr in trades.items() if hasattr(tr, "positions")}
    fx_trades = {t for t, tr in trades.items() if hasattr(tr, "positions") and any(p.currency == "JPY" for p in tr.positions)}
    all_trades = set(trades)

    def build(cal):
        return SimulationEngine(cal, trades, method="latin_hypercube", n_scenarios=N, seed=42, mpor_days=10, vm_lag_days=1)

    px = pd.read_csv(os.path.join(ROOT, "data", "raw", "backtest_prices.csv"), index_col=0, parse_dates=True)
    fx = px.pop("FX_USDJPY").ffill()
    scen = S.hypothetical(isins) + S.historical_windows(px.ffill(limit=5), fx, treasury.load_cmt_history(), isins)

    t0 = time.perf_counter()
    eng = build(calib)
    paths = eng.simulate_paths()
    ids, npv0 = reprice_all_parallel(eng, paths)
    npv0 = np.nan_to_num(npv0)
    print(f"base: {time.perf_counter() - t0:.0f}s", flush=True)
    res = {"n_scenarios": N, "ref_date": str(ref), "base": measure(eng, ids, npv0, ref), "scenarios": {}, "definitions": {}}
    for sc in scen:
        res["definitions"][sc["name"]] = {
            "kind": sc["kind"], "description": sc["description"], "window": sc.get("window"),
            "equity_return_min": min(sc["eq"].values()) if sc["eq"] else 0.0,
            "equity_return_median": float(np.median(list(sc["eq"].values()))) if sc["eq"] else 0.0,
            "equity_return_max": max(sc["eq"].values()) if sc["eq"] else 0.0,
            "fx_return": sc["fx"], "dy_tenors": None if sc["dy"] is None else list(sc["dy"][0]),
            "dy_bp": None if sc["dy"] is None else [x * 1e4 for x in sc["dy"][1]]}

    for sc in scen:
        t0 = time.perf_counter()
        bump = {"eq": {i: 1.0 + r for i, r in sc["eq"].items()}, "fx": 1.0 + sc["fx"]}
        if sc["dy"] is None:
            holders = (eq_trades if sc["eq"] else set()) | (fx_trades if sc["fx"] != 0 else set())
            bump["trades"] = holders
            (rows, arr), = reprice_bumps_parallel(eng, paths, [bump])
            npv_s, e_s = apply_rows(npv0, rows, arr), eng
        else:
            curve = S.shift_curve(calib["usd_curve"], *sc["dy"])
            cal2 = dict(calib, usd_curve=curve, hw=HullWhite1F(curve, calib["hw"].sigma, calib["hw"].a))
            e_s = build(cal2)
            p2 = e_s.simulate_paths()
            bump["trades"] = all_trades
            (rows, arr), = reprice_bumps_parallel(e_s, p2, [bump])
            npv_s = apply_rows(npv0.copy(), rows, arr)
        res["scenarios"][sc["name"]] = measure(e_s, ids, npv_s, ref)
        p = res["scenarios"][sc["name"]]["closeout"]["__portfolio__"]["MPE"]
        print(f"{sc['name']:20s} close-out portfolio MPE {p:,.0f}  ({time.perf_counter() - t0:.0f}s)", flush=True)
        json.dump(res, open(OUT, "w"))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
