"""
Regulatory CVA and SA-CVA capital for the ESF book.

Base case plus one bumped re-simulation per SA-CVA risk factor, all with the
SAME random numbers (common random numbers), so each sensitivity
s_k = [CVA(bumped) - CVA(base)] / shift  is clean of Monte Carlo noise.
Each run is cached in data/processed/sa_cva/ so an interrupted job resumes.

    python scripts/run_sa_cva.py [--scenarios 1000]
"""
import argparse
import copy
import json
import os
import sys
import time
from datetime import date

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "processed", "sa_cva")
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def bump_curve(curve, tenor_years, shift, tenors=(1, 2, 5, 10, 30)):
    """Zero-rate bump of `shift` at one SA-CVA IR tenor, triangular in
    maturity between neighbouring tenors (flat beyond the end tenors)."""
    from capitolis_pricers.curves import Curve
    ts = list(tenors)
    k = ts.index(tenor_years)

    def w(t):
        if k > 0 and t < ts[k - 1]:
            return 0.0
        if t <= ts[k]:
            return 1.0 if k == 0 else (t - ts[k - 1]) / (ts[k] - ts[k - 1])
        if k == len(ts) - 1:
            return 1.0
        return max(0.0, (ts[k + 1] - t) / (ts[k + 1] - ts[k]))

    t_p = [t for t in curve._t]
    lndf = [y - w(t) * shift * t for t, y in zip(curve._t, curve._lndf)]
    return Curve(curve.ref_date, t_p, [float(np.exp(y)) for y in lndf], basis=curve.basis)


def make_calib(calib, bump):
    """Copy of the calibration dict with one risk-factor bump applied."""
    from risk_engine.models.rates import HullWhite1F
    c = dict(calib)
    kind = bump[0]
    if kind == "base":
        return c
    c["gbm"] = copy.deepcopy(calib["gbm"])
    hw = calib["hw"]
    if kind == "ir_delta":
        c["hw"] = HullWhite1F(bump_curve(calib["usd_curve"], bump[1], 1e-4), hw.sigma, hw.a)
    elif kind == "ir_vega":
        c["hw"] = HullWhite1F(calib["usd_curve"], hw.sigma * 1.01, hw.a)
    elif kind == "fx_delta":
        c["gbm"].spots0["FX_USDJPY"] = calib["gbm"].spots0["FX_USDJPY"] * 1.01
    elif kind == "fx_vega":
        c["gbm"].vols["FX_USDJPY"] = calib["gbm"].vols["FX_USDJPY"] * 1.01
    elif kind in ("eq_delta", "eq_vega"):
        for isin in bump[2]:
            if kind == "eq_delta":
                c["gbm"].spots0[isin] = calib["gbm"].spots0[isin] * 1.01
            else:
                c["gbm"].vols[isin] = calib["gbm"].vols[isin] * 1.01
    return c


def key_of(bump):
    return "_".join(str(x) for x in bump[:2])


