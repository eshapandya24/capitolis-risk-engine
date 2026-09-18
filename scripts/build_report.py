"""
Builds docs/Capitolis_CCR_Complete_Report.pdf -- a from-scratch, fully
explained account of the Monte Carlo counterparty credit risk engine:
concepts, data, models, every modelling choice (with the alternatives that
were rejected), calibration, validation, and results, with figures produced
from the real simulation output.

Inputs: data/processed/report/* (written by scripts/generate_report_data.py),
the other data/processed/*.json artifacts, and a live build_calibration()
call for curves/vols/correlations. All text is pure ASCII (see report_lib.A).

    python scripts/build_report.py
"""
import json
import os
import pickle
import sys
import tempfile
from datetime import date, timedelta

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, ROOT)

from report_lib import (A, B, BODY, CAP, GOLD, GREY, TOCH, H1, H2, H3, NAVY, ORANGE, PAL, SMALL, TEAL, W,
                        PageBreak, Report, Spacer, callout, code, make_toc, P, tbl, plt)
from reportlab.lib.units import inch

PROC = os.path.join(ROOT, "data", "processed")
REP = os.path.join(PROC, "report")
OUT_PDF = os.path.join(ROOT, "docs", "Capitolis_CCR_Complete_Report.pdf")
CONF = 0.99


def m(x, d=1):
    return f"${x/1e6:,.{d}f}M"


def load_all():
    meta = json.load(open(os.path.join(REP, "meta.json")))
    z = np.load(os.path.join(REP, "main_run.npz"))
    D = {"meta": meta, "npv": z["npv"], "x_rate": z["x_rate"], "ln_fx": z["ln_fx"],
         "ln_spot": {k[8:]: z[k] for k in z.files if k.startswith("ln_spot_")}}
    D["trades"] = pickle.load(open(os.path.join(REP, "trades.pkl"), "rb"))
    D["node_map"] = {int(k): v for k, v in meta["node_map"].items()}
    n = len(D["node_map"])
    D["rep_idx"] = [D["node_map"][i]["reporting"] for i in range(n)]
    D["rep_dates"] = [date.fromisoformat(meta["dates"][j]) for j in D["rep_idx"]]
    D["rep_t"] = np.array([meta["times"][j] for j in D["rep_idx"]])
    return D


def exposures(D):
    from risk_engine.exposure.aggregate import netted_exposure_by_counterparty
    ids, cp = D["meta"]["trade_ids"], D["meta"]["trade_counterparty"]
    npv = np.nan_to_num(D["npv"])
    D["npv"] = npv
    full = netted_exposure_by_counterparty(ids, cp, npv)
    ri = D["rep_idx"]
    D["expo"] = {c: a[ri, :] for c, a in full.items()}
    D["expo"]["__portfolio__"] = sum(D["expo"][c] for c in sorted(full))
    return D


def prof(a):
    return {"EE": a.mean(1), "MED": np.quantile(a, 0.5, axis=1), "P95": np.quantile(a, 0.95, axis=1),
            "P99": np.quantile(a, CONF, axis=1)}


# ----------------------------------------------------------------- figures
def fig_concept_exposure():
    rng = np.random.default_rng(3)
    t = np.linspace(0, 1, 60)
    paths = np.cumsum(rng.normal(0, 1, (25, 60)), axis=1) * 0.35
    fig, ax = plt.subplots(1, 2, figsize=(7.2, 2.7))
    for p in paths:
        ax[0].plot(t, p, lw=0.7, alpha=0.7)
    ax[0].axhline(0, color="k", lw=1)
    ax[0].set_title("Simulated portfolio value V(t) on 25 scenarios")
    ax[0].set_xlabel("time"); ax[0].set_ylabel("value (net MTM)")
    ax[1].plot(t, np.maximum(paths, 0).T, lw=0.7, alpha=0.7)
    ax[1].plot(t, np.maximum(paths, 0).mean(0), color="k", lw=2, label="EE = mean of exposure")
    ax[1].set_title("Exposure = max(V, 0): only gains are at risk")
    ax[1].set_xlabel("time"); ax[1].legend()
    return fig


def fig_payoff_asym():
    v = np.linspace(-3, 3, 100)
    fig, ax = plt.subplots(figsize=(4.6, 2.5))
    ax.plot(v, np.maximum(v, 0), color=NAVY, lw=2)
    ax.plot(v, v, color=GREY, ls="--", lw=1)
    ax.set_xlabel("net portfolio value V (what the counterparty owes us if positive)")
    ax.set_ylabel("exposure")
    ax.set_title("Credit exposure is a call option on the netted MTM")
    return fig


def fig_measures_illustration(D):
    a = D["expo"]["__portfolio__"]
    j = int(np.argmin(np.abs(D["rep_t"] - 0.25)))
    x = a[j]
    fig, ax = plt.subplots(figsize=(6.6, 2.7))
    ax.hist(x / 1e6, bins=70, color=TEAL, alpha=0.8)
    for val, lab, c in ((x.mean(), "EE (mean)", NAVY), (np.median(x), "Median", GOLD),
                        (np.quantile(x, 0.95), "PFE95", ORANGE), (np.quantile(x, CONF), "PFE99", "#8B0000")):
        ax.axvline(val / 1e6, color=c, lw=1.8, label=f"{lab} = {val/1e6:,.1f}M")
    ax.set_xlabel(f"portfolio exposure at {D['rep_dates'][j]} (USD millions)")
    ax.set_ylabel("scenarios"); ax.legend()
    ax.set_title("One time slice of the exposure distribution and how each measure reads it")
    return fig


def fig_book(D):
    tr, meta = D["trades"], D["meta"]
    rows = []
    for t in meta["trade_ids"]:
        d = tr[t]
        notl = d.get("notional") or d.get("funding_notional") or 0
        rows.append((t, meta["trade_type"][t], meta["trade_counterparty"][t], meta["trade_expiry"][t]))
    return rows


def fig_book_timeline(D):
    meta = D["meta"]
    ref = date(2026, 8, 28)
    ids = meta["trade_ids"]
    fig, ax = plt.subplots(figsize=(6.8, 3.4))
    colmap = {"EquityTRS": NAVY, "BondForward": ORANGE, "BondTRS": TEAL}
    for i, t in enumerate(ids):
        typ = meta["trade_type"][t]
        end = date.fromisoformat(meta["trade_expiry"][t])
        d = D["trades"][t]
        start = d.get("start_date", ref)
        start = start if isinstance(start, date) else ref
        start = max(start, ref - timedelta(days=150))
        ax.barh(i, (end - start).days, left=(start - ref).days, color=colmap.get(typ, GREY), height=0.6)
        ax.text((end - ref).days + 5, i, meta["trade_counterparty"][t][-1], va="center", fontsize=6)
    ax.axvline(0, color="k", lw=1)
    ax.set_yticks(range(len(ids))); ax.set_yticklabels(ids, fontsize=6)
    ax.invert_yaxis(); ax.set_xlabel("days from valuation date 2026-08-28 (letter = counterparty A/B/C)")
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=c, label=k) for k, c in colmap.items()], loc="lower right")
    ax.set_title("Trade life spans: most of the book matures within ~4 months")
    return fig


def fig_t0_npv(D, npv0):
    meta = D["meta"]
    ids = meta["trade_ids"]
    fig, ax = plt.subplots(figsize=(6.8, 2.9))
    cols = {"CPTY_A": NAVY, "CPTY_B": TEAL, "CPTY_C": ORANGE}
    order = sorted(range(len(ids)), key=lambda i: (meta["trade_counterparty"][ids[i]], ids[i]))
    ax.bar(range(len(ids)), [npv0[i] / 1e6 for i in order],
           color=[cols[meta["trade_counterparty"][ids[i]]] for i in order])
    ax.set_xticks(range(len(ids))); ax.set_xticklabels([ids[i] for i in order], rotation=60, fontsize=6, ha="right")
    ax.set_ylabel("NPV today (USD M)")
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=c, label=k) for k, c in cols.items()])
    ax.set_title("Today's mark-to-market by trade (bar colour = netting set)")
    return fig


def fig_curve(calib):
    hw = calib["hw"]
    ts = np.linspace(0.02, 6.3, 120)
    zero = [-np.log(hw.discount0(t)) / t * 100 for t in ts]
    fwd = [hw.forward0(t) * 100 for t in ts]
    fig, ax = plt.subplots(figsize=(6.4, 2.6))
    ax.plot(ts, zero, color=NAVY, lw=2, label="zero rate (continuous)")
    ax.plot(ts, fwd, color=ORANGE, lw=1.3, label="instantaneous forward f(0,t)")
    ax.set_xlabel("maturity (years)"); ax.set_ylabel("%"); ax.legend()
    ax.set_title("Today's USD SOFR curve bootstrapped from CME SOFR futures (Databento)")
    return fig


def fig_vols(calib):
    vols = calib["gbm"].vols
    cur = calib["gbm"].currencies
    names = [k for k in vols if k not in ("FX_USDJPY", "RATE_USD")]
    names.sort(key=lambda k: vols[k])
    fig, ax = plt.subplots(figsize=(6.8, 3.0))
    ax.bar(range(len(names)), [vols[k] * 100 for k in names],
           color=[ORANGE if cur.get(k) == "JPY" else NAVY for k in names])
    ax.axhline(vols["FX_USDJPY"] * 100, color=GOLD, ls="--", label=f"USDJPY vol {vols['FX_USDJPY']*100:.1f}%")
    ax.set_xticks([]); ax.set_xlabel("37 equities sorted by volatility (orange = JPY-quoted)")
    ax.set_ylabel("annualised vol (%)"); ax.legend()
    ax.set_title("3-year realised lognormal volatility per equity")
    return fig


def fig_corr(calib):
    C = calib["corr_matrix"].values
    v = np.linalg.eigh(C)[1][:, -1]
    order = np.argsort(v)
    C2 = C[np.ix_(order, order)]
    fig, ax = plt.subplots(1, 2, figsize=(7.2, 3.1), gridspec_kw={"width_ratios": [1.15, 1]})
    im = ax[0].imshow(C2, cmap="RdBu_r", vmin=-1, vmax=1)
    ax[0].set_title("39x39 correlation matrix (sorted by 1st PC)"); ax[0].grid(False)
    fig.colorbar(im, ax=ax[0], fraction=0.046)
    off = C[np.triu_indices_from(C, 1)]
    ax[1].hist(off, bins=40, color=TEAL)
    ax[1].axvline(off.mean(), color="k", ls="--", label=f"mean {off.mean():.2f}")
    ax[1].set_title("Distribution of the 741 pairwise correlations"); ax[1].legend()
    ax[1].set_xlabel("correlation")
    return fig, off


def fig_cholesky_demo(calib):
    C = calib["corr_matrix"]
    names = list(C.columns)
    sub = C.values.copy()
    np.fill_diagonal(sub, 0)
    i, j = np.unravel_index(np.argmax(sub), sub.shape)
    rho = float(C.values[i, j])
    Cm = np.array([[1, rho], [rho, 1]])
    L = np.linalg.cholesky(Cm)
    rng = np.random.default_rng(0)
    z = rng.normal(size=(2500, 2))
    y = z @ L.T
    fig, ax = plt.subplots(1, 2, figsize=(6.6, 2.7))
    ax[0].scatter(z[:, 0], z[:, 1], s=3, alpha=0.4, color=GREY)
    ax[0].set_title("independent draws Z (corr ~ 0)")
    ax[1].scatter(y[:, 0], y[:, 1], s=3, alpha=0.4, color=NAVY)
    ax[1].set_title(f"Y = L Z  (target corr {rho:.2f}, sample {np.corrcoef(y.T)[0,1]:.2f})")
    for a in ax:
        a.set_xlim(-4, 4); a.set_ylim(-4, 4); a.set_aspect("equal")
    return fig, (names[i], names[j], rho)


