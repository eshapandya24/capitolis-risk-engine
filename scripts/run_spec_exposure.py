"""
Exposure on Capitolis's specified close-out-window convention (kickoff deck
slides 8-9), per trade and per counterparty -- see
src/risk_engine/exposure/spec_exposure.py for the formula.

Runs off the CACHED simulation in data/processed/report/main_run.npz, so it
needs no repricing. That cache was built with mpor_days=10, so the +10bd
close-out leg is real; the t-1bd margin leg is NOT in that grid, so this
runs in INTERIM mode (V(t) substituted for V(t-1bd)), which is biased low
by one business day of market move. Re-run scripts/run_simulation.py with
t-1bd nodes for the reportable figures.

    python scripts/run_spec_exposure.py [--confidence 0.99]
"""
import argparse
import json
import os
from datetime import date

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, ROOT)

from risk_engine.exposure import spec_exposure as spec


def _d(s):
    y, m, dd = s.split("-")
    return date(int(y), int(m), int(dd))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--confidence", type=float, default=0.99)
    p.add_argument("--cache", default=os.path.join(ROOT, "data", "processed", "report", "main_run.npz"))
    p.add_argument("--meta", default=os.path.join(ROOT, "data", "processed", "report", "meta.json"))
    p.add_argument("--out", default=os.path.join(ROOT, "data", "processed", "spec_exposure_interim.json"))
    args = p.parse_args()

    npv = np.load(args.cache, allow_pickle=True)["npv"]
    meta = json.load(open(args.meta))
    dates = [_d(s) for s in meta["dates"]]
    node_map = {int(k): v for k, v in meta["node_map"].items()}
    trade_ids = meta["trade_ids"]
    trade_cpty = meta["trade_counterparty"]
    trade_expiry = {k: _d(v) for k, v in meta["trade_expiry"].items()}

    reporting_dates = [meta["dates"][node_map[i]["reporting"]] for i in range(len(node_map))]
    print(f"cache: {npv.shape[0]} trades x {npv.shape[1]} nodes x {npv.shape[2]} scenarios, "
          f"{len(node_map)} reporting dates")
    print("MODE: INTERIM (t-1bd leg absent from cached grid -- biased low)\n")

    result = {"mode": "INTERIM -- V(t) substituted for V(t-1bd); biased low by one business day",
              "convention": "exposure(t) = max(V(t+10bd) - V(t-1bd), 0)  [slides 8-9]",
              "n_scenarios": int(npv.shape[2]), "confidence": args.confidence,
              "reporting_dates": reporting_dates}

    # ---- per counterparty, both maturity rules
    for label, excl in (("exclude_maturing", True), ("include_maturing", False)):
        by_cpty = spec.exposure_by_counterparty(
            trade_ids, trade_cpty, npv, node_map, prev_node=None,
            trade_expiry=trade_expiry, exclude_maturing=excl, dates=dates)
        block = {}
        port = None
        for cpty, arr in by_cpty.items():
            s = spec.summarize(arr, args.confidence)
            block[cpty] = {"EE_max": s["EE_max"], "MPE": s["MPE"],
                            "EE": s["EE"].tolist(), "PFE": s["PFE"].tolist(),
                            "MedianExposure": s["MedianExposure"].tolist()}
            port = arr if port is None else port + arr
        sp = spec.summarize(port, args.confidence)
        block["__portfolio__"] = {"EE_max": sp["EE_max"], "MPE": sp["MPE"],
                                   "EE": sp["EE"].tolist(), "PFE": sp["PFE"].tolist(),
                                   "MedianExposure": sp["MedianExposure"].tolist()}
        result[label] = block

        print(f"--- {label} ---")
        print(f"{'':14s} {'peak EE':>16s} {'MPE (peak PFE99)':>18s}")
        for cpty in sorted(by_cpty):
            print(f"{cpty:14s} {block[cpty]['EE_max']:>16,.0f} {block[cpty]['MPE']:>18,.0f}")
        print(f"{'PORTFOLIO':14s} {sp['EE_max']:>16,.0f} {sp['MPE']:>18,.0f}\n")

    # ---- per trade (slide 8: "computed per trade and aggregated up")
    per_trade = spec.exposure_by_trade(trade_ids, npv, node_map, prev_node=None)
    result["per_trade"] = {}
    print("--- per trade ---")
    print(f"{'trade':12s} {'cpty':8s} {'MtM(t0)':>16s} {'peak EE':>14s} {'MPE':>14s}")
    for tid in trade_ids:
        s = spec.summarize(per_trade[tid], args.confidence)
        mtm = float(npv[trade_ids.index(tid), 0, 0])
        result["per_trade"][tid] = {"counterparty": trade_cpty[tid], "mtm_t0": mtm,
                                     "EE_max": s["EE_max"], "MPE": s["MPE"],
                                     "EE": s["EE"].tolist(), "PFE": s["PFE"].tolist()}
        print(f"{tid:12s} {trade_cpty[tid]:8s} {mtm:>16,.0f} {s['EE_max']:>14,.0f} {s['MPE']:>14,.0f}")

    json.dump(result, open(args.out, "w"), indent=1)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
