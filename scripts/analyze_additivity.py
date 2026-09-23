"""
Why is the portfolio MPE close to the sum of the counterparty MPEs?

Reads the 5,000-scenario close-out run (data/processed/spec_run) and reports,
per reporting date: each counterparty's PFE99, their sum, the portfolio PFE99
and the ratio (diversification); the dependence between counterparty
exposures (rank correlation, tail co-exceedance); each counterparty's
contribution to the portfolio PFE99 (average of its exposure over the scenarios
that sit at the portfolio's 99th percentile); and the direction of each
counterparty's risk (equity delta and DV01 at t = 0).

    python scripts/analyze_additivity.py
"""
import json
import os
import sys
from datetime import date

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
RUN = os.path.join(ROOT, "data", "processed", "spec_run")
OUT = os.path.join(ROOT, "data", "processed", "additivity.json")
CP = ("CPTY_A", "CPTY_B", "CPTY_C")


def spearman(a, b):
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


def main():
    from risk_engine.exposure import spec_exposure as spec

    meta = json.load(open(os.path.join(RUN, "spec_meta.json")))
    npv = np.nan_to_num(np.load(os.path.join(RUN, "spec_run.npz"))["npv"])
    nm = {int(k): v for k, v in meta["node_map"].items()}
    dates = [date.fromisoformat(d) for d in meta["dates"]]
    ids = meta["trade_ids"]
    texp = {t: date.fromisoformat(v) for t, v in meta["trade_expiry"].items()}
    ref = date.fromisoformat(meta["ref_date"])
    prev = {i: (m["prev"] if m["prev"] is not None else m["reporting"]) for i, m in nm.items()}
    by = spec.exposure_by_counterparty(ids, meta["trade_counterparty"], npv, nm, prev_node=prev, trade_expiry=texp,
                                       exclude_maturing=True, dates=dates)
    port = sum(by[c] for c in CP)
    rep_dates = [dates[nm[i]["reporting"]] for i in range(len(nm))]
    one_year = [(d - ref).days <= 365 for d in rep_dates]
    n = port.shape[1]
    pf = {c: np.quantile(by[c], 0.99, axis=1) for c in CP}
    pp = np.quantile(port, 0.99, axis=1)
    ssum = sum(pf[c] for c in CP)
    res = {"n_scenarios": n, "dates": [str(d) for d in rep_dates], "one_year": one_year,
           "pfe99": {c: pf[c].tolist() for c in CP}, "pfe99_portfolio": pp.tolist(), "sum_of_pfe99": ssum.tolist(),
           "ratio": (pp / np.maximum(ssum, 1e-9)).tolist(), "mpe": {c: float(pf[c][one_year].max()) for c in CP},
           "mpe_date": {c: str(rep_dates[int(np.argmax(np.where(one_year, pf[c], -1)))]) for c in CP}}
    res["mpe_portfolio"] = float(pp[one_year].max())
    j = int(np.argmax(np.where(one_year, pp, -1)))
    res["portfolio_mpe_date"] = str(rep_dates[j])
    res["at_portfolio_mpe_date"] = {"pfe99": {c: float(pf[c][j]) for c in CP}, "sum": float(ssum[j]), "portfolio": float(pp[j])}

    # dependence at the portfolio-MPE date
    e = {c: by[c][j] for c in CP}
    res["rank_corr"] = {f"{a}-{b}": spearman(e[a], e[b]) for a, b in (("CPTY_A", "CPTY_B"), ("CPTY_A", "CPTY_C"), ("CPTY_B", "CPTY_C"))}
    q = {c: np.quantile(e[c], 0.99) for c in CP}
    res["tail_coexceedance"] = {}
    for a, b in (("CPTY_A", "CPTY_B"), ("CPTY_A", "CPTY_C"), ("CPTY_B", "CPTY_C")):
        hit_b = e[b] > q[b]
        res["tail_coexceedance"][f"{a}|{b}"] = float(np.mean(e[a][hit_b] > q[a])) if hit_b.any() else float("nan")
    res["prob_positive"] = {c: float(np.mean(e[c] > 0)) for c in CP}
    # Euler contribution: average exposure of each counterparty over scenarios at the portfolio's 99th percentile
    rank = np.argsort(np.argsort(port[j])) / n
    band = np.abs(rank - 0.99) <= 0.02
    res["contribution_at_p99"] = {c: float(e[c][band].mean()) for c in CP}
    res["contribution_at_p99"]["total"] = float(port[j][band].mean())
    # who is large when the portfolio is in its tail
    res["share_zero_in_tail"] = {c: float(np.mean(e[c][band] == 0)) for c in CP}

    # direction of each counterparty's risk at t = 0
    from run_simulation import load_trades
    from risk_engine.models.calibration import build_calibration
    from risk_engine.greeks.book import book_greeks
    calib = build_calibration(ref)
    trades = load_trades()
    bg = book_greeks(calib, trades)
    cpm = {t: tr.counterparty for t, tr in trades.items()}
    eqd = {c: 0.0 for c in CP}
    for isin, v in bg["equity"].items():
        for t, x in v["delta"].items():
            eqd[cpm[t]] += x
    dv01 = {c: sum(x for t, x in bg["rate"]["parallel"].items() if cpm[t] == c) for c in CP}
    fxd = {c: sum(x for t, x in bg["fx"]["delta"].items() if cpm[t] == c) for c in CP}
    res["direction"] = {"equity_delta_per_1pct": eqd, "dv01_per_bp": dv01, "fx_delta_per_1pct": fxd,
                        "trades": {t: {"type": type(tr).__name__, "counterparty": tr.counterparty,
                                        "side": getattr(tr, "direction", None) or getattr(tr, "position", None),
                                        "npv0": float(bg["npv"][t])} for t, tr in trades.items()}}
    cm = calib["corr_matrix"]
    eq = [c for c in cm.columns if c not in ("FX_USDJPY", "RATE_USD")]
    res["rate_equity_corr"] = {"mean": float(cm.loc[eq, "RATE_USD"].mean()), "min": float(cm.loc[eq, "RATE_USD"].min()),
                               "max": float(cm.loc[eq, "RATE_USD"].max())}
    json.dump(res, open(OUT, "w"), indent=1)
    print(json.dumps({k: res[k] for k in ("mpe", "mpe_portfolio", "portfolio_mpe_date", "at_portfolio_mpe_date", "rank_corr",
                                            "tail_coexceedance", "contribution_at_p99", "rate_equity_corr")}, indent=1))
    print(json.dumps(res["direction"]["equity_delta_per_1pct"]), json.dumps(res["direction"]["dv01_per_bp"]))


if __name__ == "__main__":
    main()
