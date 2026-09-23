"""
PCA factor model: what the factors are, what accuracy it gives up and how much
speed it adds (report Section 4.4 and 5).

  A. Explainability: variance explained by each factor, and the names and
     regions that load most on it.
  B. Approximation error on the actual book: the volatility of each netting
     set's equity position under the full correlation matrix versus the
     k-factor reconstruction.
  C. Speed: wall time of the correlated-shock step (full Cholesky versus k
     factors) for the reporting scenario count, against the cost of repricing.
  D. Sampling error: dispersion across seeds of a 1-month PFE99 of the
     equity positions, full-rank versus PCA (k = 3, 5, 10), Latin Hypercube.

    python scripts/run_pca_study.py
"""
import json
import os
import sys
import time
from datetime import date

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
OUT = os.path.join(ROOT, "data", "processed", "pca_study.json")
CPTYS = ("CPTY_A", "CPTY_B", "CPTY_C")


def positions_usd(trades, spots, fx):
    """{cpty: {isin: signed USD value at t0}} from the equity TRS trades."""
    out = {}
    for t in trades.values():
        if not hasattr(t, "positions"):
            continue
        sign = 1.0 if t.direction == "receive_equity" else -1.0
        d = out.setdefault(t.counterparty, {})
        for p in t.positions:
            d[p.isin] = d.get(p.isin, 0.0) + sign * p.shares * spots[p.isin] / (fx if p.currency == "JPY" else 1.0)
    return out


def main():
    from run_simulation import load_trades
    from risk_engine.models.calibration import build_calibration, _isin_to_ticker, _isin_currency
    from risk_engine.models.equity_factor_model import build_pca_factor_loadings, explained_variance_ratio, reconstruction_error
    from risk_engine.simulation.engine import SimulationEngine, _nearest_psd

    ref = date(2026, 8, 28)
    calib = build_calibration(ref)
    trades = load_trades()
    tick, cur = _isin_to_ticker(), _isin_currency()
    order = list(calib["factor_order"])
    corr = _nearest_psd(calib["corr_matrix"].loc[order, order].values)
    n = len(order)
    vals, vecs = np.linalg.eigh(corr)
    idx = np.argsort(vals)[::-1]
    vals, vecs = vals[idx], vecs[:, idx]
    label = lambda f: tick.get(f, f)
    res = {"n_factors_total": n, "eigenvalues": vals[:12].tolist(), "explained": {}, "factors": []}
    for k in (1, 3, 5, 10, 15, 20):
        res["explained"][str(k)] = float(vals[:k].sum() / vals.sum())
    for j in range(6):
        v = vecs[:, j] * (1 if vecs[:, j].sum() >= 0 else -1)
        o = np.argsort(v)
        jp = [i for i, f in enumerate(order) if cur.get(f) == "JPY"]
        us = [i for i, f in enumerate(order) if f in cur and cur.get(f) != "JPY"]
        res["factors"].append({
            "index": j + 1, "variance_share": float(vals[j] / vals.sum()),
            "top_positive": [(label(order[i]), float(v[i])) for i in o[::-1][:5]],
            "top_negative": [(label(order[i]), float(v[i])) for i in o[:5]],
            "mean_loading_us_names": float(np.mean(v[us])), "mean_loading_jpy_names": float(np.mean(v[jp])),
            "loading_fx": float(v[order.index("FX_USDJPY")]), "loading_rate": float(v[order.index("RATE_USD")])})

    # B. approximation error on the real positions
    pos = positions_usd(trades, calib["equity_spots"], calib["fx_spot"])
    vol = np.array([calib["gbm"].vols.get(f, 0.0) if f in cur else 0.0 for f in order])
    res["position_vol"] = {}
    for c, p in pos.items():
        w = np.array([p.get(f, 0.0) for f in order]) * vol
        full = float(np.sqrt(w @ corr @ w))
        row = {"full": full}
        for k in (3, 5, 10):
            B, d = build_pca_factor_loadings(corr, k)
            approx = B @ B.T + np.diag(d)
            row[str(k)] = float(np.sqrt(w @ approx @ w))
        res["position_vol"][c] = row
    res["reconstruction_error_max_abs"] = {}
    for k in (3, 5, 10):
        B, d = build_pca_factor_loadings(corr, k)
        res["reconstruction_error_max_abs"][str(k)] = float(reconstruction_error(corr, B, d))

    # C. speed of the correlated-shock step
    N = 5000
    speed = {}
    for mode, kw in (("full", {}), ("pca5", dict(corr_mode="factor", n_pca_factors=5)), ("pca10", dict(corr_mode="factor", n_pca_factors=10))):
        eng = SimulationEngine(calib, trades, method="latin_hypercube", n_scenarios=N, seed=42, mpor_days=10, vm_lag_days=1, **kw)
        ts = []
        for _ in range(3):
            t0 = time.perf_counter()
            eng._correlated_draws()
            ts.append(time.perf_counter() - t0)
        speed[mode] = {"draws_s": float(min(ts)), "n_steps": eng.n_steps, "n_factors": eng.n_factors}
    res["speed"] = speed
    reprice_s = None
    p = os.path.join(ROOT, "data", "processed", "spec_run", "spec_meta.json")
    if os.path.exists(p):
        reprice_s = json.load(open(p)).get("reprice_s")
    res["reprice_s_5000"] = reprice_s

    # D. sampling error of a 1-month PFE99 of the equity positions
    spots0 = calib["equity_spots"]
    x0 = calib["fx_spot"]

    def pfe99_all(eng):
        pth = eng.simulate_paths()
        k = int(np.argmin(np.abs(np.array(eng.times) - 30 / 365.0)))
        out = {}
        for c in CPTYS:
            if c not in pos:
                continue
            dv = np.zeros(eng.n_scenarios)
            for f, w in pos[c].items():
                r = np.exp(pth["ln_spot"][f][:, k]) / spots0[f]
                if cur.get(f) == "JPY":
                    r = r / (np.exp(pth["ln_fx"][:, k]) / x0)
                dv += w * (r - 1.0)
            out[c] = float(np.quantile(dv, 0.99))
        return out

    seeds = list(range(11, 21))
    stats_ = {}
    ref_q = pfe99_all(SimulationEngine(calib, trades, method="pseudo_random", n_scenarios=10000, seed=999))
    for mode, kw in (("full", {}), ("pca3", dict(corr_mode="factor", n_pca_factors=3)),
                     ("pca5", dict(corr_mode="factor", n_pca_factors=5)), ("pca10", dict(corr_mode="factor", n_pca_factors=10))):
        runs = [pfe99_all(SimulationEngine(calib, trades, method="latin_hypercube", n_scenarios=1000, seed=s, **kw)) for s in seeds]
        stats_[mode] = {}
        for c in ref_q:
            q = [r[c] for r in runs]
            stats_[mode][c] = {"mean": float(np.mean(q)), "std": float(np.std(q, ddof=1)), "bias_vs_reference": float(np.mean(q) - ref_q[c])}
        print(mode, {c: round(v["std"] / abs(ref_q[c]) * 100, 2) for c, v in stats_[mode].items()}, flush=True)
    res["sampling"] = {"reference_pfe99_full_pseudo_10000": ref_q, "n": 1000, "seeds": len(seeds), "modes": stats_}
    json.dump(res, open(OUT, "w"), indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