def fig_scree(calib):
    from risk_engine.models.equity_factor_model import (build_pca_factor_loadings, explained_variance_ratio,
                                                        reconstruction_error)
    C = calib["corr_matrix"].values
    vals = np.sort(np.linalg.eigvalsh(C))[::-1]
    ks = list(range(1, 21))
    ev = [explained_variance_ratio(C, k) for k in ks]
    err_max = [reconstruction_error(C, *build_pca_factor_loadings(C, k)) for k in ks]
    err_fro = []
    for k in ks:
        B_, d_ = build_pca_factor_loadings(C, k)
        err_fro.append(np.linalg.norm(C - (B_ @ B_.T + np.diag(d_)), "fro"))
    fig, ax = plt.subplots(1, 3, figsize=(7.4, 2.6))
    ax[0].bar(range(1, 16), vals[:15], color=NAVY); ax[0].set_title("Eigenvalues (scree)"); ax[0].set_xlabel("component")
    ax[1].plot(ks, ev, marker="o", ms=3, color=TEAL); ax[1].set_title("Cumulative variance explained")
    ax[1].set_xlabel("k factors"); ax[1].set_ylim(0, 1)
    ax[2].plot(ks, err_max, marker="o", ms=3, color=ORANGE, label="max abs error")
    ax[2].plot(ks, err_fro, marker="s", ms=3, color=NAVY, label="Frobenius error")
    ax[2].set_title("Reconstruction error vs k"); ax[2].set_xlabel("k factors"); ax[2].legend()
    return fig, vals, ev, err_max


def fig_loadings(calib):
    from risk_engine.models.equity_factor_model import build_pca_factor_loadings
    C = calib["corr_matrix"].values
    B_, d_ = build_pca_factor_loadings(C, 5)
    fig, ax = plt.subplots(figsize=(6.4, 2.9))
    im = ax.imshow(B_.T, aspect="auto", cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_yticks(range(5)); ax.set_yticklabels([f"factor {i+1}" for i in range(5)])
    ax.set_xlabel("39 risk factors (37 equities, then USDJPY, then USD rate)"); ax.grid(False)
    fig.colorbar(im, ax=ax, fraction=0.03)
    ax.set_title("5-factor PCA loadings: factor 1 is a broad 'market' mode")
    return fig


def fig_rate_fan(D, calib):
    hw = calib["hw"]
    t = np.array(D["meta"]["times"])
    r = (D["x_rate"] + np.array([hw.alpha(tt) for tt in t])[None, :]) * 100
    q = np.quantile(r, [0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99], axis=0)
    fig, ax = plt.subplots(figsize=(6.6, 2.9))
    for i in range(25):
        ax.plot(t, r[i], lw=0.5, alpha=0.5, color=GREY)
    ax.fill_between(t, q[0], q[6], color=TEAL, alpha=0.15, label="1-99%")
    ax.fill_between(t, q[1], q[5], color=TEAL, alpha=0.25, label="5-95%")
    ax.fill_between(t, q[2], q[4], color=TEAL, alpha=0.4, label="25-75%")
    ax.plot(t, q[3], color=NAVY, lw=2, label="median")
    ax.plot(t, [hw.forward0(tt) * 100 for tt in t], color=ORANGE, ls="--", label="today's forward curve f(0,t)")
    ax.set_xlabel("years"); ax.set_ylabel("short rate (%)"); ax.legend(ncol=3)
    ax.set_title("Simulated USD short rate: Hull-White fan (3,000 scenarios)")
    return fig


def fig_fx_eq_fan(D, calib):
    t = np.array(D["meta"]["times"])
    fx = np.exp(D["ln_fx"])
    isin = max(D["ln_spot"], key=lambda k: calib["gbm"].vols[k])
    isin2 = min(D["ln_spot"], key=lambda k: calib["gbm"].vols[k])
    fig, ax = plt.subplots(1, 3, figsize=(7.4, 2.5))
    for a_, arr, ttl in ((ax[0], fx, "USDJPY"), (ax[1], np.exp(D["ln_spot"][isin2]), f"equity {isin2[:8]} (vol {calib['gbm'].vols[isin2]*100:.0f}%)"),
                         (ax[2], np.exp(D["ln_spot"][isin]), f"equity {isin[:8]} (vol {calib['gbm'].vols[isin]*100:.0f}%)")):
        q = np.quantile(arr, [0.05, 0.25, 0.5, 0.75, 0.95], axis=0)
        a_.fill_between(t, q[0], q[4], color=TEAL, alpha=0.25)
        a_.fill_between(t, q[1], q[3], color=TEAL, alpha=0.45)
        a_.plot(t, q[2], color=NAVY); a_.set_title(ttl); a_.set_xlabel("years")
    return fig


def fig_ou_negative():
    from capitolis_pricers.curves import flat_curve
    from risk_engine.models.rates import HullWhite1F
    hw = HullWhite1F(flat_curve("2026-08-28", -0.001), sigma=0.002758, a=0.0167)
    rng = np.random.default_rng(1)
    ts = np.linspace(0, 5, 61)
    n = 1500
    x = np.zeros((n, len(ts)))
    for k in range(1, len(ts)):
        x[:, k] = x[:, k - 1] * np.exp(-hw.a * (ts[k] - ts[k - 1])) + np.sqrt(
            hw.sigma ** 2 / (2 * hw.a) * (1 - np.exp(-2 * hw.a * (ts[k] - ts[k - 1])))) * rng.normal(size=n)
    r = (x + np.array([hw.alpha(t) for t in ts])[None, :]) * 100
    fig, ax = plt.subplots(figsize=(6.2, 2.6))
    q = np.quantile(r, [0.05, 0.5, 0.95], axis=0)
    ax.fill_between(ts, q[0], q[2], color=TEAL, alpha=0.3)
    ax.plot(ts, q[1], color=NAVY)
    ax.axhline(0, color="k", lw=1)
    ax.set_xlabel("years"); ax.set_ylabel("short rate (%)")
    ax.set_title("Hull-White started from a -0.10% curve: rates stay negative-capable (no floor)")
    return fig, float((r < 0).mean())


def fig_tona():
    from risk_engine.market.boj import fetch_tona_history
    s = fetch_tona_history() * 100
    fig, ax = plt.subplots(figsize=(6.8, 2.6))
    ax.plot(s.index, s.values, color=NAVY, lw=0.8)
    ax.axhline(0, color="k", lw=0.8)
    ax.fill_between(s.index, s.values, 0, where=s.values < 0, color=ORANGE, alpha=0.8, label=f"negative days ({int((s<0).sum())})")
    ax.set_ylabel("TONA (%)"); ax.legend()
    ax.set_title("Real Bank of Japan TONA, 1998-2026: near-zero and negative for decades")
    return fig, s


def fig_usd_jpy_rates():
    from risk_engine.market.sofr import fetch_history
    from risk_engine.market.boj import fetch_tona_history
    sofr = fetch_history("2018-04-01", "2030-01-01") * 100
    tona = fetch_tona_history() * 100
    df = pd.DataFrame({"SOFR": sofr, "TONA": tona}).dropna()
    d = df.diff().dropna()
    fig, ax = plt.subplots(1, 2, figsize=(7.2, 2.7))
    ax[0].plot(df.index, df["SOFR"], color=NAVY, label="SOFR (USD)")
    ax[0].plot(df.index, df["TONA"], color=ORANGE, label="TONA (JPY)")
    ax[0].set_title("Levels move with the global cycle"); ax[0].legend(); ax[0].set_ylabel("%")
    import matplotlib.dates as mdates
    ax[0].xaxis.set_major_locator(mdates.YearLocator(2)); ax[0].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax[1].scatter(d["SOFR"], d["TONA"], s=3, alpha=0.4, color=TEAL)
    ax[1].set_title(f"Daily CHANGES: corr = {d['SOFR'].corr(d['TONA']):+.3f}")
    ax[1].set_xlabel("dSOFR (pp)"); ax[1].set_ylabel("dTONA (pp)")
    return fig, df, d


def fig_jgb_vol():
    from risk_engine.market.mof_jgb import fetch_jgb_yield_history, TENOR_COLUMNS
    y = fetch_jgb_yield_history()
    ten = {"1Y": 1, "2Y": 2, "3Y": 3, "4Y": 4, "5Y": 5, "6Y": 6, "7Y": 7, "8Y": 8, "9Y": 9, "10Y": 10,
           "15Y": 15, "20Y": 20, "25Y": 25, "30Y": 30, "40Y": 40}
    fig, ax = plt.subplots(figsize=(6.0, 2.7))
    end = y.index.max()
    for yrs, c in ((1, ORANGE), (3, NAVY), (10, TEAL)):
        w = y[(y.index > end - pd.DateOffset(years=yrs)) & (y.index <= end)]
        xs, vs = [], []
        for col in TENOR_COLUMNS:
            d = w[col].dropna().diff().dropna()
            if len(d) > 30:
                xs.append(ten[col]); vs.append(d.std() * np.sqrt(252) * 1e4)
        ax.plot(xs, vs, marker="o", ms=3, color=c, label=f"{yrs}y window")
    ax.set_xlabel("JGB tenor (years)"); ax.set_ylabel("realised normal vol (bp/yr)"); ax.legend()
    ax.set_title("Real JGB yield vol RISES with tenor -- the opposite of USD's decay")
    return fig


def fig_hw_fit(calib):
    h = json.load(open(os.path.join(PROC, "hull_white_calibration.json")))
    rows = h["contracts"]
    ten = np.array([r["avg_tenor"] for r in rows]); vol = np.array([r["vol"] for r in rows]) * 1e4
    a, s = h["a"], h["sigma_from_fit"] * 1e4
    xs = np.linspace(ten.min() - 0.1, ten.max() + 0.1, 50)
    fig, ax = plt.subplots(1, 2, figsize=(7.2, 2.7))
    ax[0].scatter(ten, vol, color=NAVY, zorder=3, label="8 SOFR futures (realised vol)")
    ax[0].plot(xs, s * np.exp(-a * xs), color=ORANGE, label=f"fit: a = {a:.3f}, R2 = {h['r_squared']:.2f}")
    ax[0].set_xlabel("average tenor (years)"); ax[0].set_ylabel("vol (bp/yr)"); ax[0].legend()
    ax[0].set_title("Futures-vol-decay calibration (USD, real history)")
    sw = json.load(open(os.path.join(PROC, "hull_white_calibration_swaption.json")))
    labs = ["futures proxy\n(USD)", "swaption cube\n(USD)", "swaption cube\n(JPY)", "JGB yields\n(JPY)"]
    from risk_engine.models.hw_calibration import calibrate_jpy_mean_reversion_from_jgb_yields
    jg = calibrate_jpy_mean_reversion_from_jgb_yields(date(2026, 8, 28))
    from risk_engine.models.hw_calibration import calibrate_mean_reversion_from_swaptions
    sj = calibrate_mean_reversion_from_swaptions(currency="JPY")
    vals = [h["a"], sw["a"], sj["a"], jg["a"]]
    ax[1].bar(range(4), vals, color=[NAVY, TEAL, ORANGE, ORANGE])
    ax[1].axhline(0, color="k", lw=1)
    ax[1].set_xticks(range(4)); ax[1].set_xticklabels(labs, fontsize=6.5)
    ax[1].set_title("Fitted mean reversion a: USD sane, JPY negative")
    for i, v in enumerate(vals):
        ax[1].text(i, 0.003 if v < 0 else v + 0.002, f"{v:.3f}", ha="center", fontsize=7)
    return fig, h, sw, sj, jg


def fig_grid(D):
    from risk_engine.simulation.engine import build_time_grid, trade_event_dates
    from run_simulation import load_trades
    trades = load_trades()
    ref = date(2026, 8, 28)
    pil, _, _ = build_time_grid(ref, trades, grid_mode="pillar", include_trade_event_dates=False)
    mon, _, _ = build_time_grid(ref, trades, grid_mode="monthly", include_trade_event_dates=False)
    pe, _, _ = build_time_grid(ref, trades, grid_mode="pillar", include_trade_event_dates=True)
    ev = sorted({d for t in trades.values() for d in trade_event_dates(t)})
    ev = [d for d in ev if d >= ref]
    fig, ax = plt.subplots(figsize=(6.8, 2.5))
    for y, ds, c, lab in ((3, mon, GREY, f"monthly ({len(mon)})"), (2, pil, TEAL, f"pillar ({len(pil)})"),
                          (1, pe, NAVY, f"pillar + trade event dates ({len(pe)})"), (0, ev, ORANGE, f"trade event dates ({len(ev)})")):
        ax.scatter([(d - ref).days for d in ds], [y] * len(ds), s=14, color=c, label=lab)
    ax.set_yticks([]); ax.set_ylim(-0.6, 3.6); ax.set_xlabel("days from valuation date"); ax.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.28), fontsize=6.5)
    ax.set_title("Simulation date grids: dense near term, sparse far term, event dates forced in")
    return fig, len(mon), len(pil), len(pe)


