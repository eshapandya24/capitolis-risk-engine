"""
SA-CCR EAD per counterparty for the ESF book (uncollateralized, no CSA data),
next to the Monte Carlo close-out exposure of Section 7.1.

    python scripts/run_sa_ccr.py

Inputs: t = 0 NPVs (data/processed/npv_2026-08-28.json from price_full_book_real_data.py),
live equity spots and USDJPY from the calibration. Writes data/processed/sa_ccr_results.json.
"""
import json
import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
OUT = os.path.join(ROOT, "data", "processed", "sa_ccr_results.json")


def main():
    from run_simulation import load_trades
    from risk_engine.models.calibration import build_calibration
    from risk_engine.exposure import sa_ccr as S

    ref = date(2026, 8, 28)
    calib = build_calibration(ref)
    trades = load_trades()
    npv = json.load(open(os.path.join(ROOT, "data", "processed", "npv_2026-08-28.json")))
    npv = npv["npv_by_trade"]
    items = S.build_items(trades, ref, calib["equity_spots"], calib["fx_spot"], lambda t: t.bond)
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
