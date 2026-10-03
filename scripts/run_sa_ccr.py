"""
SA-CCR EAD per counterparty for the ESF book (uncollateralized, no CSA data),
next to the Monte Carlo close-out exposure of Section 7.1.

    python scripts/run_sa_ccr.py

Inputs: the t = 0 NPVs, equity spots and USDJPY of the headline simulation snapshot
(data/processed/report/main_run.npz and meta.json, written by generate_report_data.py), so
the replacement cost and add-ons are on exactly the same snapshot as Sections 2.1 and 7.4
of the report. Writes data/processed/sa_ccr_results.json.
"""
import json
import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "data", "processed", "sa_ccr_results.json")


def main():
    import numpy as np
    from run_simulation import load_trades
    from risk_engine.exposure import sa_ccr as S

    ref = date(2026, 8, 28)
    trades = load_trades()
    rep = os.path.join(ROOT, "data", "processed", "report")
    meta = json.load(open(os.path.join(rep, "meta.json")))
    npv0 = np.load(os.path.join(rep, "main_run.npz"))["npv"][:, 0, :].mean(axis=1)  # t = 0 is deterministic
    npv = {tid: float(v) for tid, v in zip(meta["trade_ids"], npv0)}
    items = S.build_items(trades, ref, meta["equity_spots"], meta["fx_spot"], lambda t: t.bond)
    res = {"ref_date": str(ref), "alpha": S.ALPHA, "by_cpty": {}}
    tot = {"EAD": 0.0, "RC": 0.0, "PFE": 0.0}
    for c in sorted(items):
        v = sum(float(npv[t]) for t, tr in trades.items() if tr.counterparty == c)
        r = S.ead(v, items[c]["ir"], items[c]["eq"])
        r["n_ir_trades"], r["n_equity_positions"] = len(items[c]["ir"]), len(items[c]["eq"])
        res["by_cpty"][c] = r
        for k in tot:
            tot[k] += r[k]
        print(f"{c}: V {v:,.0f}  RC {r['RC']:,.0f}  addon IR {r['addon_ir']:,.0f}  addon EQ {r['addon_equity']:,.0f}  "
              f"mult {r['multiplier']:.3f}  PFE {r['PFE']:,.0f}  EAD {r['EAD']:,.0f}")
    res["total"] = tot
    print("TOTAL: " + "  ".join(f"{k} {v:,.0f}" for k, v in tot.items()))
    json.dump(res, open(OUT, "w"), indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