def fig_vr():
    d = json.load(open(os.path.join(PROC, "variance_reduction_benchmark.json")))
    opt = d["option_study"]["results"]
    real = d["real_engine_check"]
    names = list(opt)
    fig, ax = plt.subplots(1, 2, figsize=(7.2, 2.7))
    ax[0].bar(range(len(names)), [opt[k]["rmse"] for k in names], color=PAL[:len(names)])
    ax[0].set_yscale("log"); ax[0].set_xticks(range(len(names))); ax[0].set_xticklabels([n.replace("_", "\n") for n in names], fontsize=6.5)
    ax[0].set_title("European call test: RMSE vs Black-Scholes (log)")
    ax[1].bar(range(len(names)), [real[k]["std"] for k in names], color=PAL[:len(names)])
    ax[1].set_xticks(range(len(names))); ax[1].set_xticklabels([n.replace("_", "\n") for n in names], fontsize=6.5)
    ax[1].set_title("Real 39-factor engine: PFE(1y) estimator std")
    return fig, opt, real


def fig_conv():
    c95 = json.load(open(os.path.join(PROC, "convergence_study.json")))
    c99 = json.load(open(os.path.join(PROC, "convergence_study_tail_pfe99.json")))
    r95 = [r for r in c95["results"] if r["N"] != c95["N_pool"]]
    r99 = [r for r in c99["results"] if r["N"] != c99["N_pool"]]
    fig, ax = plt.subplots(1, 3, figsize=(7.6, 2.7))
    n = [r["N"] for r in r95]
    ax[0].loglog(n, [r["PFE95_relative_se_pct"] for r in r95], marker="o", ms=3, color=NAVY, label="PFE95")
    ax[0].loglog(n, [r["EE_relative_se_pct"] for r in r95], marker="s", ms=3, color=TEAL, label="EE")
    ref = r95[0]["PFE95_relative_se_pct"] * np.sqrt(n[0] / np.array(n))
    ax[0].loglog(n, ref, ls="--", color=GREY, label="1/sqrt(N)")
    ax[0].set_title("Relative SE vs N (95%)"); ax[0].set_xlabel("scenarios N"); ax[0].set_ylabel("% relative SE"); ax[0].legend()
    n2 = [r["N"] for r in r99]
    ax[1].loglog(n2, [r["relative_se_pct"] for r in r99], marker="o", ms=3, color=ORANGE)
    ax[1].set_title("Relative SE vs N (PFE99)"); ax[1].set_xlabel("scenarios N")
    g = [r["marginal_se_improvement_pct"] for r in r99]
    ax[2].bar(range(1, len(n2)), g[1:], color=ORANGE)
    ax[2].set_xticks(range(1, len(n2))); ax[2].set_xticklabels([f"{x//1000 if x>=1000 else x}{'k' if x>=1000 else ''}" for x in n2[1:]], fontsize=6.5)
    ax[2].set_title("Marginal SE gain per step (PFE99)"); ax[2].set_xlabel("N reached")
    return fig, c95, c99, r99


def fig_profiles(D):
    cp = ["CPTY_A", "CPTY_B", "CPTY_C", "__portfolio__"]
    fig, axs = plt.subplots(2, 2, figsize=(7.2, 5.0))
    for ax, c in zip(axs.ravel(), cp):
        p = prof(D["expo"][c])
        x = np.array(D["rep_t"]) * 365.25
        ax.fill_between(x, p["MED"] / 1e6, p["P99"] / 1e6, color=TEAL, alpha=0.15)
        ax.plot(x, p["P99"] / 1e6, color="#8B0000", lw=1.6, label="PFE99")
        ax.plot(x, p["P95"] / 1e6, color=ORANGE, lw=1.2, label="PFE95")
        ax.plot(x, p["EE"] / 1e6, color=NAVY, lw=1.8, label="EE")
        ax.plot(x, p["MED"] / 1e6, color=GOLD, lw=1.8, label="Median")
        ax.set_title("Portfolio" if c == "__portfolio__" else c); ax.set_xlabel("days"); ax.set_ylabel("USD M")
    axs[0, 0].legend()
    fig.tight_layout()
    return fig


def fig_dists(D):
    a = D["expo"]["__portfolio__"]
    targets = [30, 60, 120, 240]
    fig, axs = plt.subplots(1, 4, figsize=(7.6, 2.4))
    for ax, tdays in zip(axs, targets):
        j = int(np.argmin(np.abs(D["rep_t"] * 365.25 - tdays)))
        x = a[j] / 1e6
        ax.hist(x, bins=50, color=TEAL)
        ax.axvline(np.median(x), color=GOLD, lw=1.5); ax.axvline(x.mean(), color=NAVY, lw=1.5)
        ax.axvline(np.quantile(x, CONF), color="#8B0000", lw=1.5)
        ax.set_title(f"{D['rep_dates'][j]}", fontsize=7); ax.set_xlabel("USD M")
        ax.set_yscale("log")
    return fig


def fig_prob_positive(D):
    fig, ax = plt.subplots(figsize=(6.4, 2.5))
    x = D["rep_t"] * 365.25
    for c, col in zip(["CPTY_A", "CPTY_B", "CPTY_C"], (NAVY, TEAL, ORANGE)):
        ax.plot(x, (D["expo"][c] > 0).mean(1) * 100, color=col, label=c)
    ax.set_xlabel("days"); ax.set_ylabel("% of scenarios with exposure > 0"); ax.legend()
    ax.set_title("How often is there anything to lose? (probability of positive exposure)")
    return fig


def fig_trade_heat(D):
    meta = D["meta"]; ids = meta["trade_ids"]
    npv = D["npv"][:, D["rep_idx"], :].mean(axis=2) / 1e6
    order = sorted(range(len(ids)), key=lambda i: (meta["trade_counterparty"][ids[i]], ids[i]))
    fig, ax = plt.subplots(figsize=(6.8, 3.3))
    lim = np.abs(npv).max()
    im = ax.imshow(npv[order], aspect="auto", cmap="RdBu_r", vmin=-lim, vmax=lim)
    ax.set_yticks(range(len(ids))); ax.set_yticklabels([ids[i] + " " + meta["trade_counterparty"][ids[i]][-1] for i in order], fontsize=6)
    ax.set_xticks(range(0, len(D["rep_dates"]), 4))
    ax.set_xticklabels([str(D["rep_dates"][i])[2:7] for i in range(0, len(D["rep_dates"]), 4)], fontsize=6)
    ax.grid(False); fig = ax.figure; fig.colorbar(im, ax=ax, fraction=0.03, label="mean NPV USD M")
    ax.set_title("Expected NPV by trade through time: trades drop to zero as they mature")
    return fig


def fig_mpor(D):
    from risk_engine.exposure.collateral import mpor_vs_uncollateralized_comparison
    meta = D["meta"]
    cmp_ = mpor_vs_uncollateralized_comparison(meta["trade_ids"], meta["trade_counterparty"], D["npv"], D["node_map"], D["rep_dates"], 0.0, CONF)
    cp = ["CPTY_A", "CPTY_B", "CPTY_C"]
    fig, ax = plt.subplots(1, 2, figsize=(7.2, 2.7))
    w = 0.38
    u = [cmp_["uncollateralized"][c]["MPE"] / 1e6 for c in cp]
    mp = [cmp_["mpor_shifted"][c]["MPE"] / 1e6 for c in cp]
    ax[0].bar(np.arange(3) - w / 2, u, w, color=NAVY, label="uncollateralized")
    ax[0].bar(np.arange(3) + w / 2, mp, w, color=TEAL, label="MPOR-shifted, full VM")
    ax[0].set_xticks(range(3)); ax[0].set_xticklabels(cp); ax[0].set_ylabel("MPE (PFE99 peak), USD M"); ax[0].legend()
    ax[0].set_title("Hypothetical CSA: max PFE99")
    x = D["rep_t"] * 365.25
    ax[1].plot(x, cmp_["uncollateralized"]["CPTY_C"]["PFE"] / 1e6, color=NAVY, label="uncollateralized")
    ax[1].plot(x, cmp_["mpor_shifted"]["CPTY_C"]["PFE"] / 1e6, color=TEAL, label="MPOR-shifted")
    ax[1].plot(x, cmp_["mpor_shifted"]["CPTY_C"]["MedianExposure"] / 1e6, color=GOLD, label="MPOR median")
    ax[1].set_title("CPTY_C PFE99 profile"); ax[1].set_xlabel("days"); ax[1].legend()
    return fig, cmp_, cp, u, mp


