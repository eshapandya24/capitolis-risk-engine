"""
Full simulation on Capitolis's specified exposure convention (kickoff deck
slides 8-9): a grid carrying BOTH the t-1bd variation-margin node and the
t+10bd close-out node around every reporting date, so

    exposure(t) = max( V(t+10bd) - V(t-1bd), 0 )

is computed from real simulated nodes rather than the interim substitution
in scripts/run_spec_exposure.py. Reports per trade and per counterparty
(slide 8), with EE / PFE99 / MPE.

    python scripts/run_spec_simulation.py [--scenarios 3000] [--include-maturing]
"""
import argparse
import json
import os
import sys
import time
from datetime import date

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, ROOT)
TD = os.path.join(ROOT, "trade_data")
U = os.path.join(TD, "underlyings")


def load_trades():
    from capitolis_pricers.underlyings_loader import load_equities, load_bonds
    from capitolis_pricers.trade_loader import load_equity_trs, load_bond_forward, load_bond_trs
    baskets = load_equities(os.path.join(U, "equities.csv"))
    bonds = load_bonds(os.path.join(U, "bonds.csv"))
    trades = {}
    trades.update(load_equity_trs(os.path.join(TD, "equity_trs.csv"), baskets))
    trades.update(load_bond_forward(os.path.join(TD, "bond_forward.csv"), bonds))
    trades.update(load_bond_trs(os.path.join(TD, "bond_trs.csv"), bonds))
    return trades


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scenarios", type=int, default=3000)
    p.add_argument("--method", default="latin_hypercube")
    p.add_argument("--confidence", type=float, default=0.99)
    p.add_argument("--curve-date", default="2026-08-28")
    p.add_argument("--mpor-days", type=int, default=10)
    p.add_argument("--vm-lag-days", type=int, default=1)
    p.add_argument("--include-maturing", action="store_true",
                    help="count a trade settling inside the window as a market move "
                         "(default: exclude it from both legs)")
    p.add_argument("--outdir", default=os.path.join(ROOT, "data", "processed", "spec_run"))
    args = p.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    exclude_maturing = not args.include_maturing

    from risk_engine.models.calibration import build_calibration
    from risk_engine.simulation.engine import SimulationEngine
    from risk_engine.exposure import spec_exposure as spec

    ref_date = date.fromisoformat(args.curve_date)
    print(f"calibrating at {ref_date}...", flush=True)
    calib = build_calibration(ref_date)
    trades = load_trades()

    eng = SimulationEngine(calib, trades, method=args.method, n_scenarios=args.scenarios,
                            seed=42, mpor_days=args.mpor_days, vm_lag_days=args.vm_lag_days)
    n_prev = sum(1 for m in eng.node_map.values() if m["prev"] is not None)
    n_la = sum(1 for m in eng.node_map.values() if m["lookahead"] is not None)
    print(f"grid: {len(eng.dates)} nodes, {len(eng.node_map)} reporting dates "
          f"({n_prev} with a t-{args.vm_lag_days}bd mark, {n_la} with a t+{args.mpor_days}bd close-out)",
          flush=True)

    t0 = time.perf_counter()
    paths = eng.simulate_paths()
    print(f"simulate_paths: {time.perf_counter() - t0:.2f}s", flush=True)

    t0 = time.perf_counter()
    from risk_engine.simulation.parallel import reprice_all_parallel
    trade_ids, npv = reprice_all_parallel(eng, paths)
    reprice_s = time.perf_counter() - t0
    print(f"reprice: {reprice_s:.1f}s ({reprice_s / args.scenarios * 1000:.2f} ms/scenario)", flush=True)

    np.savez_compressed(os.path.join(args.outdir, "spec_run.npz"), npv=npv)
    dates_s = [str(d) for d in eng.dates]
    trade_expiry = {tid: eng.trade_expiries[tid] for tid in trade_ids}
    meta = {"ref_date": str(ref_date), "dates": dates_s, "node_map": eng.node_map,
            "trade_ids": trade_ids, "trade_counterparty": eng.trade_counterparty,
            "trade_expiry": {k: str(v) for k, v in trade_expiry.items()},
            "n_scenarios": args.scenarios, "method": args.method,
            "mpor_days": args.mpor_days, "vm_lag_days": args.vm_lag_days,
            "exclude_maturing": exclude_maturing, "reprice_s": reprice_s}
    json.dump(meta, open(os.path.join(args.outdir, "spec_meta.json"), "w"), indent=1, default=str)

    # ---- exposure on the specified convention
    prev_node = {i: (m["prev"] if m["prev"] is not None else m["reporting"])
                 for i, m in eng.node_map.items()}
    reporting_dates = [dates_s[eng.node_map[i]["reporting"]] for i in range(len(eng.node_map))]
    one_year = np.array([(date.fromisoformat(d) - ref_date).days <= 365 for d in reporting_dates])

    by_cpty = spec.exposure_by_counterparty(
        trade_ids, eng.trade_counterparty, npv, eng.node_map, prev_node=prev_node,
        trade_expiry=trade_expiry, exclude_maturing=exclude_maturing, dates=eng.dates)

    result = {"convention": "exposure(t) = max(V(t+10bd) - V(t-1bd), 0)  [kickoff deck slides 8-9]",
              "mode": "FULL -- real t-1bd and t+10bd nodes on the simulated grid",
              "exclude_maturing": exclude_maturing, "horizon": "MPE and peak EE over reporting dates within one year of the reference date (slide 8)", "n_scenarios": args.scenarios,
              "method": args.method, "confidence": args.confidence,
              "ref_date": str(ref_date), "reporting_dates": reporting_dates,
              "by_counterparty": {}, "per_trade": {}}

    print(f"\n--- by counterparty (exclude_maturing={exclude_maturing}) ---")
    print(f"{'':14s} {'peak EE':>16s} {'MPE (peak PFE99)':>18s} {'MPE date':>12s}")
    port = None
    for cpty in sorted(by_cpty):
        arr = by_cpty[cpty]
        s = spec.summarize(arr, args.confidence, one_year)
        mpe_date = reporting_dates[int(np.argmax(s["PFE"]))]
        result["by_counterparty"][cpty] = {
            "EE_max": s["EE_max"], "MPE": s["MPE"], "MPE_date": mpe_date,
            "EE": s["EE"].tolist(), "PFE": s["PFE"].tolist(),
            "MedianExposure": s["MedianExposure"].tolist()}
        print(f"{cpty:14s} {s['EE_max']:>16,.0f} {s['MPE']:>18,.0f} {mpe_date:>12s}")
        port = arr if port is None else port + arr

    sp = spec.summarize(port, args.confidence, one_year)
    result["by_counterparty"]["__portfolio__"] = {
        "EE_max": sp["EE_max"], "MPE": sp["MPE"],
        "MPE_date": reporting_dates[int(np.argmax(sp["PFE"]))],
        "EE": sp["EE"].tolist(), "PFE": sp["PFE"].tolist(),
        "MedianExposure": sp["MedianExposure"].tolist()}
    print(f"{'PORTFOLIO':14s} {sp['EE_max']:>16,.0f} {sp['MPE']:>18,.0f} "
          f"{result['by_counterparty']['__portfolio__']['MPE_date']:>12s}")

    per_trade = spec.exposure_by_trade(trade_ids, npv, eng.node_map, prev_node=prev_node,
                                        trade_expiry=trade_expiry, exclude_maturing=exclude_maturing, dates=eng.dates)
    print(f"\n--- per trade ---")
    print(f"{'trade':12s} {'cpty':8s} {'MtM(t0)':>16s} {'peak EE':>14s} {'MPE':>14s}")
    for i, tid in enumerate(trade_ids):
        s = spec.summarize(per_trade[tid], args.confidence, one_year)
        mtm = float(npv[i, 0, 0])
        result["per_trade"][tid] = {"counterparty": eng.trade_counterparty[tid], "mtm_t0": mtm,
                                     "EE_max": s["EE_max"], "MPE": s["MPE"],
                                     "EE": s["EE"].tolist(), "PFE": s["PFE"].tolist()}
        print(f"{tid:12s} {eng.trade_counterparty[tid]:8s} {mtm:>16,.0f} "
              f"{s['EE_max']:>14,.0f} {s['MPE']:>14,.0f}")

    out = os.path.join(args.outdir, "spec_exposure.json")
    json.dump(result, open(out, "w"), indent=1)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