def run_case(calib, trades, n, bump):
    from risk_engine.simulation.engine import SimulationEngine
    from risk_engine.simulation.parallel import reprice_all_parallel
    from risk_engine.exposure.aggregate import netted_exposure_by_counterparty
    from risk_engine.exposure.cva import path_discount_factors, discounted_ee
    path = os.path.join(OUT, key_of(bump) + ".npz")
    if os.path.exists(path):
        z = np.load(path, allow_pickle=True)
        return z["times"], {c: z["dee_" + c] for c in ("CPTY_A", "CPTY_B", "CPTY_C")}
    cal = make_calib(calib, bump)
    eng = SimulationEngine(cal, trades, method="latin_hypercube", n_scenarios=n, seed=42)
    t0 = time.perf_counter()
    paths = eng.simulate_paths()
    ids, npv = reprice_all_parallel(eng, paths)
    npv = np.nan_to_num(npv)
    exp = netted_exposure_by_counterparty(ids, eng.trade_counterparty, npv)
    disc = path_discount_factors(paths["x_rate"], eng.times, eng.hw)
    dee = {c: discounted_ee(exp[c], disc) for c in exp}
    np.savez(path, times=np.array(eng.times), **{"dee_" + c: v for c, v in dee.items()})
    print(f"  {key_of(bump):20s} done in {time.perf_counter() - t0:.0f}s", flush=True)
    return np.array(eng.times), dee


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", type=int, default=1000)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    global OUT
    if args.tag:
        OUT = OUT + "_" + args.tag
    os.makedirs(OUT, exist_ok=True)

    from run_simulation import load_trades
    from risk_engine.models.calibration import build_calibration, _isin_to_ticker
    from risk_engine.models.credit import COUNTERPARTY_ASSUMPTIONS
    from risk_engine.market.credit_spreads import rating_spread_curve, RATING_SERIES, INVESTMENT_GRADE
    from risk_engine.market.equity_buckets import load_equity_buckets, RISK_WEIGHT, VEGA_RW_LARGE, VEGA_RW_OTHER
    from risk_engine.exposure.cva import cva
    from risk_engine.exposure import sa_cva as S

    ref = date(2026, 8, 28)
    calib = build_calibration(ref)
    trades = load_trades()
    eq = load_equity_buckets(_isin_to_ticker())
    buckets = {}
    for isin, v in eq.items():
        buckets.setdefault(v["bucket"], []).append(isin)

    bumps = [("base", "-")] + [("ir_delta", t) for t in S.IR_TENORS] + [("ir_vega", "USD"), ("fx_delta", "JPY"), ("fx_vega", "JPY")]
    bumps += [("eq_delta", b, tuple(names)) for b, names in sorted(buckets.items())]
    bumps += [("eq_vega", b, tuple(names)) for b, names in sorted(buckets.items())]
    print(f"{len(bumps)} simulations at N={args.scenarios} (common random numbers)", flush=True)
    res = {key_of(b): run_case(calib, trades, args.scenarios, b) for b in bumps}

    cptys = ["CPTY_A", "CPTY_B", "CPTY_C"]
    curves = {c: rating_spread_curve(COUNTERPARTY_ASSUMPTIONS[c]["rating"], ref, S.CCS_TENORS) for c in cptys}

    def total_cva(key, shift_curves=None):
        times, dee = res[key]
        cc = shift_curves or curves
        return sum(cva(dee[c], times, cc[c][0], cc[c][1]) for c in cptys)

    base = total_cva("base_-")
    out = {"n_scenarios": args.scenarios, "ref_date": str(ref), "ratings": {c: COUNTERPARTY_ASSUMPTIONS[c]["rating"] for c in cptys},
           "spread_curves_bp": {c: [float(x) * 1e4 for x in curves[c][1]] for c in cptys},
           "cva_by_cpty": {c: cva(res["base_-"][1][c], res["base_-"][0], *curves[c]) for c in cptys}, "cva_total": base}

    # CVA vs rating (analytic, same exposure)
    out["cva_vs_rating"] = {}
    for rt in RATING_SERIES:
        cr = rating_spread_curve(rt, ref, S.CCS_TENORS)
        out["cva_vs_rating"][rt] = sum(cva(res["base_-"][1][c], res["base_-"][0], *cr) for c in cptys)
    # CVA profile (cumulative by grid time) for a figure
    times, dee = res["base_-"]
    out["dee"] = {c: dee[c].tolist() for c in cptys}
    out["times"] = list(map(float, times))

    # ---- sensitivities
    sens = {"ir_delta": [(total_cva(f"ir_delta_{t}") - base) / 1e-4 for t in S.IR_TENORS],
            "ir_vega": (total_cva("ir_vega_USD") - base) / 0.01,
            "fx_delta": (total_cva("fx_delta_JPY") - base) / 0.01,
            "fx_vega": (total_cva("fx_vega_JPY") - base) / 0.01,
            "eq_delta": {b: (total_cva(f"eq_delta_{b}") - base) / 0.01 for b in buckets},
            "eq_vega": {b: (total_cva(f"eq_vega_{b}") - base) / 0.01 for b in buckets}}
    ccs = {}
    for c in cptys:
        for k, tk in enumerate(S.CCS_TENORS):
            sp = curves[c][1].copy()
            sp[k] += 1e-4
            bumped = dict(curves)
            bumped[c] = (curves[c][0], sp)
            ccs[f"{c}|{tk}"] = (total_cva("base_-", bumped) - base) / 1e-4
    sens["ccs_delta"] = ccs
    out["sensitivities"] = sens

    # ---- SA-CVA capital
    cap = {}
    ws = {"USD": sens["ir_delta"] * S.IR_RW}
    cap["ir_delta"], _ = S.aggregate({"USD": ws["USD"]}, {"USD": S.IR_RHO}, 0.5)
    cap["ir_vega"], _ = S.aggregate({"USD": [sens["ir_vega"] * S.IR_VEGA_RW]}, {"USD": np.eye(1)}, 0.5)
    cap["fx_delta"], _ = S.aggregate({"JPY": [sens["fx_delta"] * S.FX_DELTA_RW]}, {"JPY": np.eye(1)}, 0.6)
    cap["fx_vega"], _ = S.aggregate({"JPY": [sens["fx_vega"] * S.FX_VEGA_RW]}, {"JPY": np.eye(1)}, 0.6)
    keys, R = S.ccs_rho(cptys, S.CCS_TENORS)
    rw = S.CCS_RW[(2, "IG")]
    vec = np.array([sens["ccs_delta"][f"{n}|{t}"] * rw for n, t in keys])
    cap["ccs_delta"], _ = S.aggregate({2: vec}, {2: R}, 0.0)
    bs = sorted(buckets)
    cap["eq_delta"], _ = S.aggregate({b: [sens["eq_delta"][b] * RISK_WEIGHT[b]] for b in bs}, {b: np.eye(1) for b in bs}, S.eq_gamma(bs))
    vrw = {b: (VEGA_RW_LARGE if b <= 8 else VEGA_RW_OTHER) for b in bs}
    cap["eq_vega"], _ = S.aggregate({b: [sens["eq_vega"][b] * vrw[b]] for b in bs}, {b: np.eye(1) for b in bs}, S.eq_gamma(bs))
    out["capital_by_class"] = cap
    out["K_sa_cva"] = float(sum(cap.values()))
    out["RWA"] = out["K_sa_cva"] * 12.5
    out["K_sa_cva_m125"] = out["K_sa_cva"] * 1.25
    out["equity_buckets"] = {str(b): len(v) for b, v in buckets.items()}
    with open(os.path.join(ROOT, "data", "processed", "sa_cva_results%s.json" % (("_" + args.tag) if args.tag else "")), "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps({k: out[k] for k in ("cva_by_cpty", "cva_total", "capital_by_class", "K_sa_cva", "RWA")}, indent=1))


if __name__ == "__main__":
    main()