def fig_factor_cmp():
    from risk_engine.exposure.aggregate import netted_exposure_by_counterparty, portfolio_exposure
    cm = json.load(open(os.path.join(REP, "cmp_meta.json")))
    out = {}
    for key, f in (("full", "cmp_full_5.npz"), ("k=3", "cmp_factor_3.npz"), ("k=5", "cmp_factor_5.npz"), ("k=10", "cmp_factor_10.npz")):
        npv = np.nan_to_num(np.load(os.path.join(REP, f))["npv"])
        ex = portfolio_exposure(netted_exposure_by_counterparty(cm["trade_ids"], cm["trade_counterparty"], npv))
        out[key] = {"EE": ex.mean(1), "P99": np.quantile(ex, CONF, axis=1)}
    fig, ax = plt.subplots(1, 2, figsize=(7.2, 2.7))
    for (k, v), c in zip(out.items(), (NAVY, ORANGE, TEAL, GOLD)):
        ax[0].plot(v["EE"] / 1e6, color=c, label=k); ax[1].plot(v["P99"] / 1e6, color=c, label=k)
    ax[0].set_title("Portfolio EE: full-rank vs PCA factor model"); ax[1].set_title("Portfolio PFE99")
    ax[0].set_xlabel("time node"); ax[1].set_xlabel("time node"); ax[0].set_ylabel("USD M"); ax[0].legend()
    mpe = {k: float(v["P99"].max()) for k, v in out.items()}
    ee_peak = {k: float(v["EE"].max()) for k, v in out.items()}
    return fig, mpe, ee_peak, cm["n"]


