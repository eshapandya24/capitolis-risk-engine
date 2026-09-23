"""
CVA, DVA and FVA for the ESF book on BOTH exposure definitions, from the
5,000-scenario close-out run (data/processed/spec_run/spec_run.npz) and the
same simulated paths (re-generated deterministically: same seed and grid).

    python scripts/run_xva.py

Writes data/processed/xva_results.json.
"""
import json
import os
import sys
from datetime import date

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
RUN = os.path.join(ROOT, "data", "processed", "spec_run")
OUT = os.path.join(ROOT, "data", "processed", "xva_results.json")
CPTYS = ("CPTY_A", "CPTY_B", "CPTY_C")
OWN_RATING = "BBB"


def main():
    from run_simulation import load_trades
    from risk_engine.models.calibration import build_calibration
    from risk_engine.simulation.engine import SimulationEngine
    from risk_engine.exposure import spec_exposure as spec
    from risk_engine.exposure.cva import path_discount_factors
    from risk_engine.exposure.sa_cva import CCS_TENORS
    from risk_engine.exposure.xva import xva_summary
    from risk_engine.market.credit_spreads import rating_spread_curve, RATING_SERIES
    from risk_engine.models.credit import COUNTERPARTY_ASSUMPTIONS

    meta = json.load(open(os.path.join(RUN, "spec_meta.json")))
    N = meta["n_scenarios"]
    ref = date.fromisoformat(meta["ref_date"])
    npv = np.load(os.path.join(RUN, "spec_run.npz"))["npv"]
    calib = build_calibration(ref)
    trades = load_trades()
    eng = SimulationEngine(calib, trades, method=meta["method"], n_scenarios=N, seed=42,
                           mpor_days=meta["mpor_days"], vm_lag_days=meta["vm_lag_days"])
    assert [str(d) for d in eng.dates] == meta["dates"], "grid differs from the cached run"
    paths = eng.simulate_paths()
    ids = meta["trade_ids"]
    assert npv.shape == (len(ids), len(eng.dates), N)
    npv = np.nan_to_num(npv)

    ridx = [eng.node_map[i]["reporting"] for i in range(len(eng.node_map))]
    times = np.array([eng.times[r] for r in ridx])
    disc = path_discount_factors(paths["x_rate"], eng.times, eng.hw)[:, ridx]   # (N, n_rep)
    prev = {i: (m["prev"] if m["prev"] is not None else m["reporting"]) for i, m in eng.node_map.items()}
    cpm = eng.trade_counterparty
    texp = dict(eng.trade_expiries)

    prof = {"closeout": {}, "level": {}}
    for side in ("pos", "neg"):
        by = spec.exposure_by_counterparty(ids, cpm, npv, eng.node_map, prev_node=prev, trade_expiry=texp,
                                           exclude_maturing=True, dates=eng.dates, side=side)
        for c in CPTYS:
            prof["closeout"].setdefault(c, {})[side] = (by[c] * disc.T).mean(axis=1)
    for c in CPTYS:
        idx = [i for i, t in enumerate(ids) if cpm[t] == c]
        v = npv[idx].sum(axis=0)[ridx, :]                                        # (n_rep, N)
        prof["level"][c] = {"pos": (np.maximum(v, 0) * disc.T).mean(axis=1),
                            "neg": (np.maximum(-v, 0) * disc.T).mean(axis=1)}

    def curve(r):
        return rating_spread_curve(r, ref, CCS_TENORS)

    own = curve(OWN_RATING)
    res = {"n_scenarios": N, "ref_date": str(ref), "own_rating": OWN_RATING, "times": times.tolist(),
           "ratings": {c: COUNTERPARTY_ASSUMPTIONS[c]["rating"] for c in CPTYS},
           "own_spread_bp": [float(x) * 1e4 for x in own[1]], "conventions": {}}
    for conv in ("closeout", "level"):
        by_c, tot = {}, {}
        for c in CPTYS:
            cc = curve(COUNTERPARTY_ASSUMPTIONS[c]["rating"])
            by_c[c] = xva_summary(prof[conv][c]["pos"], prof[conv][c]["neg"], times, cc, own)
        for k in by_c[CPTYS[0]]:
            tot[k] = float(sum(by_c[c][k] for c in CPTYS))
        # own-credit rating sensitivity (DVA and FVA move with it; CVA does not)
        sens = {}
        for r in RATING_SERIES:
            o = curve(r)
            row = {k: 0.0 for k in ("DVA", "FCA", "FBA", "FVA", "total_no_overlap")}
            for c in CPTYS:
                s = xva_summary(prof[conv][c]["pos"], prof[conv][c]["neg"], times,
                                curve(COUNTERPARTY_ASSUMPTIONS[c]["rating"]), o)
                for k in row:
                    row[k] += s[k]
            sens[r] = row
        res["conventions"][conv] = {
            "by_cpty": by_c, "total": tot, "own_rating_sensitivity": sens,
            "profiles": {c: {"EPE": prof[conv][c]["pos"].tolist(), "ENE": prof[conv][c]["neg"].tolist()} for c in CPTYS}}
        print(f"\n{conv}:")
        for c in CPTYS:
            b = by_c[c]
            print(f"  {c}: CVA {b['CVA']:,.0f}  DVA {b['DVA']:,.0f}  FCA {b['FCA']:,.0f}  FBA {b['FBA']:,.0f}  FVA {b['FVA']:,.0f}")
        print(f"  TOTAL: " + "  ".join(f"{k} {v:,.0f}" for k, v in tot.items()))
    json.dump(res, open(OUT, "w"), indent=1)
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
