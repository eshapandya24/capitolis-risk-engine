"""
Extra credit: a RISKY-bond sample trade priced with an issuer credit curve.

No CDS quotes were obtainable for any issuer, so the credit curve is a PROXY:
ICE BofA BBB option-adjusted spreads (FRED), with the credit-triangle
survival curve the pricing library provides (capitolis_pricers.credit,
recovery 40%). The sample is a long forward on a 5% BBB corporate bond
(trade_data/samples/), NOT part of the ESF book, and the results here do not
enter any other number in the report.

Reported: (i) the issuer credit charge at t = 0 (risk-free minus risky price)
and its spread sensitivity; (ii) the counterparty exposure of the trade with
and without issuer credit on the same simulated paths. Issuer spreads are
held deterministic in simulation (the curve is re-anchored at each node with
the same term structure).

    python scripts/run_risky_bond_sample.py
"""
import json
import os
import sys
from datetime import date

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
OUT = os.path.join(ROOT, "data", "processed", "risky_bond_sample.json")
SAMPLES = os.path.join(ROOT, "trade_data", "samples")
TENORS = (0.5, 1, 3, 5, 10)
RECOVERY = 0.40


def load_sample():
    from capitolis_pricers.underlyings_loader import load_bonds
    from capitolis_pricers.trade_loader import load_bond_forward
    bonds = load_bonds(os.path.join(SAMPLES, "bonds_risky.csv"))
    return load_bond_forward(os.path.join(SAMPLES, "bond_forward_risky.csv"), bonds)


def main():
    from capitolis_pricers.credit import CreditCurve
    from capitolis_pricers.market import MarketState
    from risk_engine.market.credit_spreads import rating_spread_curve
    from risk_engine.models.calibration import build_calibration
    from risk_engine.simulation.engine import SimulationEngine
    from risk_engine.simulation.parallel import reprice_all_parallel
    from risk_engine.exposure import spec_exposure as spec

    ref = date(2026, 8, 28)
    calib = build_calibration(ref)
    trades = load_sample()
    tid, tr = next(iter(trades.items()))
    tn, sp = rating_spread_curve("BBB", ref, TENORS)
    print("BBB proxy spreads (bp): " + ", ".join(f"{t}y {s * 1e4:.0f}" for t, s in zip(tn, sp)))

    def market(spreads):
        credit = {tr.bond.issuer: CreditCurve(ref, tn, spreads, RECOVERY)} if spreads is not None else {}
        return MarketState(ref_date=ref, reporting_ccy="USD", discount_curves={"USD": calib["usd_curve"]}, credit_curves=credit)

    npv_rf, npv_risky = tr.npv(market(None)), tr.npv(market(sp))
    npv_up = tr.npv(market(sp + 1e-4))
    clean_rf = tr.bond.forward_clean(calib["usd_curve"], tr.forward_date, None)
    clean_r = tr.bond.forward_clean(calib["usd_curve"], tr.forward_date, CreditCurve(ref, tn, sp, RECOVERY))
    res = {"trade": tid, "issuer": tr.bond.issuer, "notional": tr.notional, "forward_date": str(tr.forward_date),
           "bbb_spreads_bp": {str(t): float(s) * 1e4 for t, s in zip(tn, sp)}, "recovery": RECOVERY,
           "npv_risk_free": npv_rf, "npv_risky": npv_risky, "credit_charge": npv_rf - npv_risky,
           "cs01": npv_up - npv_risky, "forward_clean_risk_free": clean_rf, "forward_clean_risky": clean_r}
    print(f"t=0 NPV risk-free {npv_rf:,.0f}, risky {npv_risky:,.0f}; issuer credit charge {npv_rf - npv_risky:,.0f}; CS01 {npv_up - npv_risky:,.0f}")

    exp = {}
    for label, iss in (("risk_free", None), ("risky", {tr.bond.issuer: (list(tn), list(sp), RECOVERY)})):
        cal = dict(calib, issuer_spreads=iss) if iss else calib
        eng = SimulationEngine(cal, {tid: tr}, method="latin_hypercube", n_scenarios=1000, seed=42, mpor_days=10, vm_lag_days=1)
        paths = eng.simulate_paths()
        ids, npv = reprice_all_parallel(eng, paths)
        npv = np.nan_to_num(npv)
        prev = {i: (m["prev"] if m["prev"] is not None else m["reporting"]) for i, m in eng.node_map.items()}
        by = spec.exposure_by_counterparty(ids, {tid: "CPTY_S"}, npv, eng.node_map, prev_node=prev,
                                           trade_expiry=dict(eng.trade_expiries), exclude_maturing=True, dates=eng.dates)["CPTY_S"]
        ridx = [eng.node_map[i]["reporting"] for i in range(len(eng.node_map))]
        s = spec.summarize(by, 0.99)
        lvl = np.maximum(npv[0][ridx, :], 0.0)
        exp[label] = {"dates": [str(eng.dates[r]) for r in ridx], "closeout_EE": s["EE"].tolist(),
                      "closeout_PFE99": s["PFE"].tolist(), "level_EE": lvl.mean(1).tolist(),
                      "level_PFE99": np.quantile(lvl, 0.99, axis=1).tolist(), "npv_mean": npv[0][ridx, :].mean(1).tolist(),
                      "MPE99_closeout": float(s["PFE"].max())}
        print(f"{label}: close-out MPE99 {s['PFE'].max():,.0f}; level PFE99 peak {max(exp[label]['level_PFE99']):,.0f}")
    res["exposure"] = exp
    json.dump(res, open(OUT, "w"), indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