# ------------------------------------------------------------------ report
def main():
    from datetime import date as _d
    from risk_engine.models.calibration import build_calibration
    D = exposures(load_all())
    calib = build_calibration(_d(2026, 8, 28))
    meta = D["meta"]
    tmp = tempfile.mkdtemp(prefix="ccrfig_")
    doc = Report(OUT_PDF, "Monte Carlo Counterparty Credit Risk Engine - Complete Report", tmp)
    S = []
    def add(x):
        if isinstance(x, (list, tuple)):
            S.extend(x)
        else:
            S.append(x)

    ids = meta["trade_ids"]
    npv0 = D["npv"][:, 0, :].mean(axis=1)  # t=0 is deterministic
    tot = prof(D["expo"]["__portfolio__"])
    mpe99 = float(tot["P99"].max()); j_mpe = int(tot["P99"].argmax())
    per = {c: prof(D["expo"][c]) for c in ("CPTY_A", "CPTY_B", "CPTY_C")}

    # ---------- cover + exec summary
    add(Spacer(1, 0.6 * inch))
    add(P("Monte Carlo Counterparty Credit Risk Engine", ParagraphStyleTitle()))
    add(P("Complete report: concepts, data, models, modelling choices, validation and results", ParagraphStyleSub()))
    add(P("Capitolis x Berkeley MFE industry project | Valuation date 2026-08-28 | Exposure measures at the 99th percentile", SMALL))
    add(Spacer(1, 0.2 * inch))
    add(callout(
        f"<b>What this document is.</b> A start-to-finish explanation, assuming no prior knowledge, of how we measure the "
        f"credit risk of Capitolis' equity-swap-financing (ESF) derivatives book: what the risk is, what the trades are, what "
        f"market data we used, how we simulate the future, every modelling choice we made and the alternatives we rejected, how "
        f"we checked that the engine is right, and what it says about the book. Every number is either measured from the real "
        f"engine on real market data or is an explicitly labelled assumption."))
    add(P("<b>Headline results</b> (3,000 Latin-Hypercube scenarios, uncollateralized book, PFE at the 99th percentile):", BODY))
    ce0 = {c: float(per[c]["EE"][0]) for c in per}
    add(tbl([["Measure", "Value", "Meaning"],
             ["Current exposure today (portfolio)", m(tot["EE"][0]), "What we would lose today if every counterparty defaulted now, after netting"],
             ["Peak EE (portfolio)", f"{m(tot['EE'].max())} at {D['rep_dates'][int(tot['EE'].argmax())]}", "Highest average future exposure"],
             ["Peak median exposure", f"{m(tot['MED'].max())} at {D['rep_dates'][int(tot['MED'].argmax())]}", "Typical (50th percentile) exposure at its worst date"],
             ["Maximum PFE99 (MPE)", f"{m(mpe99)} at {D['rep_dates'][j_mpe]}", "Worst plausible (99%) exposure over the life of the book"],
             ["Where the risk sits", f"{ce0['CPTY_C']/max(tot['EE'][0],1)*100:.0f}% of today's exposure is CPTY_C", "One $500M bond forward (BF_0003) dominates"],
             ["Time profile", "Most exposure disappears by ~Dec 2026", "Trades mature; a small Bond-TRS tail runs to Jan 2028"]],
            widths=[2.3, 2.0, 3.4]))
    add(Spacer(1, 6))
    add(P("<b>Choices we finally made</b> (each is justified in Section 8):", BODY))
    add(B([
        "Model: Monte Carlo under the risk-neutral measure. USD short rate = one-factor Hull-White (exact fit to today's SOFR curve); equities and USDJPY = correlated geometric Brownian motion driven by the simulated rate.",
        "Correlation: one static 39x39 matrix from 613 aligned daily returns, applied through a Cholesky factor (default); PCA factor model (5 factors) offered as an alternative.",
        "Scenarios: 3,000 Latin-Hypercube paths for reporting (the best variance-reduction method we measured); 10,000-15,000 if PFE99 must be tight to 0.2%.",
        "Dates: standard market pillar dates (O/N ... 10Y) plus every trade's own reset/maturity date forced onto the grid.",
        "Mean reversion a: USD 0.0167 from the swaption cube; JPY falls back to the USD value because real JPY vol rises with tenor (two independent sources).",
        "JPY: a real negative-rate-capable Hull-White factor exists (sigma from real TONA, correlation to USD rate calibrated at ~0), but it is not yet driving JPY equity drift.",
        "Uncollateralized by default (no CSA data); an MPOR-shifted collateralized calculation is built and demonstrated as a hypothetical."]))
    add(PageBreak())
    toc = make_toc()
    add(P("Contents", TOCH)); add(toc); add(PageBreak())

    # ---------- 1 concepts
    add(P("1. The problem from scratch", H1))
    add(P("1.1 What is counterparty credit risk?", H2))
    add(P("A derivative is a contract whose value changes as markets move. If we hold a contract with positive value to us, the "
          "counterparty owes us that value. If the counterparty then defaults, we lose (some of) it. <b>Counterparty credit "
          "risk (CCR)</b> is that loss risk. It is not the same as market risk: market risk is about our profit and loss moving; "
          "CCR is about whether the other side can pay when the contract is in our favour."))
    add(P("Two properties make CCR different from ordinary risk measures:"))
    add(B(["<b>It is one-sided.</b> If a contract is worth -5M to us we owe them; their default does not cost us that 5M back. "
           "So exposure is max(V, 0), a call option on the value (Figure 1).",
           "<b>It is about the future.</b> A default can happen at any date, so what matters is not today's value but the "
           "distribution of what the book could be worth on every future date. That needs simulation."]))
    add(doc.figure(fig_payoff_asym(), "Exposure is the positive part of the net value V. Negative value is not a credit exposure."))
    add(P("1.2 Netting", H2))
    add(P("Trades with the same counterparty under one legal netting agreement are combined before applying max(V,0): a +10M trade "
          "and a -6M trade give exposure 4M, not 10M. Netting never crosses counterparties. The portfolio exposure is therefore "
          "the <i>sum over counterparties</i> of each counterparty's own max(sum of trade values, 0)."))
    add(P("1.3 The four measures reported", H2))
    add(tbl([["Measure", "Definition", "How to read it"],
             ["Exposure profile V+(t)", "max(net MTM, 0) at each future date t, in each simulated scenario", "The raw object; everything below summarises its distribution across scenarios"],
             ["EE (Expected Exposure)", "Mean of exposure across scenarios at date t", "Average loss if default happens at t; used for pricing credit charges (CVA)"],
             ["Median exposure", "50th percentile of exposure across scenarios at date t", "The typical scenario. Exposure is floored at zero: the median is below EE when exposure is right-skewed (most scenarios small, a few large) and can be exactly zero when most scenarios are out of the money; it can sit slightly above EE when the book is almost always in the money, as for the dominant CPTY_C forward"],
             ["PFE (Potential Future Exposure)", f"The {int(CONF*100)}th percentile of exposure at date t", "A worst-plausible level: in 99 of 100 scenarios exposure at t is below it. Used for limits"],
             ["MPE (Maximum PFE)", "Peak of the PFE curve over all dates", "One number to set a counterparty limit against"]],
            widths=[1.5, 2.6, 3.6]))
    add(P("<b>Confidence level.</b> Throughout this report PFE means the <b>99th percentile</b> (an earlier stretch of this project "
          "briefly used 99.9%; that was a mistake and everything was re-run at 99%). The code default is now 0.99 everywhere; "
          "95% is quoted only where a study needs to be comparable with earlier work, and is labelled PFE95."))
    add(doc.figure(fig_concept_exposure(), "Left: simulated values of a portfolio through time. Right: the same paths after applying max(V,0); EE is their average."))
    add(doc.figure(fig_measures_illustration(D), "The real portfolio exposure distribution ~3 months out, with EE, median, PFE95 and PFE99 marked. The long right tail is why the mean, median and percentiles differ so much."))
    add(P("1.4 Why Monte Carlo", H2))
    add(P("The value of the book at a future date depends on the future levels of ~40 market variables (37 stock prices, USDJPY, "
          "interest rates) that move together. There is no closed formula for the distribution of a netted, path-dependent-schedule "
          "book. Monte Carlo solves this by: (1) simulating thousands of joint futures for all the variables; (2) fully re-pricing every "
          "trade in every simulated future at every date; (3) netting; (4) reading off the distribution. The cost is that the answer has "
          "sampling noise, which we measure and control (Sections 5.4 and 5.5)."))
    add(P("1.5 Real-world versus risk-neutral simulation", H2))
    add(P("Simulating under the <i>risk-neutral</i> measure (drift = short rate minus dividends) is the pricing-consistent choice used for "
          "CVA and for exposure numbers that must be consistent with today's market prices. The alternative, real-world (physical) drift, "
          "is used for regulatory PFE limits and would add a risk premium to the drifts. We use risk-neutral because it needs no extra "
          "unobservable inputs and is verified by a martingale test (Section 9). Because the horizon is short (under two years) and most "
          "positions are financed at the same rates, the difference between the two drifts is small relative to volatility."))
    add(PageBreak())

    # ---------- 2 book
    add(P("2. The trade book", H1))
    add(P("The book has <b>16 trades</b> with <b>3 counterparties</b> (CPTY_A, CPTY_B, CPTY_C), referencing 37 unique equities (%d USD-quoted, %d JPY-quoted) and 5 US Treasury bonds. Trade files are supplied by Capitolis in trade_data/." % (sum(1 for v in meta["currencies"].values() if v != "JPY"), sum(1 for v in meta["currencies"].values() if v == "JPY"))))
    add(P("2.1 The three instruments", H2))
    add(P("<b>Equity Total Return Swap (TRS).</b> One party pays the total return of a basket of shares (price change plus dividends) and receives a "
          "funding leg (SOFR plus a spread, or a fixed rate) on a financed amount. Value = equity leg minus funding leg:"))
    add(code("equity leg  = sum_i shares_i * DF(end) * (F_i(end) - basis_i)     F(t) = S(t)/DF(end)\n"
             "funding leg = sum_k rate_k * Notional * tau_k * DF(t_k)            rate_k = SOFR_fwd + spread  (or fixed)\n"
             "NPV         = equity leg - funding leg"))
    add(P("Eight of these (EQTRS_0001-0008), all 'pay_equity' from our side, so we are long the funding leg and short the equity return: "
          "our value rises when the shares fall. Two are JPY <i>compo</i> trades: both legs settle in USD but the equity leg pays the return of the USD "
          "value of a JPY share (S_JPY x USDJPY), so equity and FX risk both matter."))
    add(P("<b>Bond Forward.</b> An agreement to sell/buy a Treasury at a fixed clean price on a future date: NPV = sign x (notional/par) x DF(T) x "
          "(forward clean price - strike). The forward price is the spot financed at the repo rate less coupons in the window. Four of these, all short. "
          "BF_0003 has a 500M notional and dominates CPTY_C."))
    add(P("<b>Bond TRS.</b> Same idea as an equity TRS but on a bond: return leg (price change plus coupons) versus a funding leg over a reset schedule. Four of these."))
    rows = [["Trade", "Type", "Counterparty", "Ends", "Today's NPV"]]
    for i, t in enumerate(ids):
        rows.append([t, meta["trade_type"][t], meta["trade_counterparty"][t], meta["trade_expiry"][t], f"{npv0[i]:,.0f}"])
    add(tbl(rows, widths=[1.3, 1.2, 1.1, 1.1, 1.5]))
    add(Spacer(1, 6))
    add(doc.figure(fig_book_timeline(D), "Life span of every trade. Nearly all exposure will therefore disappear within four months; only BTRS_0001 and EQTRS_0008 run past mid-2027."))
    add(doc.figure(fig_t0_npv(D, npv0), "Today's mark-to-market per trade. CPTY_C's total is dominated by BF_0003 (+101M); CPTY_B nets to a small negative, so it has zero exposure today."))
    add(P("2.2 Pricing library (the 'contract')", H2))
    add(P("The trades are priced by capitolis_pricers, a self-contained standard-library re-implementation of QuantLib/ORE-style discounted cash flows supplied "
          "with the project. Every pricer is a pure function <font face='Courier'>npv = pricer.npv(MarketState)</font>. Our simulation therefore never contains pricing logic of its own: "
          "at every (scenario, date) we build a <font face='Courier'>MarketState</font> from simulated inputs (a discount curve, equity spots, an FX curve) and call the same "
          "<font face='Courier'>.npv()</font>. This is a deliberate design choice: the pricers were independently reviewed (docs/notes/pricer_review.md), so any error "
          "in the exposure numbers cannot hide inside re-implemented pricing."))
    add(PageBreak())

    # ---------- 3 data
    add(P("3. Market data: what we used and why", H1))
    add(P("Every risk factor needs both a <i>starting value</i> and <i>dynamics</i> (volatility, correlation, mean reversion). We prefer real, verifiable data; "
          "where none exists we use a labelled assumption."))
    add(tbl([["Input", "Source", "Used for", "Note"],
             ["USD discount curve", "Databento: CME SR3/SR1 SOFR futures (33 live contracts), bootstrapped by us", "Discounting, forwards, Hull-White fit", "Validated against Treasury.gov par curve (spread 13bp at 1M to 46bp at 10Y)"],
             ["37 equity spots and dividend yields", "yfinance", "GBM start values and drift", "Keyed by ISIN; BRK.B ticker mismatch found and fixed"],
             ["USDJPY spot", "yfinance", "FX start value", ""],
             ["Volatilities (39)", "Realised, 3 years of daily data", "Diffusion size", "No options data available; documented proxy"],
             ["Correlation matrix 39x39", "613 dates where all series exist (inner join)", "Cholesky / PCA", "Verified positive semi-definite"],
             ["SOFR level history", "FRED", "Rate vol, USD-JPY correlation", "From April 2018"],
             ["JPY OIS curve, swaption cube, USDJPY forwards", "Bloomberg one-time export, 2026-08-31 snapshot", "JPY factor, JPY-USD differential", "Licensed: derived numbers only appear here, never the raw data"],
             ["TONA (JPY overnight rate)", "Bank of Japan public API, daily from 1998", "JPY rate vol, USD-JPY correlation", "Includes real negative-rate years"],
             ["JGB par yields 1Y-40Y", "Japan Ministry of Finance, daily from 1974", "JPY mean-reversion test", "Public"]],
            widths=[1.5, 2.2, 1.8, 2.2], font=7.3))
    add(Spacer(1, 6))
    add(P("3.1 The USD curve", H2))
    add(P("Databento provides the futures, not a ready OIS curve, so we build one: each 3-month SOFR future price gives an implied forward rate (100 - price) for its "
          "reference quarter; chaining consecutive quarters multiplies discount factors. Beyond the last live contract (about 6.3 years out) the curve is extrapolated flat. "
          "Two real bugs were found here by cross-checking with the Treasury curve (Section 10). The curve is the starting point of the Hull-White model and the discount curve at t=0."))
    add(doc.figure(fig_curve(calib), "The bootstrapped USD SOFR curve. The upward slope (zero rate about 3.7% at the front, above 4% by 6 years) means forwards exceed spot rates."))
    add(P("3.2 Volatilities", H2))
    add(P("Volatility is the annualised standard deviation of daily changes over the last three years (log returns for equities and FX; simple differences for the rate, "
          "because rate LEVELS near or below zero make log returns meaningless). Rate vol: %.2f%% per year (normal vol on SOFR)." % (calib["gbm"].vols.get("RATE_USD", 0) * 100 if "RATE_USD" in calib["gbm"].vols else 0.6311)))
    add(doc.figure(fig_vols(calib), "Realised volatility spans an order of magnitude across the 37 names. A few names carry 50-76% vol, which dominates tail exposure of the trades that reference them."))
    add(P("<b>Choice and alternative.</b> Implied volatility from options would be forward-looking and is the norm for pricing, but we had no single-name options data (the Bloomberg "
          "export has only SPX/TOPIX index vols, which would need a per-name basis assumption). A 3-year realised window is a documented, reproducible proxy. Its limitation is that it "
          "is backward-looking and cannot see regime changes; the sensitivity test (Section 9) shows how much the results move if vols are 50% higher."))
    add(P("3.3 Correlations", H2))
    fig_c, off = fig_corr(calib)
    add(doc.figure(fig_c, "Left: the 39x39 correlation matrix reordered so similar names sit together; a broad positive 'market' block is visible. Right: the 741 pairwise correlations centre on %.2f." % off.mean()))
    add(P("<b>Is this matrix created every day? No.</b> It is one static matrix. We take the daily returns of all 39 factors, keep only the 613 dates on which every series has a price "
          "(US and Tokyo trade on different calendars, so we join by calendar date, not timestamp - a bug we hit once), and compute one pairwise correlation matrix. It is assumed "
          "constant over the simulation horizon. The alternatives (time-varying DCC-GARCH, or stressed correlations) add parameters we cannot validate with our data; we flag this as a limitation."))
    add(PageBreak())

    # ---------- 4 models
    add(P("4. The risk-factor models", H1))
    add(P("4.1 USD short rate: Hull-White one-factor", H2))
    add(P("We need the whole USD curve at every future date and scenario, because bonds and funding legs are discounted with it. The standard tool is the <b>Hull-White one-factor "
          "model</b>, a Gaussian, mean-reverting short-rate model:"))
    add(code("dr(t) = [ theta(t) - a * r(t) ] dt + sigma dW(t)"))
    add(P("<b>a</b> is mean reversion (how fast rates are pulled back), <b>sigma</b> is rate volatility, and <b>theta(t)</b> is chosen so that the model prices today's curve "
          "exactly. We use the equivalent shifted Ornstein-Uhlenbeck form r(t) = x(t) + alpha(t):"))
    add(code("x(t+dt) = x(t) e^{-a dt} + sigma sqrt( (1 - e^{-2 a dt}) / (2a) ) Z      (exact transition)\n"
             "alpha(t) = f(0,t) + sigma^2/(2 a^2) (1 - e^{-a t})^2                      (fits today's curve)\n"
             "P(t,T)   = A(t,T) exp( -B(t,T) r(t) ),  B = (1 - e^{-a (T-t)})/a        (analytic bond price)"))
    add(P("<b>Why this model.</b> (1) It reproduces today's curve to 1e-9 (tested). (2) Bond prices at future nodes are analytic, so building the discount curve for a scenario costs one "
          "function evaluation (10x faster than building a curve object, and exact rather than interpolated). (3) It is Gaussian, so it can produce negative rates, essential for JPY history and harmless for USD. "
          "<b>Alternatives rejected:</b> CIR/Black-Karasinski (positive-only, cannot represent negative JPY rates); LMM/HJM multi-factor curve models (more realistic curve twists but many more parameters than "
          "our data can support and slower); a constant-rate assumption (would ignore the funding-leg and bond-forward rate risk)."))
    add(P("<b>Parameters.</b> sigma = %.2f%% (realised SOFR vol); a = %.4f (calibrated, Section 6). Today's short rate r(0) = %.2f%%." % (meta["hw_sigma"] * 100, meta["hw_a"], meta["hw_r0"] * 100)))
    add(doc.figure(fig_rate_fan(D, calib), "Simulated USD short rate. The median tracks today's forward curve (dashed) because the model is fitted to it; the widening bands are rate uncertainty."))
    add(P("4.2 Equities and USDJPY: correlated geometric Brownian motion", H2))
    add(code("dS_i / S_i = ( r(t) - q_i ) dt + sigma_i dW_i        USD-quoted names\n"
             "dS_i / S_i = ( r_JPY(t) - q_i ) dt + sigma_i dW_i     JPY-quoted names\n"
             "dFX / FX   = ( r_USD - r_JPY ) dt + sigma_FX dW_FX    USDJPY (JPY per USD)"))
    add(P("Each step is the exact log-normal step ln S(t+dt) = ln S(t) + (r - q - sigma^2/2) dt + sigma sqrt(dt) Z, with r the simulated USD short rate at the start of the step "
          "(so equities and rates are linked). Under the risk-neutral measure the expected growth is r - q, verified in Section 9 by a martingale test."))
    add(P("<b>Why GBM.</b> It matches the lognormal vol convention we measure, is the market default for equity CCR, and needs only a vol per name. <b>Alternatives:</b> local/stochastic vol "
          "(Heston, SABR) would capture skew and vol-of-vol but need option surfaces we do not have; jump models help tails but add unobservable parameters. We disclose that GBM understates fat tails."))
    add(doc.figure(fig_fx_eq_fan(D, calib), "Simulated USDJPY and two equities (a low-vol and the highest-vol name) with 5-95 and 25-75 percent bands."))
    add(P("4.3 Correlation and the Cholesky factor", H2))
    add(P("Independent random numbers give independent assets. Real assets move together, so we transform independent standard normals Z into correlated ones. Given the target "
          "correlation matrix C, the <b>Cholesky decomposition</b> finds the lower-triangular L with L L' = C. Then Y = L Z has exactly correlation C:"))
    add(code("Cov(Y) = L Cov(Z) L' = L I L' = L L' = C"))
    add(P("It is used because it is the cheapest exact way to impose an arbitrary positive-definite correlation structure. A tiny eigenvalue clip guards against CSV round-off making C numerically non-PSD."))
    fig_ch, (n1, n2, r12) = fig_cholesky_demo(calib)
    add(doc.figure(fig_ch, "Demonstration on the most correlated pair in our real matrix (%s / %s, corr %.2f): independent draws (left) become correlated draws (right) after multiplying by L." % (n1[:8], n2[:8], r12)))
    add(P("4.4 Optional alternative: a PCA factor model for correlation", H2))
    add(P("A 39x39 matrix has 741 free correlations estimated from only 613 days, so many entries are noisy. A <b>factor model</b> assumes co-movement comes from a few common drivers "
          "plus each name's own noise: C ~ B B' + diag(d), where B (39 x k) are loadings on k factors. We build it by principal-component analysis: B = top-k eigenvectors x sqrt(eigenvalue), "
          "and d = 1 - row sums of squares so every name still has unit variance. Simulation then draws k systematic and 39 idiosyncratic shocks."))
    fig_s, vals, ev, err_max = fig_scree(calib)
    add(doc.figure(fig_s, "Left: the first eigenvalue (%.1f of a total 39) is one dominant market factor. Middle: %d factors explain %.0f%% of variance and 10 explain %.0f%%. Right: reconstruction error falls as k grows (exactly zero at full rank)." % (vals[0], 5, ev[4] * 100, ev[9] * 100)))
    add(doc.figure(fig_loadings(calib), "Loadings of each of the 39 factors on the first five principal factors."))
    add(P("<b>Trade-off.</b> The factor model is smoother and more robust to estimation noise and gives quasi-random sequences a low-dimensional space where they work best, but it only approximates the "
          "empirical matrix. Because it changes results, it is an option (corr_mode='factor'), not the default. Section 7.5 compares its exposure profiles with the full-rank engine."))
    add(PageBreak())

    add(P("4.5 JPY: a negative-rate-capable rate model", H2))
    add(P("Until recently JPY drift used r_USD minus a constant differential. That cannot represent JPY's own rate dynamics. We therefore built a genuine second Hull-White factor for JPY "
          "(<font face='Courier'>build_jpy_hull_white</font>): it starts from the real JPY OIS curve and, being Gaussian, has <b>no floor at zero</b>."))
    fig_t, tona = fig_tona()
    add(doc.figure(fig_t, "Real TONA history from the Bank of Japan: rates were at or below zero for most of 25 years, with %d negative daily fixings (2003 and 2016-2024). A model that floors at zero could not represent this." % int((tona < 0).sum())))
    fg, frac = fig_ou_negative()
    add(doc.figure(fg, "Demonstration of the capability: Hull-White started from a synthetic -0.10%% flat curve. %.0f%% of simulated points are negative and nothing is clipped. (Our only real JPY curve snapshot, Aug 2026, is positive after BOJ hikes, so the negative case is shown synthetically.)" % (frac * 100)))
    hj = meta["hw_jpy"]
    add(tbl([["JPY factor parameter", "Value", "Source / status"],
             ["Curve", "Real JPY OIS zero curve", "Bloomberg snapshot 2026-08-31"],
             ["sigma", "%.3f%%/yr" % (hj["sigma"] * 100), "REALISED TONA vol, 3y window: real Bank of Japan data (replaces an earlier swaption-implied 0.400%)"],
             ["a (mean reversion)", "%.4f" % hj["a"], "Fallback to the USD value: both real JPY calibrations gave a negative a (Section 6.2)"],
             ["USD-JPY rate-factor correlation", "%+.3f" % meta["usd_jpy_corr"], "Calibrated from real SOFR vs TONA daily changes (n=%d, p=%.2f): statistically zero" % (meta["usd_jpy_corr_detail"]["n_obs"], meta["usd_jpy_corr_detail"]["p_value"])],
             ["Wired into simulate_paths()?", "NO (disclosed)", "JPY equity/FX drift still uses r_USD minus the constant differential (%.2f%%, from real Bloomberg curves)" % (meta["jpy_usd_rate_diff"] * 100)]],
            widths=[1.8, 1.4, 4.5]))
    add(Spacer(1, 4))
    fg2, df_, d_ = fig_usd_jpy_rates()
    add(doc.figure(fg2, "Levels (left) rise together with the global cycle (level correlation ~0.38), but day-to-day changes (right) are uncorrelated (%+.3f): central banks set policy independently. A Hull-White correlation needs the CHANGES." % d_["SOFR"].corr(d_["TONA"])))
    add(P("<b>Why this matters little for the results:</b> only 2 of 16 trades are JPY compo, so this simplification affects a small part of the book. It is disclosed rather than hidden, and "
          "the next engineering step is to let the simulated JPY rate drive those two trades."))
    add(PageBreak())

    # ---------- 5 engine
    add(P("5. How the simulation engine works", H1))
    add(P("5.1 The pipeline", H2))
    add(code("1. calibrate:   curve, sigma, a, vols, correlation (real data)\n"
             "2. grid:        choose simulation dates (pillars + trade event dates [+ MPOR look-ahead])\n"
             "3. draw:        random numbers (Latin Hypercube) -> correlated shocks (Cholesky or PCA)\n"
             "4. step:        advance short rate, 37 equities, USDJPY along every path\n"
             "5. reprice:     for every (scenario, date): build MarketState, call npv() of all 16 trades\n"
             "6. aggregate:   net by counterparty -> max(.,0) -> EE, median, PFE, MPE"))
    add(P("5.2 Choosing the simulation dates", H2))
    add(P("Monthly steps are simple but wasteful and blunt: they spend nodes evenly when the risk changes fastest near term, and a trade's own reset or maturity rarely falls on a month node. "
          "Capitolis' hint was to use <b>pillar dates</b>: the standard market curve tenors already used to build the SOFR curve (O/N, T/N, 1W, 2W, 1M, 2M, 3M, 6M, 9M, 1Y, 18M, 2Y ...). "
          "This is also how production CCR systems space dates: dense short-term, sparse long-term. On top, every trade's own reset/settlement/maturity date is <b>forced onto the grid</b> so "
          "exposure jumps at cash-flow dates are not smoothed over."))
    fg, nm, npil, npe = fig_grid(D)
    add(doc.figure(fg, "For this book the pillar grid (%d dates) plus forced trade-event dates (%d in total) is more compact than a plain monthly grid (%d) and hits every real cash-flow date exactly." % (npil, npe, nm)))
    add(P("5.3 Speed", H2))
    add(tbl([["Bottleneck", "Fix", "Before", "After"],
             ["Discount curve per (scenario, node)", "Analytic Hull-White bond price instead of building a Curve object", "0.206 ms/call", "0.019 ms/call (10.6x, and exact)"],
             ["Pure-Python pricers (~1.2 ms each)", "Multiprocessing over scenarios, 8 workers (a Windows spawn re-import bug was fixed)", "113 ms/scenario", "51 ms/scenario at the time"],
             ["Combined, 2,000 scenarios x 16 trades", "", "~12 min projected", "93 s (7.7x)"]], widths=[2.0, 3.2, 1.2, 1.7]))
    add(P("Current measured cost for the 3,000-scenario reporting run: %.0f s simulation of paths, %.0f s repricing (%.0f ms/scenario, including the extra MPOR look-ahead nodes)." % (meta["timing"]["paths_s"], meta["timing"]["reprice_s"], meta["timing"]["reprice_s"] / meta["n_scenarios"] * 1000)))
    add(P("5.4 Random numbers and variance reduction", H2))
    add(P("Plain pseudo-random draws waste information: by chance a sample can cluster. Five sampling schemes sit behind one interface: <b>pseudo-random</b> (baseline), <b>antithetic</b> (each draw z paired with -z), "
          "<b>moment-matched</b> (rescale so the sample mean is 0 and std 1), <b>Sobol</b> (low-discrepancy quasi-random), and <b>Latin Hypercube</b> (each dimension split into equal-probability bins, one draw per bin)."))
    fg, opt, real = fig_vr()
    add(doc.figure(fg, "Left: on a European call with a known Black-Scholes answer, Latin Hypercube has ~%.0fx lower error than pseudo-random. Right: on the real 663-dimensional engine the ranking survives but compresses; Latin Hypercube still gives %.2fx lower PFE variability." % (opt["pseudo_random"]["rmse"] / opt["latin_hypercube"]["rmse"], real["pseudo_random"]["std"] / real["latin_hypercube"]["std"])))
    add(P("<b>Finding that was not assumed:</b> antithetic and moment-matching, which help in one dimension, give no benefit at 663 effective dimensions (39 factors x 17 steps); Sobol's advantage shrinks (the 'curse of "
          "dimensionality'); Latin Hypercube still wins because it stratifies each dimension's marginal independently. <b>Choice: Latin Hypercube</b>, at negligible extra cost."))
    add(PageBreak())

    add(P("5.5 How many scenarios? The convergence study", H2))
    add(P("Monte Carlo error falls like 1/sqrt(N). Rather than re-run the expensive repricing at every candidate N, we simulate one large pool once and bootstrap-resample subsets to measure the standard error at each N."))
    fg, c95, c99, r99 = fig_conv()
    add(doc.figure(fg, "Left: for PFE95 and EE the error follows the 1/sqrt(N) law almost exactly (dashed). Middle/right: for PFE99 (a rarer tail, 30,000-path pool), error is larger at the same N and the marginal gain per extra batch peaks at N=5,000 then declines."))
    rows = [["N", "PFE99 (USD)", "Relative SE", "Bias vs 30k pool", "Marginal SE gain", "Est. time"]]
    for r in c99["results"]:
        rows.append([f"{r['N']:,}", f"{r['PFE_mean']:,.0f}", f"{r['relative_se_pct']:.2f}%", f"{r['bias_vs_pool_pct']:+.2f}%",
                     "-" if r["marginal_se_improvement_pct"] is None or r["N"] == c99["N_pool"] else f"{r['marginal_se_improvement_pct']:+.1f}%", f"{r['est_time_s']:,.0f}s"])
    add(tbl(rows, widths=[0.8, 1.5, 1.2, 1.4, 1.5, 1.0]))
    add(Spacer(1, 4))
    add(P("<b>Conclusions.</b> For the 95th percentile, N=1,000 gives 0.39%% relative error (73 s); N=2,000-3,000 gives 0.1-0.3%%. For PFE99 (portfolio at ~1 year, pool value $%s): "
          "N=5,000-10,000 is the knee (0.29-0.21%% error, 8-15 min), and beyond 15,000 each doubling buys little. The 30,000-path run is the reference, not an operating point. "
          "We report with N=3,000 because past a few thousand paths the dominant uncertainty is model risk (mean reversion, volatility proxy), not sampling noise." % f"{c99['pool_pfe_reference']:,.0f}"))
    add(PageBreak())

    # ---------- 6 calibration
    add(P("6. Calibrating Hull-White mean reversion", H1))
    add(P("Mean reversion a controls how fast rate shocks decay; the convergence study flagged it as the largest unquantified model uncertainty. The textbook method is to fit swaption "
          "volatilities. Hull-White predicts that the volatility of a forward rate at maturity T decays with time to maturity:"))
    add(code("sigma_f(t, T) = sigma * exp( -a (T - t) )      =>   ln(vol) = ln(sigma) - a * tenor   (line, slope = -a)"))
    add(P("So measuring vol at several tenors and regressing ln(vol) on tenor gives a. We tried three real data routes, in order of preference:"))
    fg, h, sw, sj, jg = fig_hw_fit(calib)
    add(doc.figure(fg, "Left: USD SOFR-futures fit. Right: fitted a for each route. USD routes give sensible positive values; both JPY routes give a NEGATIVE a."))
    add(tbl([["Route", "Data", "a", "R2", "Verdict"],
             ["Swaption cube, USD (preferred)", "Bloomberg ATM normal vol, 1M expiry, tenors 1Y-15Y", "%.4f" % sw["a"], "%.2f" % sw["r_squared"], "USED for USD"],
             ["SOFR-futures vol decay, USD", "8 contracts, ~2y Databento history", "%.4f" % h["a"], "%.2f" % h["r_squared"], "cross-check (different instrument, higher a)"],
             ["Swaption cube, JPY", "Bloomberg JPY OIS ATM vols (one snapshot)", "%.4f" % sj["a"], "%.2f" % sj["r_squared"], "invalid (vol rises with tenor)"],
             ["JGB yield vol, JPY", "MOF daily 1Y-30Y yields, 3y window", "%.4f" % jg["a"], "%.2f" % jg["r_squared"], "invalid (vol rises with tenor)"]],
            widths=[2.0, 2.6, 0.8, 0.6, 2.0]))
    add(Spacer(1, 5))
    add(P("6.1 Why the two USD numbers differ", H2))
    add(P("0.0167 (swaptions) versus 0.0458 (futures) is not a contradiction: they use different instruments (swaption-implied vs realised vol) and different tenor ranges (1-15Y swap tenors vs 1-3Y forward reset times). "
          "The swaption route is the industry standard and is used; the gap is itself a measure of model uncertainty and motivates the sensitivity test."))
    add(P("6.2 Why JPY does not fit, and what we did", H2))
    fj = fig_jgb_vol()
    add(doc.figure(fj, "Real realised JGB yield vol by tenor. At every window tried (1y, 3y, 10y) long tenors are MORE volatile than short ones, the reverse of the decay Hull-White assumes."))
    add(P("This is not bad data; it is a structural finding confirmed by two independent real sources (a 2026 swaption cube and 52 years of JGB yields). The plausible reason: for two decades the "
          "Bank of Japan pinned the SHORT end (zero and negative policy rates, yield-curve control) so short-tenor vol was suppressed while longer tenors moved more freely. A single-factor model with "
          "positive mean reversion cannot represent that shape, and a negative a would make the short rate diverge. <b>Choice:</b> reuse the USD value a = %.4f for the JPY factor and label it as a "
          "fallback. What would truly fix it is a two-factor or regime-dependent model, or a long history of the full JPY swap curve; this is listed under future work." % meta["hw_a"]))
    add(P("<b>Practical impact:</b> small. JPY affects two trades, the JPY factor is not yet wired into the drift, and the USD parameters are the ones used for discounting the whole book."))
    add(PageBreak())

    # ---------- 7 results
    add(P("7. Results", H1))
    add(P("7.1 Exposure today (t = 0)", H2))
    rows = [["Counterparty", "Trades", "Net MTM today", "Netted exposure today", "Comment"]]
    for c in ("CPTY_A", "CPTY_B", "CPTY_C"):
        idx = [i for i, t in enumerate(ids) if meta["trade_counterparty"][t] == c]
        net = float(npv0[idx].sum())
        rows.append([c, str(len(idx)), f"{net:,.0f}", f"{max(net,0):,.0f}", {"CPTY_A": "Small positive net", "CPTY_B": "We owe them: zero exposure", "CPTY_C": "One 500M bond forward dominates"}[c]])
    rows.append(["Portfolio", str(len(ids)), f"{npv0.sum():,.0f}", f"{tot['EE'][0]:,.0f}", "Sum of counterparty exposures (netting does not cross counterparties)"])
    add(tbl(rows, widths=[1.2, 0.7, 1.5, 1.7, 2.6]))
    add(P("The simulated EE at t=0 equals the directly computed current exposure to 0.0000% (the engine's built-in self-check): at t=0 there is no randomness so both must agree exactly."))
    add(P("7.2 Exposure profiles through time", H2))
    add(doc.figure(fig_profiles(D), "EE, median, PFE95 and PFE99 for each counterparty and the portfolio. The shaded band runs from the median to PFE99."))
    rows = [["Counterparty", "EE(0)", "Peak EE", "Peak median", "Peak PFE95", "MPE (peak PFE99)", "MPE date"]]
    for c in ("CPTY_A", "CPTY_B", "CPTY_C", "__portfolio__"):
        p = prof(D["expo"][c]); jj = int(p["P99"].argmax())
        rows.append([("Portfolio" if c == "__portfolio__" else c), m(p["EE"][0]), m(p["EE"].max()), m(p["MED"].max()), m(p["P95"].max()), m(p["P99"].max()), str(D["rep_dates"][jj])])
    add(tbl(rows, widths=[1.2, 0.9, 0.9, 1.0, 1.0, 1.4, 1.1]))
    add(Spacer(1, 4))
    add(P("<b>Reading the shape.</b> Exposure peaks soon after today and then falls steeply as trades mature. By the end of December 2026 the portfolio EE has fallen by more than 90%; the "
          "remainder is the Bond TRS BTRS_0001 and the year-long EQTRS_0008. So almost all counterparty credit risk sits in the next four months and monitoring should be concentrated there."))
    add(P("<b>EE versus median versus PFE.</b> The median is far below EE for the counterparties with more than half of scenarios at zero exposure (CPTY_B especially): EE is pulled up by the right tail, "
          "the median describes the typical outcome, and PFE99 describes the bad tail. Reporting all three prevents any single number from misleading."))
    add(doc.figure(fig_prob_positive(D), "Probability that a counterparty has any positive exposure at all. Where this is far below 100%, the median exposure is zero even though EE and PFE are large."))
    add(doc.figure(fig_dists(D), "Portfolio exposure histograms (log count) at four dates with median (gold), EE (navy) and PFE99 (red). The right tail lengthens with time."))
    add(PageBreak())

    add(P("7.3 Where does the risk come from?", H2))
    add(doc.figure(fig_trade_heat(D), "Expected NPV by trade at each reporting date. CPTY_C's BF_0003 dominates the picture and disappears at its 2026-12-06 settlement; a few equity TRS contribute negative expected NPV."))
    cC = per["CPTY_C"]
    add(P("<b>Concentration.</b> CPTY_C accounts for %.0f%% of the portfolio's peak PFE99 and %.0f%% of today's exposure, and almost all of it comes from one trade, BF_0003 (500M notional, short forward struck at 100 on a long-dated 2.88%% 2049 Treasury trading roughly 20 points below par, so we are owed the difference). This is concentration risk rather than diversified counterparty risk; a limit or collateral on that single trade would move the portfolio number more than any modelling choice in this report." % (
              cC["P99"].max() / tot["P99"].max() * 100, ce0["CPTY_C"] / max(tot["EE"][0], 1) * 100)))
    add(P("7.4 What if the counterparty posts margin? (MPOR-shifted exposure)", H2))
    add(P("The real book is treated as <b>uncollateralized</b> because trade_data carries no CSA terms. For a collateralized counterparty, default does not mean instant close-out: there is a Margin Period of Risk "
          "(standard 10 days) between the last collateral exchange and the actual replacement of the trades. The relevant exposure is what the position could gain in that window beyond the collateral held:"))
    add(code("C(t)        = max( V(t) - threshold, 0 )        collateral held at reporting date t\n"
             "Exposure(t) = max( V(t + MPOR) - C(t), 0 )      same simulated path, MPOR days later"))
    add(P("Implementation: an extra look-ahead node is inserted MPOR days after every reporting node on the same simulated path (no separate simulation). The demonstration below is explicitly hypothetical: "
          "full variation margin (threshold 0), MPOR 10 days, 3,000 scenarios."))
    fg, cmp_, cp, u, mp = fig_mpor(D)
    add(doc.figure(fg, "If a full-VM CSA existed, peak PFE99 would fall sharply, most of all for CPTY_C whose exposure is a large, already-visible MTM that margin would cover."))
    rows = [["Counterparty", "Uncollateralized MPE99", "MPOR-shifted MPE99", "Reduction"]]
    for c, a1, a2 in zip(cp, u, mp):
        rows.append([c, f"${a1:,.1f}M", f"${a2:,.1f}M", f"{(1 - a2 / a1) * 100 if a1 > 0 else 0:.0f}%"])
    add(tbl(rows, widths=[1.5, 2.0, 2.0, 1.2]))
    add(P("Whether any trade is actually margined is the most important open question for Capitolis: it changes the answer by roughly an order of magnitude for CPTY_C."))
    add(PageBreak())

    add(P("7.5 Full-rank correlation versus PCA factor model", H2))
    fg, mpe_f, ee_f, ncmp = fig_factor_cmp()
    add(doc.figure(fg, f"Same seed and method ({ncmp:,} scenarios) with the full Cholesky correlation versus a k-factor PCA model. Curves coincide closely from k=5."))
    rows = [["Model", "Peak portfolio EE", "MPE (peak PFE99)", "MPE difference vs full"]]
    for k in mpe_f:
        rows.append([k, m(ee_f[k]), m(mpe_f[k]), "-" if k == "full" else f"{(mpe_f[k] / mpe_f['full'] - 1) * 100:+.1f}%"])
    add(tbl(rows, widths=[1.5, 1.8, 1.8, 1.8]))
    add(P("This is a like-for-like comparison at one scenario count, so differences include sampling noise of a few tenths of a percent as well as the approximation itself. "
          "The factor model with about 5 factors reproduces the book's exposure closely, which supports it as a lower-dimensional, more robust alternative, but the full-rank default is kept because it "
          "is exact with respect to the estimated matrix. That five factors (only about half of the correlation matrix's total variance) suffice here is because this book's exposure is driven by the rate, a few large positions and FX, not by the fine correlation structure among all 37 names."))

    # ---------- 8 choices
    add(P("8. Every modelling choice, and what we rejected", H1))
    add(tbl([["Topic", "Choice", "Alternatives considered", "Reason"],
             ["Measure", "Risk-neutral", "Real-world drifts", "No unobservable risk premia; verified martingale; horizon short"],
             ["Confidence", "PFE99 (+ median, EE, PFE95 for context)", "99.9%, 95%", "99% intended target; 99.9% needed far more paths for little insight"],
             ["USD rates", "Hull-White 1F", "CIR, BK, LMM, constant", "Exact curve fit, analytic bonds, negative-rate capable, few parameters"],
             ["Equities/FX", "Correlated GBM", "Heston, SABR, jumps", "No option surfaces; matches lognormal vol convention"],
             ["Volatility", "3y realised", "Implied vols", "No single-name options data; documented proxy"],
             ["Correlation", "One static matrix, Cholesky", "Time-varying (DCC), stressed, factor", "Data supports one matrix; factor model offered as alternative"],
             ["Equity factor model", "Optional PCA (k=5)", "Full rank only", "Robustness, dimension reduction; approximation disclosed"],
             ["Dates", "Pillar dates + trade event dates", "Monthly grid", "Industry convention, denser where risk moves, exact cash-flow dates"],
             ["Sampling", "Latin Hypercube", "Pseudo-random, antithetic, moment-matched, Sobol", "Best measured error on both test and real engine"],
             ["Scenario count", "3,000 (reporting); 10-15k for tight PFE99", "30,000 pool", "Diminishing returns; model risk dominates beyond a few thousand"],
             ["Mean reversion a", "Swaption-based (USD 0.0167)", "Futures proxy (0.0458), textbook 0.03", "Industry-standard instrument"],
             ["JPY rates", "Real JPY Hull-White factor (built), not yet wired", "Constant differential only", "Negative-rate capable; real TONA sigma; correlation calibrated ~0"],
             ["Collateral", "Uncollateralized default; MPOR-shift option", "Assume full VM", "No CSA data; hypothetical shown separately"],
             ["Pricing", "Reuse validated pricer library", "Vectorised reimplementation", "Correctness first; speed via multiprocessing"]],
            widths=[1.2, 2.0, 2.0, 2.6], font=7.2))
    add(PageBreak())

    # ---------- 9 validation
    add(P("9. Validation: how we know the engine is right", H1))
    add(P("Each check isolates one layer (paths, pricing, calibration, aggregation) so a failure points at where to look."))
    add(P("9.1 Self-consistency at t = 0", H2))
    add(P("Simulated EE(0) must equal a direct current-exposure calculation from the identical calibrated snapshot: matches to 0.0000% (after fixing two comparison-object mismatches, Section 10)."))
    add(P("9.2 Martingale / no-arbitrage test", H2))
    add(P("Under the risk-neutral measure discounted asset prices must have no drift. With 8,000 paths: the bank-account check E[exp(-integral r)] = P(0,T) holds to a maximum relative difference of 0.73 bp "
          "across nodes (a small, understood trapezoid-integration effect of the coarse monthly grid), and the discounted-equity 'gains process' for six names has all |z| below 1.4. This validates the drift terms "
          "in the engine itself, independent of any trade pricing."))
    add(P("9.3 Parametric (delta-normal) VaR benchmark", H2))
    add(P("An independent standard method: portfolio dollar-deltas by bump-and-reprice with the SAME vols and correlations, giving VaR95 of $43.9M versus $40.8M from the Monte Carlo P&L distribution "
          "(ratio 1.08, accepted range 0.2-1.5). It agrees on order of magnitude and the slight excess is consistent with a mostly-linear book at a one-month horizon."))
    add(P("9.4 Sensitivity (stress) test", H2))
    add(P("Directional test with common random numbers: equity vol x1.5 raised MPE by 11.4%; a +100bp parallel rate shift by 39.1% (the largest single delta is to the USD rate); Hull-White sigma x1.5 by 1.8%. "
          "All three moved exposure in the economically required direction. (These stress numbers were measured earlier at the 95th percentile; the directional conclusions do not depend on the confidence level.)"))
    add(P("9.5 Statistical and unit tests", H2))
    add(P("58 automated tests pass. They cover: Hull-White reproducing the curve at t=0 to 1e-9; the GBM martingale property; the 1/sqrt(N) error law; antithetic variance reduction; Cholesky recovering a target "
          "correlation; MPOR look-ahead spacing and formula; pillar dates and forced event dates; negative-rate behaviour of Hull-White; the PCA factor model (exact at full rank, monotone error, variance "
          "preservation); the BOJ TONA and MOF JGB loaders and the empirical JPY findings; the tail-convergence result; and median exposure."))
    add(P("9.6 Greeks (sensitivities)", H2))
    add(P("Three delta estimators were compared on a call option: pathwise, bump-and-reprice with <b>common random numbers</b> (same draws in base and bumped runs) and bump-and-reprice with independent draws."))
    add(tbl([["Method", "Bias", "Std of estimate", "Time/trial"],
             ["Pathwise", "+0.000085", "0.003771", "0.470 ms"], ["Bump, common random numbers", "+0.000033", "0.003742", "0.327 ms"],
             ["Bump, independent random numbers", "-0.003502", "0.096885", "0.850 ms"]], widths=[2.6, 1.3, 1.6, 1.3]))
    add(P("Common random numbers make bump-and-reprice statistically indistinguishable from the pathwise estimator (26x lower noise than independent draws), and it works on any pricer as a black box, "
          "so it is the method that generalises to the real book. On the real book, the exact t=0 delta of EQTRS_0003's NPV to its largest position is -$212,269 per $1 move, exactly equal to the share count "
          "(a linear-payoff consistency check)."))
    add(PageBreak())

    # ---------- 10 bugs
    add(P("10. Bugs found and fixed", H1))
    add(P("Each was caught because something was checked against an independent source, a hand calculation or a full end-to-end run, not because the first attempt was assumed right."))
    add(tbl([["#", "Bug", "How it was caught / fix"],
             ["1", "BRK.B vs BRK-B ticker silently failed in two functions", "Missing prices; fixed in both current and historical fetch"],
             ["2", "SOFR curve: recently-expired serial futures wrapped a decade forward, creating a multi-year gap", "Cross-check against Treasury.gov par curve (73bp vs smooth 56bp at 10Y); fixed"],
             ["3", "The fix for #2 over-corrected and dropped genuine far-dated live contracts (e.g. SR3H0, March 2030)", "Found while calibrating Hull-White; fixed with a 400-day plausibility threshold; curve coverage 3.6y -> 6.3y"],
             ["4", "US and Tokyo equity histories joined by timestamp gave a ~70% blank table", "Join by calendar date instead"],
             ["5", "Stale cached exposure file gave false 7-15% 'discrepancies'", "Root cause: real overnight moves (one name has 76% vol); check now uses the in-memory snapshot"],
             ["6", "Residual 0.02-0.03% self-check gap", "Different curve object; both sides now use the identical exact analytic curve: 0.0000%"],
             ["7", "PFE confidence was 99.9% by mistake in the tail study", "Corrected to 99% and fully re-run; tests updated"],
             ["8", "JPY mean-reversion fit gave a negative a", "Diagnosed as a real structural property (two sources); guarded with documented fallback"]],
            widths=[0.3, 3.3, 4.2], font=7.4))
    add(P("11. Assumptions and limitations (what a reader should not over-trust)", H1))
    add(B(["<b>Uncollateralized and no CSA data.</b> If margin exists, results change by up to an order of magnitude (Section 7.4).",
           "<b>Volatility is a 3-year realised proxy</b>, not implied. Regime shifts and skew are not captured.",
           "<b>One static correlation matrix</b> from 613 days; correlations tend to rise in stress and are not stressed here.",
           "<b>GBM underestimates fat tails</b>, most relevant for PFE99 on high-vol names.",
           "<b>Single-factor USD rates</b>: no curve twists independent of the level.",
           "<b>Risk-neutral drift</b>: not a real-world forecast; regulatory PFE may need physical drift.",
           "<b>JPY:</b> mean reversion is a fallback and the JPY rate does not yet drive JPY equity/FX drift (two trades).",
           "<b>Model risk vs sampling risk:</b> above a few thousand scenarios the uncertainty is in the models, not the random numbers.",
           "<b>No wrong-way risk or credit dynamics of the counterparty itself</b>; this is exposure, not a loss estimate (that needs PD and LGD).",
           "<b>Bloomberg data is a single 2026-08-31 snapshot</b> (three days after the 2026-08-28 market data); acceptable for shape and level, disclosed."]))
    add(P("12. Conclusions and recommendations", H1))
    add(B([f"The engine is validated (t=0 self-check, martingale, VaR benchmark, stress test, 58 tests) and reproducible with a single command per stage.",
           f"The uncollateralized book has peak portfolio PFE99 of {m(mpe99)} at {D['rep_dates'][j_mpe]}, versus EE of {m(tot['EE'].max())} and median of {m(tot['MED'].max())}; the spread between these three is the point of reporting all of them.",
           "Risk is short-dated (about four months) and concentrated (one trade, one counterparty).",
           "Ask Capitolis whether any trade is margined and on what terms; that single fact matters more than any modelling refinement.",
           "Use 3,000 Latin-Hypercube scenarios for reporting; 10,000-15,000 for a tight PFE99.",
           "Next engineering steps: wire the JPY Hull-White factor into JPY equity/FX drift; PFE Greeks (d PFE / d spot) using common random numbers; a two-factor or regime-aware rate model if a long JPY curve history becomes available; a vectorised pricer reimplementation if scenario counts must exceed ~10,000; a model-risk study varying a, vols and correlation."]))
    add(PageBreak())

    add(P("Appendix A. Glossary", H1))
    add(tbl([["Term", "Meaning"],
             ["Counterparty credit risk (CCR)", "Loss risk if the other side of a derivative defaults while the contract is in our favour"],
             ["MTM / NPV", "Mark-to-market / net present value: what the trade is worth today"],
             ["Netting set", "Trades under one legal netting agreement; combined before taking max(V,0)"],
             ["EE, PFE, MPE", "Expected exposure (mean), potential future exposure (percentile), maximum PFE over time"],
             ["Median exposure", "50th percentile exposure at a date"],
             ["Total return swap (TRS)", "Swap exchanging an asset's total return for a funding rate"],
             ["Compo", "Payoff in one currency on an asset quoted in another, so both asset and FX move the value"],
             ["SOFR / OIS", "US overnight risk-free rate / overnight index swap; the discount curve"],
             ["TONA", "Tokyo Overnight Average rate, JPY's overnight risk-free rate"],
             ["Hull-White", "Gaussian mean-reverting short-rate model that fits today's curve exactly"],
             ["Mean reversion (a)", "Speed at which a rate is pulled back toward its long-run path"],
             ["GBM", "Geometric Brownian motion: lognormal price dynamics"],
             ["Cholesky", "Factorisation C = L L' used to create correlated random draws"],
             ["PCA / factor model", "Explain most co-movement with a few principal factors plus idiosyncratic noise"],
             ["Latin Hypercube / Sobol", "Stratified / low-discrepancy sampling schemes that reduce Monte Carlo noise"],
             ["Common random numbers", "Reuse identical random draws across compared runs so differences are not noise"],
             ["MPOR", "Margin period of risk: delay between last margin call and close-out (typically 10 days)"],
             ["CSA / VM / threshold", "Credit support annex / variation margin / uncollateralized amount before margin is called"],
             ["Pillar dates", "Standard curve tenor points: O/N, T/N, 1W, 2W, 1M ... 10Y"],
             ["Risk-neutral measure", "Pricing measure in which discounted assets are martingales; drift = r - q"]],
            widths=[2.2, 5.5]))
    add(P("Appendix B. Reproducing the results", H1))
    add(code("python scripts/generate_report_data.py --scenarios 3000   # ~15 min: simulation, arrays for figures\n"
             "python scripts/build_report.py                            # this PDF\n"
             "python scripts/run_simulation.py --scenarios 3000         # printed EE/PFE99/MPE profiles\n"
             "python scripts/run_mpor_comparison.py                     # hypothetical collateral demo\n"
             "python -m pytest tests                                    # 58 tests"))
    add(P("Key modules: src/risk_engine/models (rates, equity_fx, calibration, hw_calibration, equity_factor_model), simulation (engine, random_numbers, parallel), "
          "exposure (aggregate, collateral), market (sofr, boj, mof_jgb, bloomberg, vols, correlations).", SMALL))

    doc.multiBuild(S)
    print("wrote", OUT_PDF)


def ParagraphStyleTitle():
    from reportlab.lib.styles import ParagraphStyle
    return ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=26, leading=30, textColor=NAVY_C(), spaceAfter=8)


def ParagraphStyleSub():
    from reportlab.lib.styles import ParagraphStyle
    return ParagraphStyle("sub", fontName="Helvetica", fontSize=13, leading=17, textColor=NAVY_C(), spaceAfter=8)


def NAVY_C():
    from reportlab.lib import colors
    return colors.HexColor(NAVY)


if __name__ == "__main__":
    main()
