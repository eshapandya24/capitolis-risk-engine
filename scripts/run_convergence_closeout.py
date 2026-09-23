"""
Convergence of the close-out exposure measures in the number of scenarios,
on the corrected engine: bootstrap resampling of the 5,000-scenario close-out
run (data/processed/spec_run). For each N, subsets of N scenarios are drawn
without replacement (finite-pool corrected) and the spread of the estimates of
EE, median PFE, PFE99 and the MPE is measured, by counterparty and for the
portfolio, at the date where the portfolio PFE99 peaks and for the peak
itself.

    python scripts/run_convergence_closeout.py
"""
import json
import os
from datetime import date

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN = os.path.join(ROOT, "data", "processed", "spec_run")
OUT = os.path.join(ROOT, "data", "processed", "convergence_closeout.json")
CP = ("CPTY_A", "CPTY_B", "CPTY_C")
NS = (250, 500, 1000, 2000, 3000, 4000)
B = 200


def main():
    from risk_engine.exposure import spec_exposure as spec
    meta = json.load(open(os.path.join(RUN, "spec_meta.json")))
    npv = np.nan_to_num(np.load(os.path.join(RUN, "spec_run.npz"))["npv"])
    nm = {int(k): v for k, v in meta["node_map"].items()}
    dates = [date.fromisoformat(d) for d in meta["dates"]]
    ref = date.fromisoformat(meta["ref_date"])
    texp = {t: date.fromisoformat(v) for t, v in meta["trade_expiry"].items()}
    prev = {i: (m["prev"] if m["prev"] is not None else m["reporting"]) for i, m in nm.items()}
    by = spec.exposure_by_counterparty(meta["trade_ids"], meta["trade_counterparty"], npv, nm, prev_node=prev,
                                       trade_expiry=texp, exclude_maturing=True, dates=dates)
    by["__portfolio__"] = sum(by[c] for c in CP)
    rep = [dates[nm[i]["reporting"]] for i in range(len(nm))]
    keep = [i for i, d in enumerate(rep) if (d - ref).days <= 365]
    N_pool = by["__portfolio__"].shape[1]
    j = keep[int(np.argmax(np.quantile(by["__portfolio__"][keep], 0.99, axis=1)))]
    rng = np.random.default_rng(0)
    res = {"pool": N_pool, "peak_date": str(rep[j]), "results": {}}
    for ent, arr in by.items():
        ref_pfe = float(np.quantile(arr[j], 0.99))
        ref_ee = float(arr[j].mean())
        ref_mpe = float(np.quantile(arr[keep], 0.99, axis=1).max())
        rows = []
        for n in NS:
            pfe, ee, mpe = [], [], []
            for _ in range(B):
                idx = rng.choice(N_pool, size=n, replace=False)
                pfe.append(np.quantile(arr[j, idx], 0.99))
                ee.append(arr[j, idx].mean())
                mpe.append(np.quantile(arr[np.ix_(keep, idx)], 0.99, axis=1).max())
            fpc = np.sqrt(max(1.0 - n / N_pool, 1e-12))       # finite-pool correction
            rows.append({"N": n, "rse_pfe99_pct": float(np.std(pfe, ddof=1) / abs(ref_pfe) / fpc * 100),
                         "rse_ee_pct": float(np.std(ee, ddof=1) / abs(ref_ee) / fpc * 100),
                         "rse_mpe_pct": float(np.std(mpe, ddof=1) / abs(ref_mpe) / fpc * 100)})
        res["results"][ent] = {"ref_pfe99": ref_pfe, "ref_ee": ref_ee, "ref_mpe": ref_mpe, "rows": rows}
        print(ent, [(r["N"], round(r["rse_pfe99_pct"], 2), round(r["rse_mpe_pct"], 2)) for r in rows], flush=True)
    json.dump(res, open(OUT, "w"), indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
