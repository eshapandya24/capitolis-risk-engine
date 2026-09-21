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

import report_greeks as RG
from report_lib import GOLD, GREY, NAVY, ORANGE, PAL, TEAL, plt
from report_tex import (A, B, BODY, CAP, H1, H2, H3, SMALL, TOCH, PageBreak, Report, Spacer, callout,
                        code, make_toc, P, tbl, titlepage)
inch = 72

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
    return {"EE": a.mean(1), "MED": np.quantile(a, 0.5, axis=1),
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
    for val, lab, c in ((x.mean(), "EE (mean)", NAVY), (np.median(x), "Median PFE", GOLD),
                        (np.quantile(x, CONF), "PFE99", "#8B0000")):
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
    q = np.quantile(r, [0.01, 0.10, 0.25, 0.5, 0.75, 0.90, 0.99], axis=0)
    fig, ax = plt.subplots(figsize=(6.6, 2.9))
    for i in range(25):
        ax.plot(t, r[i], lw=0.5, alpha=0.5, color=GREY)
    ax.fill_between(t, q[0], q[6], color=TEAL, alpha=0.15, label="1-99%")
    ax.fill_between(t, q[1], q[5], color=TEAL, alpha=0.25, label="10-90%")
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
        q = np.quantile(arr, [0.01, 0.25, 0.5, 0.75, 0.99], axis=0)
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
    q = np.quantile(r, [0.01, 0.5, 0.99], axis=0)
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
    from risk_engine.market import jpy_ois
    y = fetch_jgb_yield_history()
    ten = {"1Y": 1, "2Y": 2, "3Y": 3, "4Y": 4, "5Y": 5, "6Y": 6, "7Y": 7, "8Y": 8, "9Y": 9, "10Y": 10,
           "15Y": 15, "20Y": 20, "25Y": 25, "30Y": 30, "40Y": 40}
    fig, ax = plt.subplots(1, 2, figsize=(7.4, 2.7), sharey=True)
    end = y.index.max()
    for yrs, c in ((1, ORANGE), (3, NAVY), (10, TEAL)):
        w = y[(y.index > end - pd.DateOffset(years=yrs)) & (y.index <= end)]
        xs, vs = [], []
        for col in TENOR_COLUMNS:
            d = w[col].dropna().diff().dropna()
            if len(d) > 30:
                xs.append(ten[col]); vs.append(d.std() * np.sqrt(252) * 1e4)
        ax[0].plot(xs, vs, marker="o", ms=3, color=c, label="%dy window" % yrs)
        v = jpy_ois.realized_vol_by_tenor(date(2026, 8, 28), yrs)
        ax[1].plot(list(v), [x * 1e4 for x in v.values()], marker="o", ms=3, color=c, label="%dy window" % yrs)
    ax[0].set_title("JGB par yields (Ministry of Finance)"); ax[1].set_title("JPY OIS par rates (daily history)")
    for a_ in ax:
        a_.set_xlabel("tenor (years)")
    ax[0].set_ylabel("realised normal vol (bp/yr)"); ax[0].legend()
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
    labs = ["futures\nUSD", "swaption\nUSD", "swaption\nJPY", "JGB\nJPY", "OIS hist.\nJPY"]
    from risk_engine.models.hw_calibration import calibrate_jpy_mean_reversion_from_jgb_yields
    jg = calibrate_jpy_mean_reversion_from_jgb_yields(date(2026, 8, 28))
    from risk_engine.models.hw_calibration import calibrate_mean_reversion_from_swaptions
    sj = calibrate_mean_reversion_from_swaptions(currency="JPY")
    from risk_engine.models.hw_calibration import calibrate_jpy_mean_reversion_from_ois
    oi = calibrate_jpy_mean_reversion_from_ois(date(2026, 8, 28))
    vals = [h["a"], sw["a"], sj["a"], jg["a"], oi["a"]]
    ax[1].bar(range(5), vals, color=[NAVY, TEAL, ORANGE, ORANGE, ORANGE])
    ax[1].axhline(0, color="k", lw=1)
    ax[1].set_xticks(range(5)); ax[1].set_xticklabels(labs, fontsize=6.5)
    ax[1].set_title("Fitted mean reversion a: USD sane, JPY negative")
    for i, v in enumerate(vals):
        ax[1].text(i, 0.003 if v < 0 else v + 0.002, f"{v:.3f}", ha="center", fontsize=7)
    return fig, h, sw, sj, jg, oi


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
    ax[0].set_yscale("log"); ax[0].set_xticks(range(len(names))); ax[0].set_xticklabels([n.replace("_", chr(10)) for n in names], fontsize=6.5)
    ax[0].set_title("European call test: RMSE vs Black-Scholes (log)")
    w = 0.38
    x = np.arange(len(names))
    ax[1].bar(x - w / 2, [real[k]["std"] / real[k]["mean"] * 100 for k in names], w, color=ORANGE, label="PFE99")
    ax[1].bar(x + w / 2, [real[k]["med_std"] / real[k]["med_mean"] * 100 for k in names], w, color=TEAL, label="median PFE")
    ax[1].set_xticks(x); ax[1].set_xticklabels([n.replace("_", chr(10)) for n in names], fontsize=6.5)
    ax[1].set_ylabel("relative std of estimator (%)"); ax[1].legend()
    ax[1].set_title("Real engine: estimator noise at equal N")
    return fig, opt, real


def fig_conv(D, meta):
    c99 = json.load(open(os.path.join(PROC, "convergence_study_tail_pfe99.json")))
    r99 = [r for r in c99["results"] if r["N"] != c99["N_pool"]]
    a = D["expo"]["__portfolio__"]
    jp = int(np.argmax(np.quantile(a, CONF, axis=1)))
    x = a[jp]
    M = len(x)
    rng = np.random.default_rng(5)
    Ns = [100, 250, 500, 1000, 1500, 2000]
    boot = []
    for N in Ns:
        q99, q50 = [], []
        for _ in range(400):
            sub = x[rng.choice(M, N, replace=False)]
            q99.append(np.quantile(sub, CONF)); q50.append(np.quantile(sub, 0.5))
        fpc = np.sqrt(1 - N / M)  # sampling without replacement from a finite pool understates the SE
        boot.append({"N": N, "se99": np.std(q99) / fpc / np.mean(q99) * 100, "se50": np.std(q50) / fpc / np.mean(q50) * 100})
    fig, ax = plt.subplots(1, 3, figsize=(7.6, 2.7))
    ax[0].loglog(Ns, [b["se99"] for b in boot], marker="o", ms=3, color=ORANGE, label="PFE99")
    ax[0].loglog(Ns, [b["se50"] for b in boot], marker="s", ms=3, color=TEAL, label="median PFE")
    ax[0].loglog(Ns, boot[0]["se99"] * np.sqrt(Ns[0] / np.array(Ns)), ls="--", color=GREY, label="1/sqrt(N)")
    ax[0].set_title("Relative SE at the peak-PFE date", fontsize=8); ax[0].set_xlabel("scenarios N"); ax[0].set_ylabel("% relative SE"); ax[0].legend()
    n2 = [r["N"] for r in r99]
    ax[1].loglog(n2, [r["relative_se_pct"] for r in r99], marker="o", ms=3, color=ORANGE)
    ax[1].set_title("PFE99 at 1y, 30,000-path pool", fontsize=8); ax[1].set_xlabel("scenarios N")
    g = [r["marginal_se_improvement_pct"] for r in r99]
    ax[2].bar(range(1, len(n2)), g[1:], color=ORANGE)
    ax[2].set_xticks(range(1, len(n2))); ax[2].set_xticklabels([("%dk" % (v // 1000)) if v >= 1000 else str(v) for v in n2[1:]], fontsize=6.5)
    ax[2].set_title("Marginal SE gain per step", fontsize=8); ax[2].set_xlabel("N reached")
    return fig, c99, r99, boot, D["rep_dates"][jp]


def fig_profiles(D):
    cp = ["CPTY_A", "CPTY_B", "CPTY_C", "__portfolio__"]
    fig, axs = plt.subplots(2, 2, figsize=(7.2, 5.0))
    for ax, c in zip(axs.ravel(), cp):
        p = prof(D["expo"][c])
        x = np.array(D["rep_t"]) * 365.25
        ax.fill_between(x, p["MED"] / 1e6, p["P99"] / 1e6, color=TEAL, alpha=0.15)
        ax.plot(x, p["P99"] / 1e6, color="#8B0000", lw=1.6, label="PFE99")
        ax.plot(x, p["EE"] / 1e6, color=NAVY, lw=1.8, label="EE")
        ax.plot(x, p["MED"] / 1e6, color=GOLD, lw=1.8, label="Median PFE")
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
    ax[1].plot(x, cmp_["mpor_shifted"]["CPTY_C"]["MedianExposure"] / 1e6, color=GOLD, label="MPOR median PFE")
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



def load_sa_cva():
    return json.load(open(os.path.join(PROC, "sa_cva_results.json")))


def fig_credit_curves():
    from risk_engine.market.credit_spreads import rating_spread_curve
    ref = date(2026, 8, 28)
    fig, ax = plt.subplots(figsize=(5.6, 2.6))
    tn = np.linspace(0.5, 10, 40)
    for rt, c in zip(("AA", "A", "BBB", "BB"), (NAVY, TEAL, ORANGE, GOLD)):
        t, sp = rating_spread_curve(rt, ref, tn)
        ax.plot(t, sp * 1e4, color=c, label=rt, lw=1.8)
    ax.set_xlabel("maturity (years)"); ax.set_ylabel("proxy credit spread (bp)"); ax.legend(ncol=4)
    ax.set_title("Proxy credit spread curves by rating (ICE BofA OAS, FRED, 2026-08-28)")
    return fig


def fig_cva_results(R_):
    fig, ax = plt.subplots(1, 3, figsize=(7.6, 2.7))
    t = np.array(R_["times"]) * 365.25
    for c, col in zip(("CPTY_A", "CPTY_B", "CPTY_C"), (NAVY, TEAL, ORANGE)):
        ax[0].plot(t, np.array(R_["dee"][c]) / 1e6, color=col, label=c)
    ax[0].set_title("Discounted EE", fontsize=8); ax[0].set_xlabel("days"); ax[0].set_ylabel("USD M"); ax[0].legend()
    cs = ["CPTY_A", "CPTY_B", "CPTY_C"]
    ax[1].bar(range(3), [R_["cva_by_cpty"][c] / 1e3 for c in cs], color=[NAVY, TEAL, ORANGE])
    ax[1].set_xticks(range(3)); ax[1].set_xticklabels(cs, fontsize=7); ax[1].set_title("CVA at BBB (USD k)", fontsize=8)
    rt = list(R_["cva_vs_rating"])
    ax[2].bar(range(len(rt)), [R_["cva_vs_rating"][r] / 1e3 for r in rt], color=PAL[:len(rt)])
    ax[2].set_xticks(range(len(rt))); ax[2].set_xticklabels(rt, fontsize=7); ax[2].set_title("CVA by rating (USD k)", fontsize=8)
    return fig


def fig_sa_cva(R_):
    S_ = R_["sensitivities"]
    fig, ax = plt.subplots(1, 3, figsize=(7.6, 2.7))
    ax[0].bar(range(5), np.array(S_["ir_delta"]) / 1e6, color=NAVY)
    ax[0].set_xticks(range(5)); ax[0].set_xticklabels(["1y", "2y", "5y", "10y", "30y"], fontsize=7)
    ax[0].set_title("IR delta (USD M / 1.0)", fontsize=8)
    ct = list(S_["ccs_delta"])
    ax[1].bar(range(len(ct)), [S_["ccs_delta"][k] / 1e6 for k in ct], color=[ORANGE if "CPTY_C" in k else TEAL for k in ct])
    ax[1].set_xticks([]); ax[1].set_title("Cpty spread delta (USD M / 1.0)", fontsize=8)
    cap = R_["capital_by_class"]
    ks = list(cap)
    ax[2].barh(range(len(ks)), [cap[k] / 1e6 for k in ks], color=NAVY)
    ax[2].set_yticks(range(len(ks))); ax[2].set_yticklabels([k.replace("_", " ") for k in ks], fontsize=7)
    ax[2].invert_yaxis(); ax[2].set_title("Capital by class (USD M)", fontsize=8)
    return fig


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
    add(titlepage("Monte Carlo Counterparty Credit Risk Engine",
                  "Methodology, calibration and results for the ESF derivatives book",
                  "Prepared for Capitolis | Berkeley MFE Industry Project",
                  "Valuation date 2026-08-28 | September 2026"))
    add("\\section*{Abstract}\n")
    add(P("This report describes a Monte Carlo counterparty credit risk (CCR) engine for Capitolis' equity swap financing "
          "(ESF) derivatives book, which comprises 16 trades with three counterparties. The engine simulates the joint evolution "
          "of the USD short rate (one-factor Hull-White model), 37 equities and USDJPY (correlated geometric Brownian motion), "
          "reprices every trade in every scenario with the supplied pricer library, and reports Expected Exposure (EE), median "
          "PFE, Potential Future Exposure at the 99th percentile (PFE99) and Maximum PFE (MPE) by counterparty and for the "
          "portfolio, prices counterparty credit risk (CVA) with bond-implied credit spreads, computes the Basel SA-CVA capital requirement, and provides the full set of sensitivities (Greeks) of the book and of the exposure measures. The report sets out the underlying concepts from first principles, the market data and calibration, each "
          "modelling choice together with the alternatives considered, the validation performed, and the results. Every "
          "quantity is either measured from the engine on real market data as of 2026-08-28 or is an explicitly stated assumption."))
    add(make_toc())
    add(PageBreak())
    add("\\section*{Summary of results}\n")
    add(P("The table reports the portfolio results for the uncollateralized book (3,000 Latin Hypercube scenarios, PFE at the 99th percentile).", BODY))
    ce0 = {c: float(per[c]["EE"][0]) for c in per}
    Rc0 = load_sa_cva()
    add(tbl([["Measure", "Value", "Meaning"],
             ["Current exposure (portfolio)", m(tot["EE"][0]), "Loss if every counterparty defaulted today, after netting"],
             ["Peak EE", f"{m(tot['EE'].max())} at {D['rep_dates'][int(tot['EE'].argmax())]}", "Highest average future exposure"],
             ["Peak median PFE", f"{m(tot['MED'].max())} at {D['rep_dates'][int(tot['MED'].argmax())]}", "Typical (50th percentile) exposure at its highest date"],
             ["Maximum PFE99 (MPE)", f"{m(mpe99)} at {D['rep_dates'][j_mpe]}", "Highest 99th-percentile exposure over the life of the book"],
             ["Concentration", f"{ce0['CPTY_C']/max(tot['EE'][0],1)*100:.0f}% of current exposure is CPTY_C", "A single $500M bond forward (BF_0003) dominates"],
             ["Time profile", "Most exposure has run off by December 2026", "Trades mature; a small Bond TRS tail runs to January 2028"],
             ["Greeks", "t = 0 book Greeks; sensitivities of EE, median PFE and PFE99 to equities, USDJPY, USD rates and volatilities", "Complete, by netting set (Section 9)"],
             ["CVA (BBB proxy)", "$" + format(Rc0["cva_total"], ",.0f"), "Price of counterparty default risk, unilateral, uncollateralized (Section 8)"],
             ["SA-CVA capital", "$%.2fM (RWA $%.1fM)" % (Rc0["K_sa_cva"] / 1e6, Rc0["RWA"] / 1e6), "Basel standardised approach; dominated by counterparty credit spread risk"]],
            widths=[2.3, 2.3, 3.4]))
    add(P("<b>Principal modelling choices</b> (each is justified in Section 10):", BODY))
    add(B([
        "Monte Carlo under the risk-neutral measure. USD short rate: one-factor Hull-White (exact fit to today's SOFR curve). Equities and USDJPY: correlated geometric Brownian motion driven by the simulated rate.",
        "Correlation: one static 39x39 matrix estimated from 613 aligned daily returns and applied through a Cholesky factor; a PCA factor model (5 factors) is provided as an alternative.",
        "Sampling and size: Latin Hypercube sampling (lowest error of the five methods tested) with N = 5,000 scenarios for standard reporting (PFE99 relative standard error about 1% at the worst-case date), N = 1,000 for iteration and N = 10,000 for limit sign-off (Section 5.5).",
        "Dates: standard market pillar dates (O/N to 10Y) with every trade's own reset and maturity date forced onto the grid.",
        "Mean reversion: a = 0.0167 for USD from the swaption cube; for JPY the lower bound a = 0.001, because real JPY volatility rises with tenor (three independent sources, including the full daily OIS history).",
        "JPY: a negative-rate-capable Hull-White factor is built (sigma from real TONA; correlation with the USD rate calibrated at approximately zero) but does not yet drive JPY equity drift.",
        "The book is treated as uncollateralized (no CSA data); an MPOR-shifted collateralized calculation is built and demonstrated as a hypothetical.",
        "CVA: unilateral regulatory CVA (MAR50.32) with counterparty spreads proxied from ICE BofA bond indices by an assumed BBB rating and 60% LGD; SA-CVA capital from common-random-number bump sensitivities (Section 8)."]))
    add(PageBreak())

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
             ["Median PFE", "50th percentile of exposure across scenarios at date t", "The typical scenario. Exposure is floored at zero: the median is below EE when exposure is right-skewed (most scenarios small, a few large) and can be exactly zero when most scenarios are out of the money; it can sit slightly above EE when the book is almost always in the money, as for the dominant CPTY_C forward"],
             ["PFE99 (Potential Future Exposure)", f"The {int(CONF*100)}th percentile of exposure at date t", "In 99 of 100 scenarios exposure at t is below this level. Used to set limits"],
             ["MPE (Maximum PFE)", "Peak of the PFE curve over all dates", "One number to set a counterparty limit against"]],
            widths=[1.5, 2.6, 3.6]))
    add(P("<b>Confidence level.</b> PFE is reported at the 99th percentile throughout, together with the median PFE (the 50th percentile of the same exposure distribution), which describes the typical scenario."))
    add(doc.figure(fig_concept_exposure(), "Left: simulated values of a portfolio through time. Right: the same paths after applying max(V,0); EE is their average."))
    add(doc.figure(fig_measures_illustration(D), "The real portfolio exposure distribution ~3 months out, with EE, median PFE and PFE99 marked. The long right tail is why EE, median PFE and PFE99 differ so much."))
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
          "unobservable inputs and is verified by a martingale test (Section 11). Because the horizon is short (under two years) and most "
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
             ["JPY OIS par-rate history, 35 tenors, 2011-2026", "Bloomberg export provided by the project team (data/raw/sources/JPY.xlsx)", "JPY curve, JPY factor volatility, JPY-USD differential, mean-reversion test", "Licensed data: only derived quantities are reported"],
             ["USD and JPY swaption cubes, USDJPY forwards", "Bloomberg one-time export, 2026-08-31 snapshot", "USD mean reversion, cross-checks, FX forwards", "Licensed data: only derived quantities are reported"],
             ["TONA (JPY overnight rate)", "Bank of Japan public API, daily from 1998", "JPY rate vol, USD-JPY correlation", "Includes real negative-rate years"],
             ["JGB par yields 1Y-40Y", "Japan Ministry of Finance, daily from 1974", "JPY mean-reversion test", "Public"]],
            widths=[1.5, 2.2, 1.8, 2.2], font=7.3))
    add(Spacer(1, 6))
    add(P("3.1 The USD curve", H2))
    add(P("Databento provides the futures, not a ready OIS curve, so we build one: each 3-month SOFR future price gives an implied forward rate (100 - price) for its "
          "reference quarter; chaining consecutive quarters multiplies discount factors. Beyond the last live contract (about 6.3 years out) the curve is extrapolated flat. "
          "Two real bugs were found here by cross-checking with the Treasury curve (Section 12). The curve is the starting point of the Hull-White model and the discount curve at t=0."))
    add(doc.figure(fig_curve(calib), "The bootstrapped USD SOFR curve. The upward slope (zero rate about 3.7% at the front, above 4% by 6 years) means forwards exceed spot rates."))
    add(P("3.2 Volatilities", H2))
    add(P("Volatility is the annualised standard deviation of daily changes over the last three years (log returns for equities and FX; simple differences for the rate, "
          "because rate LEVELS near or below zero make log returns meaningless). Rate vol: %.2f%% per year (normal vol on SOFR)." % (calib["gbm"].vols.get("RATE_USD", 0) * 100 if "RATE_USD" in calib["gbm"].vols else 0.6311)))
    add(doc.figure(fig_vols(calib), "Realised volatility spans an order of magnitude across the 37 names. A few names carry 50-76% vol, which dominates tail exposure of the trades that reference them."))
    add(P("<b>Choice and alternative.</b> Implied volatility from options would be forward-looking and is the norm for pricing, but we had no single-name options data (the Bloomberg "
          "export has only SPX/TOPIX index vols, which would need a per-name basis assumption). A 3-year realised window is a documented, reproducible proxy. Its limitation is that it "
          "is backward-looking and cannot see regime changes; the sensitivity test (Section 11) shows how much the results move if vols are 50% higher."))
    add(P("3.3 Correlations", H2))
    fig_c, off = fig_corr(calib)
    add(doc.figure(fig_c, "Left: the 39x39 correlation matrix reordered so similar names sit together; a broad positive 'market' block is visible. Right: the 741 pairwise correlations centre on %.2f." % off.mean()))
    add(P("<b>Estimation and stationarity.</b> The matrix is static, not re-estimated per date. We take the daily returns of all 39 factors, keep only the 613 dates on which every series has a price "
          "(US and Tokyo trade on different calendars, so series are joined by calendar date rather than timestamp), and compute one pairwise correlation matrix. It is assumed "
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
          "(so equities and rates are linked). Under the risk-neutral measure the expected growth is r - q, verified in Section 11 by a martingale test."))
    add(P("<b>Why GBM.</b> It matches the lognormal vol convention we measure, is the market default for equity CCR, and needs only a vol per name. <b>Alternatives:</b> local/stochastic vol "
          "(Heston, SABR) would capture skew and vol-of-vol but need option surfaces we do not have; jump models help tails but add unobservable parameters. We disclose that GBM understates fat tails."))
    add(doc.figure(fig_fx_eq_fan(D, calib), "Simulated USDJPY and two equities (a low-vol and the highest-vol name) with 1-99 and 25-75 percent bands."))
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
    from risk_engine.market import jpy_ois
    _h = jpy_ois.load_jpy_ois_history()
    _cols = [c for c in _h.columns if c.startswith("JYSO") and jpy_ois.tenor_years(c) <= 5.0]
    add(P("The daily JPY OIS history provided by the project team (35 tenors, %d business days from October 2011) shows the same for the whole short end of the curve: the overnight call rate was negative on %d days, and OIS par rates out to five years were negative on %d days, with a minimum of %.2f%%." % (len(_h), int((_h["MUTKCALM"] < 0).sum()), int((_h[_cols] < 0).any(axis=1).sum()), _h.min().min())))
    fg, frac = fig_ou_negative()
    add(doc.figure(fg, "Demonstration of the capability: Hull-White started from a synthetic -0.10%% flat curve. %.0f%% of simulated points are negative and nothing is clipped. (Our only real JPY curve snapshot, Aug 2026, is positive after BOJ hikes, so the negative case is shown synthetically.)" % (frac * 100)))
    hj = meta["hw_jpy"]
    add(tbl([["JPY factor parameter", "Value", "Source / status"],
             ["Curve", "JPY OIS zero curve, 2026-08-28", "Bootstrapped from the daily JPY OIS par history (project-team Bloomberg file); matches Bloomberg's own zero curve to within 1bp at all tenors"],
             ["sigma", "%.3f%%/yr" % (hj["sigma"] * 100), "Realised vol of the overnight call rate, 3y window, from the same OIS file (Bank of Japan TONA gives 0.276%, consistent)"],
             ["a (mean reversion)", "%.4f" % hj["a"], "Lower bound: all three real JPY calibrations gave a negative a (Section 6.2)"],
             ["USD-JPY rate-factor correlation", "%+.3f" % meta["usd_jpy_corr"], "Calibrated from real SOFR vs TONA daily changes (n=%d, p=%.2f): statistically zero" % (meta["usd_jpy_corr_detail"]["n_obs"], meta["usd_jpy_corr_detail"]["p_value"])],
             ["Wired into simulate_paths()?", "NO (disclosed)", "JPY equity/FX drift still uses r_USD minus the constant differential (%.2f%%, our USD curve minus the JPY OIS zero curve at one year)" % (meta["jpy_usd_rate_diff"] * 100)]],
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
             "6. aggregate:   net by counterparty -> max(.,0) -> EE, median PFE, PFE99, MPE"))
    add(P("5.2 Choosing the simulation dates", H2))
    add(P("Monthly steps are simple but wasteful and blunt: they spend nodes evenly when the risk changes fastest near term, and a trade's own reset or maturity rarely falls on a month node. "
          "Following Capitolis' guidance, we adopt <b>pillar dates</b>: the standard market curve tenors also used to build the SOFR curve (O/N, T/N, 1W, 2W, 1M, 2M, 3M, 6M, 9M, 1Y, 18M, 2Y ...). "
          "This mirrors production CCR practice: dense short-term, sparse long-term. In addition, every trade's own reset/settlement/maturity date is <b>forced onto the grid</b> so "
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
    rel99 = {k: real[k]["std"] / real[k]["mean"] * 100 for k in real}
    rel50 = {k: real[k]["med_std"] / real[k]["med_mean"] * 100 for k in real}
    add(doc.figure(fg, "Left: on a European call with a known Black-Scholes value, Latin Hypercube has about %.0fx lower error than pseudo-random. Right: on the real 663-dimensional engine (300 scenarios, 8 repeats) the methods are much closer, and no method is best for both PFE99 and the median PFE." % (opt["pseudo_random"]["rmse"] / opt["latin_hypercube"]["rmse"])))
    verdicts = {"pseudo_random": "Baseline",
                "antithetic": "Improves both measures modestly on the real engine, but only 1.4x on the controlled test",
                "moment_matched": "Helps the median only; no PFE99 benefit",
                "sobol": "Best PFE99 on the real engine but no median benefit; unscrambled Sobol degrades in high dimension and is harder to replicate",
                "latin_hypercube": "SELECTED: 50x on the controlled test and improves both PFE99 and median PFE on the real engine"}
    rows = [["Method", "Call RMSE", "vs pseudo-random", "PFE99 rel. std (real engine)", "Median PFE rel. std (real engine)", "Verdict"]]
    for k in opt:
        rows.append([k.replace("_", " "), "%.4f" % opt[k]["rmse"], "%.1fx better" % (opt["pseudo_random"]["rmse"] / opt[k]["rmse"]) if k != "pseudo_random" else "-",
                     "%.2f%% (%.2fx)" % (rel99[k], rel99["pseudo_random"] / rel99[k]), "%.2f%% (%.2fx)" % (rel50[k], rel50["pseudo_random"] / rel50[k]), verdicts[k]])
    add(tbl(rows, widths=[1.2, 0.8, 1.0, 1.4, 1.5, 3.0]))
    add(P("Relative standard deviation of the estimator across 8 independent repeats at 300 scenarios (portfolio, about 6 weeks out, near the PFE99 peak); the multiple in brackets is the improvement over pseudo-random. With only 8 repeats each standard deviation is itself uncertain by roughly a quarter, so real-engine differences between the better methods are indicative rather than conclusive.", SMALL))
    add(P("<b>Finding.</b> The controlled test gives a clear ordering (Latin Hypercube, Sobol, moment matching, antithetic, pseudo-random). On the real engine, at 663 effective dimensions (39 factors x 17 time steps), the advantages compress and the ranking depends on the statistic: the tail (PFE99) and the centre (median PFE) respond to different methods. Latin Hypercube is the only method that is both best on the controlled test and better than pseudo-random on both real-engine statistics."))
    add(callout("<b>Decision: Latin Hypercube sampling.</b> It is the best method on the controlled test and the most consistent across both reported statistics on the real engine, at negligible additional cost over plain pseudo-random draws. Sobol is the runner-up on the controlled test but is not recommended here because its benefit disappears for the median PFE and it is less robust at this dimensionality."))
    add(PageBreak())

    add(P("5.5 Number of scenarios", H2))
    add(P("Monte Carlo error falls as 1/sqrt(N). Rather than rerun the expensive repricing at every candidate N, we estimate the standard error by bootstrap resampling of a simulated pool. Two studies are combined: (i) resampling of the 3,000-scenario reporting run, at the date of peak PFE99, for both PFE99 and the median PFE; (ii) a dedicated 30,000-scenario pool for the 99th percentile at the one-year node, which extends the range to large N."))
    fg, c99, r99, boot, jdate = fig_conv(D, meta)
    add(doc.figure(fg, "Left: relative standard error of PFE99 and median PFE at the peak-PFE date (%s); the error follows the 1/sqrt(N) law. Middle and right: PFE99 tail study at one year; error is larger for the same N, and the marginal gain per additional batch peaks at N = 5,000 and then declines." % jdate))
    rows = [["N", "Relative SE of PFE99", "Relative SE of median PFE"]]
    for b in boot:
        rows.append([format(b["N"], ","), "%.2f%%" % b["se99"], "%.2f%%" % b["se50"]])
    c_se = float(np.mean([b["se99"] * np.sqrt(b["N"]) for b in boot[2:]]))  # SE(N) = c_se / sqrt(N)
    se_at = lambda n_: c_se / np.sqrt(n_)
    se3000 = se_at(3000)
    add(tbl(rows, widths=[1.0, 2.0, 2.0]))
    add(P("Relative standard errors at the peak-PFE date, bootstrapped from the reporting run (finite-pool corrected). Extrapolating with the 1/sqrt(N) law, the 3,000-scenario run used for this report has a PFE99 relative standard error of about %.2f%% at its peak." % se3000, SMALL))
    verdicts_n = {500: "Screening only", 1000: "Iteration and what-if runs", 2000: "Acceptable for routine monitoring", 5000: "RECOMMENDED: standard reporting",
                  10000: "Recommended for limit sign-off", 15000: "Diminishing returns", 20000: "Diminishing returns", 25000: "Diminishing returns"}
    rows = [["N", "PFE99 at 1y (USD)", "Rel. SE at 1y", "Rel. SE at peak date (est.)", "Marginal SE gain (1y)", "Est. time", "Verdict"]]
    for r in c99["results"]:
        if r["N"] == c99["N_pool"]:
            continue
        rows.append([format(r["N"], ","), format(r["PFE_mean"], ",.0f"), "%.2f%%" % r["relative_se_pct"], "%.2f%%" % se_at(r["N"]),
                     "-" if r["marginal_se_improvement_pct"] is None else "%+.1f%%" % r["marginal_se_improvement_pct"],
                     "%ss" % format(r["est_time_s"], ",.0f"), verdicts_n[r["N"]]])
    add(tbl(rows, widths=[0.7, 1.1, 0.9, 1.3, 1.1, 0.8, 2.1]))
    add(P("Tail study at the one-year node (pool value $%s, 30,000 scenarios) and the corresponding estimate at the date of peak PFE99, where the exposure distribution is wider (relative SE = %.1f%% / sqrt(N/1000), fitted to the reporting-run bootstrap). Times assume 8 cores." % (format(c99["pool_pfe_reference"], ",.0f"), se_at(1000)), SMALL))
    add(callout("<b>Decision: number of paths.</b> Use <b>N = 5,000</b> for standard PFE99 reporting: relative standard error %.1f%% at the worst-case date (0.29%% at the one-year node), about 8 minutes on 8 cores. Use <b>N = 1,000</b> for iteration and what-if runs (%.1f%% at the worst-case date, about 2 minutes) and <b>N = 10,000</b> when a limit is being signed off (%.1f%%, about 15 minutes). We do not recommend more than 15,000: cost grows linearly while error falls only as 1/sqrt(N), and the remaining sampling error (below %.1f%%) is an order of magnitude smaller than the model sensitivities in Section 11.4 (a 50%% increase in equity volatility moves MPE by about 9%%). The figures in this report use N = 3,000 (%.1f%% at the worst-case date)." % (se_at(5000), se_at(1000), se_at(10000), se_at(15000), se3000)))
    add(PageBreak())

    # ---------- 6 calibration
    add(P("6. Calibrating Hull-White mean reversion", H1))
    add(P("Mean reversion a controls how fast rate shocks decay; the convergence study flagged it as the largest unquantified model uncertainty. The textbook method is to fit swaption "
          "volatilities. Hull-White predicts that the volatility of a forward rate at maturity T decays with time to maturity:"))
    add(code("sigma_f(t, T) = sigma * exp( -a (T - t) )      =>   ln(vol) = ln(sigma) - a * tenor   (line, slope = -a)"))
    add(P("So measuring vol at several tenors and regressing ln(vol) on tenor gives a. We tried three real data routes, in order of preference:"))
    fg, h, sw, sj, jg, oi = fig_hw_fit(calib)
    add(doc.figure(fg, "Left: USD SOFR-futures fit. Right: fitted a for each route. USD routes give sensible positive values; all three JPY routes give a NEGATIVE a."))
    add(tbl([["Route", "Data", "a", "R2", "Verdict"],
             ["Swaption cube, USD (preferred)", "Bloomberg ATM normal vol, 1M expiry, tenors 1Y-15Y", "%.4f" % sw["a"], "%.2f" % sw["r_squared"], "USED for USD"],
             ["SOFR-futures vol decay, USD", "8 contracts, ~2y Databento history", "%.4f" % h["a"], "%.2f" % h["r_squared"], "cross-check (different instrument, higher a)"],
             ["Swaption cube, JPY", "Bloomberg JPY OIS ATM vols (one snapshot)", "%.4f" % sj["a"], "%.2f" % sj["r_squared"], "invalid (vol rises with tenor)"],
             ["JGB yield vol, JPY", "MOF daily 1Y-30Y yields, 3y window", "%.4f" % jg["a"], "%.2f" % jg["r_squared"], "invalid (vol rises with tenor)"],
             ["JPY OIS history, JPY (most complete)", "Daily OIS par rates, 35 tenors, 2011-2026, 1Y-30Y vols, 3y window", "%.4f" % oi["a"], "%.2f" % oi["r_squared"], "invalid (vol rises with tenor); lower bound a = 0.001 used"]],
            widths=[2.0, 2.6, 0.8, 0.6, 2.0]))
    add(Spacer(1, 5))
    add(P("6.1 Why the two USD numbers differ", H2))
    add(P("0.0167 (swaptions) versus 0.0458 (futures) is not a contradiction: they use different instruments (swaption-implied vs realised vol) and different tenor ranges (1-15Y swap tenors vs 1-3Y forward reset times). "
          "The swaption route is the industry standard and is used; the gap is itself a measure of model uncertainty and motivates the sensitivity test."))
    add(P("6.2 Why JPY does not fit, and what we did", H2))
    fj = fig_jgb_vol()
    add(doc.figure(fj, "Realised volatility of JPY rates by tenor from two independent real datasets. At every window tried (1y, 3y, 10y) long tenors are MORE volatile than short ones, the reverse of the decay Hull-White assumes."))
    add(P("This is not bad data; it is a structural finding confirmed by three independent real sources: the daily JPY OIS curve history (35 tenors, 2011 to 2026, provided by the project team and the most complete of the three), 52 years of JGB yields, and a 2026 swaption cube. The fitted a is negative for the OIS history in every window tested (1, 3, 5, 10 and 15 years, and since the end of negative rates in March 2024). One factor, the level, explains about 84% of daily changes in the curve, and long rates move more than short rates. The plausible reason is that for two decades the Bank of Japan pinned the SHORT end (zero and negative policy rates, yield-curve control), so short-tenor volatility was suppressed while longer tenors moved more freely. A single mean-reverting Gaussian factor implies volatility that DEcreases with tenor, so it cannot represent this shape, and a negative a would make the short rate diverge."))
    add(P("<b>Choice:</b> use the lowest admissible mean reversion, a = %.4f, the Ho-Lee limit in which volatility is flat across tenors. This is the closest a Gaussian factor can get to the data, and it replaces our earlier use of the USD value. A two-factor or regime-dependent model would be needed to match the shape, and is listed under future work." % meta["hw_jpy"]["a"]))
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
    add(doc.figure(fig_profiles(D), "EE, median PFE and PFE99 for each counterparty and the portfolio. The shaded band runs from the median PFE to PFE99."))
    rows = [["Counterparty", "EE(0)", "Peak EE", "Peak median PFE", "MPE (peak PFE99)", "MPE date"]]
    for c in ("CPTY_A", "CPTY_B", "CPTY_C", "__portfolio__"):
        p = prof(D["expo"][c]); jj = int(p["P99"].argmax())
        rows.append([("Portfolio" if c == "__portfolio__" else c), m(p["EE"][0]), m(p["EE"].max()), m(p["MED"].max()), m(p["P99"].max()), str(D["rep_dates"][jj])])
    add(tbl(rows, widths=[1.3, 1.0, 1.0, 1.3, 1.5, 1.2]))
    add(Spacer(1, 4))
    add(P("<b>Reading the shape.</b> Exposure peaks soon after today and then falls steeply as trades mature. By the end of December 2026 the portfolio EE has fallen by more than 90%; the "
          "remainder is the Bond TRS BTRS_0001 and the year-long EQTRS_0008. So almost all counterparty credit risk sits in the next four months and monitoring should be concentrated there."))
    add(P("<b>EE, median PFE and PFE99.</b> The median PFE is far below EE for the counterparties with more than half of scenarios at zero exposure (CPTY_B especially): EE is pulled up by the right tail, "
          "the median PFE describes the typical outcome, and PFE99 describes the adverse tail. Reporting all three prevents any single statistic from misleading."))
    add(doc.figure(fig_prob_positive(D), "Probability that a counterparty has any positive exposure at all. Where this is far below 100%, the median PFE is zero even though EE and PFE99 are large."))
    add(doc.figure(fig_dists(D), "Portfolio exposure histograms (log count) at four dates with median (gold), EE (navy) and PFE99 (red). The right tail lengthens with time."))
    add(PageBreak())

    add(P("7.3 Where does the risk come from?", H2))
    add(doc.figure(fig_trade_heat(D), "Expected NPV by trade at each reporting date. CPTY_C's BF_0003 dominates the picture and disappears at its 2026-12-06 settlement; a few equity TRS contribute negative expected NPV."))
    cC = per["CPTY_C"]
    add(P("<b>Concentration.</b> CPTY_C accounts for %.0f%% of the portfolio's peak PFE99 and %.0f%% of today's exposure, and almost all of it comes from one trade, BF_0003 (500M notional, short forward struck at 100 on a long-dated 2.88%% 2049 Treasury trading roughly 20 points below par, so we are owed the difference). This is concentration risk rather than diversified counterparty risk; a limit or collateral on that single trade would move the portfolio number more than any modelling choice in this report." % (
              cC["P99"].max() / tot["P99"].max() * 100, ce0["CPTY_C"] / max(tot["EE"][0], 1) * 100)))
    add(P("7.4 What if the counterparty posts margin? (MPOR-shifted exposure)", H2))
    add(P("The real book is treated as <b>uncollateralized</b> because trade_data carries no CSA terms. For a collateralized counterparty, default does not mean instant close-out: there is a Margin Period of Risk "
          "(standard 10 business days) between the last collateral exchange and the actual replacement of the trades. The relevant exposure is what the position could gain in that window beyond the collateral held:"))
    add(code("C(t)        = max( V(t) - threshold, 0 )        collateral held at reporting date t\n"
             "Exposure(t) = max( V(t + MPOR) - C(t), 0 )      same simulated path, MPOR days later"))
    add(P("Implementation: an extra look-ahead node is inserted MPOR days after every reporting node on the same simulated path (no separate simulation). The demonstration below is explicitly hypothetical: "
          "full variation margin (threshold 0), MPOR 10 business days, 3,000 scenarios."))
    fg, cmp_, cp, u, mp = fig_mpor(D)
    add(doc.figure(fg, "If a full-VM CSA existed, peak PFE99 would fall sharply, most of all for CPTY_C whose exposure is a large, already-visible MTM that margin would cover."))
    rows = [["Counterparty", "Uncollateralized MPE99", "MPOR-shifted MPE99", "Reduction"]]
    for c, a1, a2 in zip(cp, u, mp):
        rows.append([c, f"${a1:,.1f}M", f"${a2:,.1f}M", f"{(1 - a2 / a1) * 100 if a1 > 0 else 0:.0f}%"])
    add(tbl(rows, widths=[1.5, 2.0, 2.0, 1.2]))
    add(P("<b>Relation to SIMM and Basel.</b> The 10-day figure is the convention shared by both frameworks. Under the Basel counterparty credit risk rules (SA-CCR and the internal models method) the margin period of risk for a margined bilateral OTC netting set is at least 10 business days, 5 business days for centrally cleared trades and 20 business days for large or illiquid netting sets, and it lengthens after margin disputes. The ISDA Standard Initial Margin Model (SIMM) is a different object: a sensitivity-based methodology for the <i>initial margin</i> that the uncleared margin rules require counterparties to post, calibrated to a 99% one-tailed loss over a 10-day horizon using a stress period. Initial margin is collateral posted in addition to variation margin and held against precisely the close-out window described above."))
    add(P("Our engine does <b>not</b> implement SIMM and does not model initial margin. The calculation in this section is a variation-margin-only illustration: a threshold of zero removes any unsecured amount, but there is no initial margin buffer. If initial margin were posted it would absorb part of the 10-day move and reduce the exposure shown further; quantifying that requires computing SIMM sensitivities for each netting set, which we have not attempted. Two simplifications should also be noted: the look-ahead is exactly 10 business days (Monday to Friday, US federal holidays skipped; the SIFMA bond-market calendar differs marginally), and no minimum transfer amount is modelled."))
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

    # ---------- 8 CVA
    Rc = load_sa_cva()
    cpt = ["CPTY_A", "CPTY_B", "CPTY_C"]
    add(P("8. Credit valuation adjustment and SA-CVA capital", H1))
    add(P("Sections 1 to 7 measure how much a counterparty could owe us. This section prices the risk that they fail to pay it (credit valuation adjustment, CVA) and computes the Basel regulatory capital held against the volatility of that CVA under the Standardised Approach (SA-CVA). Both reuse the exposure engine unchanged."))
    add(P("8.1 Definition", H2))
    add(P("CVA is the expected loss from counterparty default, assuming the bank itself cannot default (unilateral CVA). Following Basel MAR50.32:"))
    add(code("CVA = LGD * sum_i  0.5 * [ DEE(t_{i-1}) + DEE(t_i) ] * PD(t_{i-1}, t_i)\n"
             "DEE(t) = E[ D(t) * max(V(t), 0) ]            D = pathwise risk-free discount factor\n"
             "PD(t_{i-1}, t_i) = exp(-s_{i-1} t_{i-1}/LGD) - exp(-s_i t_i/LGD)      (market-implied, from spreads)"))
    add(P("The expected discounted exposure DEE is the exposure profile of Section 7 with each scenario discounted along its own simulated short rate. The default probability is implied by a credit spread s through the credit-triangle relation with a loss given default LGD of 60% (40% recovery, the senior unsecured convention). Exposure and default are assumed independent, so wrong-way risk is excluded, and the book is treated as uncollateralized because no margin terms are available."))
    add(P("8.2 Credit inputs: rating proxies from bond spreads", H2))
    add(P("CDS spreads for the counterparties are not available, and the counterparties are anonymised. MAR50.32(3) permits an illiquid counterparty's spread to be proxied from liquid peers by credit quality, industry and region. We proxy by credit quality using public bond-market data: the ICE BofA US corporate option-adjusted spread indices by rating (FRED), with the maturity shape taken from the ICE BofA corporate index by maturity bucket, scaled to each rating. The rating-level spread is one number per rating, so the same maturity shape is used for all ratings (a disclosed simplification)."))
    add(P("<b>Sources.</b> Rating spreads: FRED series BAMLC0A1CAAA (AAA), BAMLC0A2CAA (AA), BAMLC0A3CA (A), BAMLC0A4CBBB (BBB), BAMLH0A1HYBB (BB) and BAMLH0A2HYB (B), ICE BofA US option-adjusted spreads. Maturity shape: BAMLC1A0C13Y, BAMLC2A0C35Y, BAMLC3A0C57Y and BAMLC4A0C710Y relative to BAMLC0A0CM (all US corporate). Basel parameters: Bank for International Settlements, Targeted revisions to the credit valuation adjustment risk framework (July 2020), MAR50. Equity bucket attributes (sector, country, market capitalisation): yfinance."))
    add(doc.figure(fig_credit_curves(), "Proxy spread curves by rating on the valuation date. The BBB curve used for the counterparties runs from about %.0f bp at 6 months to about %.0f bp at 10 years." % (Rc["spread_curves_bp"]["CPTY_A"][0], Rc["spread_curves_bp"]["CPTY_A"][-1])))
    add(tbl([["Counterparty", "Assumed rating", "Assumed sector", "Basis"],
             ["CPTY_A", Rc["ratings"]["CPTY_A"], "Financials (SA-CVA bucket 2)", "Assumption: unrated counterparty proxied at BBB"],
             ["CPTY_B", Rc["ratings"]["CPTY_B"], "Financials (SA-CVA bucket 2)", "Assumption"],
             ["CPTY_C", Rc["ratings"]["CPTY_C"], "Financials (SA-CVA bucket 2)", "Assumption"]], widths=[1.2, 1.2, 2.2, 3.0]))
    add(P("The counterparty identities and ratings were not provided, so these are explicit assumptions. Because they matter more than any modelling choice, Section 8.3 reports CVA across the whole rating range so the reader can substitute the correct rating."))
    add(P("8.3 Results: CVA", H2))
    add(doc.figure(fig_cva_results(Rc), "Left: expected discounted exposure by counterparty. Middle: CVA by counterparty at the BBB proxy. Right: portfolio CVA if all counterparties had the rating shown."))
    rows = [["Counterparty", "CVA (USD)", "Share of total"]]
    for c in cpt:
        rows.append([c, format(Rc["cva_by_cpty"][c], ",.0f"), "%.0f%%" % (Rc["cva_by_cpty"][c] / Rc["cva_total"] * 100)])
    rows.append(["Portfolio", format(Rc["cva_total"], ",.0f"), "100%"])
    add(tbl(rows, widths=[2.0, 2.0, 1.5]))
    rows = [["Rating", "Portfolio CVA (USD)", "Multiple of BBB"]]
    for r_, v in Rc["cva_vs_rating"].items():
        rows.append([r_, format(v, ",.0f"), "%.2fx" % (v / Rc["cva_vs_rating"]["BBB"])])
    add(tbl(rows, widths=[1.2, 2.2, 1.5]))
    add(P("CVA is concentrated where the exposure is: CPTY_C carries %.0f%% of it, as it carries almost all of the exposure. CVA scales approximately linearly with the credit spread, so the rating assumption moves the result by a factor of about %.1f between AA and BB. These figures use %s scenarios (Latin Hypercube) with common random numbers across the sensitivity runs of Section 8.4." % (Rc["cva_by_cpty"]["CPTY_C"] / Rc["cva_total"] * 100, Rc["cva_vs_rating"]["BB"] / Rc["cva_vs_rating"]["AA"], format(Rc["n_scenarios"], ","))))
    add(P("8.4 Basel SA-CVA capital", H2))
    add(P("SA-CVA (MAR50.27 to 50.77) sets capital from the sensitivity of regulatory CVA to market risk factors. It is an adaptation of the market-risk standardised approach and needs supervisory approval, a CVA desk and monthly sensitivity calculation (MAR50.30); the figures here are therefore indicative of the requirement, not a filed number. For each risk factor k the CVA sensitivity s_k is computed by bump-and-reprice with common random numbers, converted to a weighted sensitivity WS_k = RW_k x s_k, and aggregated by bucket and risk class:"))
    add(code("K_b = sqrt( sum_k WS_k^2 + sum_{k!=l} rho_kl WS_k WS_l )        S_b = clip( sum_k WS_k, -K_b, +K_b )\n"
             "K   = m_CVA * sqrt( sum_b K_b^2 + sum_{b!=c} gamma_bc S_b S_c )\n"
             "Capital = sum over classes of ( K_delta + K_vega );   RWA = 12.5 * Capital"))
    add(P("Risk classes present in the book, the shift used for each sensitivity and the Basel parameters applied:"))
    add(tbl([["Risk class", "Risk factors and shift", "Risk weight", "Correlation"],
             ["Interest rate delta (USD)", "USD risk-free yield at 1, 2, 5, 10, 30y; +1bp with triangular weights", "1.11%, 0.93%, 0.74%, 0.74%, 0.74%", "Tenor matrix 31-91% (Table 4)"],
             ["Interest rate vega (USD)", "All USD rate volatilities, +1% relative", "100%", "Single factor"],
             ["FX delta (USDJPY)", "USDJPY spot, +1% relative", "11%", "Single factor; cross-bucket 0.6"],
             ["FX vega", "USDJPY volatility, +1% relative", "100%", "Single factor"],
             ["Counterparty credit spread", "Each counterparty at 0.5, 1, 3, 5, 10y; +1bp", "5% (financials, investment grade)", "Tenor 0.9 x name 0.5 (unrelated)"],
             ["Equity delta", "All names in an equity bucket, +1% relative spot", "30-55% by bucket", "Cross-bucket 0.15"],
             ["Equity vega", "All volatilities in a bucket, +1% relative", "78% large cap, 100% small cap", "Cross-bucket 0.15"],
             ["Reference credit, commodity", "None: no such drivers of exposure", "-", "-"]], widths=[1.6, 3.0, 1.7, 1.6], font=7.4))
    add(Spacer(1, 4))
    eqb = Rc["equity_buckets"]
    add(P("Equity names are assigned to Basel buckets by size (market capitalisation of at least USD 2 billion), region (advanced versus emerging economy) and sector, using yfinance data: " + ", ".join("bucket %s: %d names" % (b, n_) for b, n_ in sorted(eqb.items(), key=lambda kv: int(kv[0]))) + "."))
    add(doc.figure(fig_sa_cva(Rc), "Left: CVA sensitivity to a 1bp rise in USD yields at each SA-CVA tenor. Middle: sensitivity of CVA to the counterparty credit spreads (three counterparties by five tenors). Right: SA-CVA capital by risk class."))
    cap = Rc["capital_by_class"]
    rows = [["Risk class", "Capital K (USD)"]]
    for k_, v in cap.items():
        rows.append([k_.replace("_", " "), format(v, ",.0f")])
    rows.append(["Total SA-CVA capital requirement (m_CVA = 1)", format(Rc["K_sa_cva"], ",.0f")])
    rows.append(["Risk-weighted assets (12.5 x capital)", format(Rc["RWA"], ",.0f")])
    rows.append(["Total if the pre-2023 multiplier m_CVA = 1.25 applied", format(Rc["K_sa_cva_m125"], ",.0f")])
    add(tbl(rows, widths=[4.0, 2.0]))
    top = max(cap, key=cap.get)
    add(P("The requirement is dominated by %s (%.0f%% of the total), as is typical: a 5%% risk weight on credit spreads is large relative to a 100 bp spread level, so the capital charge is a multiple of the CVA itself. Interest rate, FX and equity classes are comparatively small. The multiplier m_CVA is 1 in the framework in force from 2023 (it was 1.25 in the original 2017 text); both are shown." % (top.replace("_", " "), cap[top] / Rc["K_sa_cva"] * 100)))
    add(P("8.5 Assumptions and limitations of the CVA work", H2))
    add(B(["<b>Counterparty ratings are assumed</b> (BBB financials). CVA and the credit-spread capital scale with this assumption; Section 8.3 shows the range.",
           "<b>Spreads are bond-index proxies</b>, not CDS: the maturity shape is common to all ratings, and the indices are US corporate spreads regardless of counterparty region or sector.",
           "<b>Unilateral, independent, uncollateralized.</b> No DVA, no wrong-way risk (exposure and default dependence) and no margin, which MAR50.32 allows to be recognised only where terms are known.",
           "<b>Interest rate risk is USD only:</b> the JPY rate is not simulated, so JPY rate sensitivity is captured through the USD curve; inflation risk factors are omitted (no inflation exposure).",
           "<b>Sensitivities are one-sided bumps</b> from 1,000 Latin Hypercube scenarios with common random numbers, not adjoint sensitivities; vega shifts apply to the volatilities driving the simulated paths (the trades contain no options, so there are no option-pricing volatilities).",
           "<b>Parameters</b> are transcribed from the BIS text (July 2020 revisions); the vega risk weights follow the 100% and 78% values in that text. Regulatory use requires supervisory approval and validation of the sensitivity calculation.",
           "The Basel Basic Approach (BA-CVA) is not computed; it needs only counterparty exposure and maturity and is the natural fallback if SA-CVA approval is not held."]))
    add(PageBreak())

    # ---------- 9 Greeks
    g_ = RG.load()
    from run_simulation import load_trades as _lt
    from risk_engine.models.calibration import _isin_to_ticker
    _tr = _lt()
    tickers_ = _isin_to_ticker()
    tm_ = {}
    for tid_, t_ in _tr.items():
        if hasattr(t_, "positions"):
            sign_ = -1.0 if t_.direction == "pay_equity" else 1.0
            tm_[tid_] = {}
            for p_ in t_.positions:
                s_ = calib["equity_spots"][p_.isin] / (calib["fx_spot"] if p_.currency == "JPY" else 1.0)
                tm_[tid_][p_.isin] = sign_ * p_.shares * s_ * 0.01
    RG.section(add, doc, g_, tickers_, tm_)

    add(P("10. Every modelling choice, and what we rejected", H1))
    add(tbl([["Topic", "Choice", "Alternatives considered", "Reason"],
             ["Measure", "Risk-neutral", "Real-world drifts", "No unobservable risk premia; verified martingale; horizon short"],
             ["Confidence", "PFE99 and median PFE (with EE)", "Other percentiles", "99% is the specified target; 99.9% needs far more paths for little added insight"],
             ["USD rates", "Hull-White 1F", "CIR, BK, LMM, constant", "Exact curve fit, analytic bonds, negative-rate capable, few parameters"],
             ["Equities/FX", "Correlated GBM", "Heston, SABR, jumps", "No option surfaces; matches lognormal vol convention"],
             ["Volatility", "3y realised", "Implied vols", "No single-name options data; documented proxy"],
             ["Correlation", "One static matrix, Cholesky", "Time-varying (DCC), stressed, factor", "Data supports one matrix; factor model offered as alternative"],
             ["Equity factor model", "Optional PCA (k=5)", "Full rank only", "Robustness, dimension reduction; approximation disclosed"],
             ["Dates", "Pillar dates + trade event dates", "Monthly grid", "Industry convention, denser where risk moves, exact cash-flow dates"],
             ["Sampling", "Latin Hypercube", "Pseudo-random, antithetic, moment-matched, Sobol", "Best measured error on both test and real engine"],
             ["Scenario count", "5,000 (reporting); 1,000 (iteration); 10,000 (sign-off)", "30,000 pool", "Diminishing returns beyond 10-15k; model risk dominates"],
             ["Mean reversion a", "Swaption-based (USD 0.0167)", "Futures proxy (0.0458), textbook 0.03", "Industry-standard instrument"],
             ["JPY rates", "Real JPY Hull-White factor (built), not yet wired", "Constant differential only", "Negative-rate capable; real TONA sigma; correlation calibrated ~0"],
             ["Collateral", "Uncollateralized default; MPOR-shift option", "Assume full VM", "No CSA data; hypothetical shown separately"],
             ["Pricing", "Reuse validated pricer library", "Vectorised reimplementation", "Correctness first; speed via multiprocessing"]],
            widths=[1.2, 2.0, 2.0, 2.6], font=7.2))
    add(PageBreak())

    # ---------- 9 validation
    add(P("11. Validation: how we know the engine is right", H1))
    add(P("Each check isolates one layer (paths, pricing, calibration, aggregation) so a failure points at where to look."))
    add(P("11.1 Self-consistency at t = 0", H2))
    add(P("Simulated EE(0) must equal a direct current-exposure calculation from the identical calibrated snapshot: matches to 0.0000% (after fixing two comparison-object mismatches, Section 10)."))
    add(P("11.2 Martingale / no-arbitrage test", H2))
    add(P("Under the risk-neutral measure discounted asset prices must have no drift. With 8,000 paths: the bank-account check E[exp(-integral r)] = P(0,T) holds to a maximum relative difference of 0.73 bp "
          "across nodes (a small, understood trapezoid-integration effect of the coarse monthly grid), and the discounted-equity 'gains process' for six names has all |z| below 1.4. This validates the drift terms "
          "in the engine itself, independent of any trade pricing."))
    add(P("11.3 Parametric (delta-normal) VaR benchmark", H2))
    add(P("An independent standard method: portfolio dollar-deltas by bump-and-reprice with the same volatilities and correlations as the simulation, combined into a delta-normal VaR at the first simulated node (one day, the overnight pillar). The 99% delta-normal VaR is $11.4M against $11.7M from the Monte Carlo P&L distribution (ratio 0.98; accepted range 0.3-1.3). At this short horizon the book is close to linear in the risk factors, so close agreement is expected; a large discrepancy would have indicated a sign or scaling error in the deltas or the covariance."))
    add(P("11.4 Sensitivity (stress) test", H2))
    add(P("Directional test with common random numbers (800 scenarios, same seed in base and bumped runs). Base MPE (PFE99) is $174.0M. Raising equity volatility by 50% increases it to $189.8M (+9.1%); a +100bp parallel shift of the USD curve to $230.5M (+32.5%), consistent with the USD rate being the largest single delta; and raising Hull-White sigma by 50% to $183.4M (+5.4%). All three moved exposure in the economically required direction. The magnitudes also show the scale of model risk: an equity volatility error of 50% matters about ten times more than the sampling error at the recommended path count."))
    add(P("11.5 Statistical and unit tests", H2))
    add(P("82 automated tests pass. They cover: Hull-White reproducing the curve at t=0 to 1e-9; the GBM martingale property; the 1/sqrt(N) error law; antithetic variance reduction; Cholesky recovering a target "
          "correlation; MPOR look-ahead spacing and formula; pillar dates and forced event dates; negative-rate behaviour of Hull-White; the PCA factor model (exact at full rank, monotone error, variance "
          "preservation); the BOJ TONA and MOF JGB loaders and the empirical JPY findings; the tail-convergence result; and median PFE, CVA and the SA-CVA aggregation, the credit-spread proxy curves, and the Greeks machinery (bump helpers, t=0 Greeks against analytic values, exposure measures)."))
    add(P("11.6 Greeks (sensitivities)", H2))
    add(P("Three delta estimators were compared on a call option: pathwise, bump-and-reprice with <b>common random numbers</b> (same draws in base and bumped runs) and bump-and-reprice with independent draws."))
    add(tbl([["Method", "Bias", "Std of estimate", "Time/trial"],
             ["Pathwise", "+0.000085", "0.003771", "0.470 ms"], ["Bump, common random numbers", "+0.000033", "0.003742", "0.327 ms"],
             ["Bump, independent random numbers", "-0.003502", "0.096885", "0.850 ms"]], widths=[2.6, 1.3, 1.6, 1.3]))
    add(P("Common random numbers make bump-and-reprice statistically indistinguishable from the pathwise estimator (26x lower noise than independent draws), and it works on any pricer as a black box, "
          "so it is the method that generalises to the real book. On the real book, the exact t=0 delta of EQTRS_0003's NPV to its largest position is -$212,269 per $1 move, exactly equal to the share count "
          "(a linear-payoff consistency check)."))
    add(PageBreak())

    # ---------- 10 bugs
    add(P("12. Defects identified and resolved", H1))
    add(P("Each defect was identified by checking against an independent source, a hand calculation or a full end-to-end run."))
    add(tbl([["#", "Bug", "How it was caught / fix"],
             ["1", "BRK.B vs BRK-B ticker silently failed in two functions", "Missing prices; fixed in both current and historical fetch"],
             ["2", "SOFR curve: recently-expired serial futures wrapped a decade forward, creating a multi-year gap", "Cross-check against Treasury.gov par curve (73bp vs smooth 56bp at 10Y); fixed"],
             ["3", "The fix for #2 over-corrected and dropped genuine far-dated live contracts (e.g. SR3H0, March 2030)", "Found while calibrating Hull-White; fixed with a 400-day plausibility threshold; curve coverage 3.6y -> 6.3y"],
             ["4", "US and Tokyo equity histories joined by timestamp gave a ~70% blank table", "Join by calendar date instead"],
             ["5", "Stale cached exposure file gave false 7-15% 'discrepancies'", "Root cause: real overnight moves (one name has 76% vol); check now uses the in-memory snapshot"],
             ["6", "Residual 0.02-0.03% self-check gap", "Different curve object; both sides now use the identical exact analytic curve: 0.0000%"],
             ["7", "Tail-convergence study initially run at 99.9% rather than the specified 99%", "Re-run at 99%; tests and documentation updated"],
             ["8", "JPY mean-reversion fit gave a negative a", "Diagnosed as a real structural property (three sources); lower bound a = 0.001 used"]],
            widths=[0.3, 3.3, 4.2], font=7.4))
    add(P("13. Assumptions and limitations", H1))
    add(B(["<b>Uncollateralized and no CSA data.</b> If margin exists, results change by up to an order of magnitude (Section 7.4).",
           "<b>Volatility is a 3-year realised proxy</b>, not implied. Regime shifts and skew are not captured.",
           "<b>One static correlation matrix</b> from 613 days; correlations tend to rise in stress and are not stressed here.",
           "<b>GBM underestimates fat tails</b>, most relevant for PFE99 on high-vol names.",
           "<b>Single-factor USD rates</b>: no curve twists independent of the level.",
           "<b>Risk-neutral drift</b>: not a real-world forecast; regulatory PFE may need physical drift.",
           "<b>JPY:</b> mean reversion is at its lower bound (the data give a negative value) and the JPY rate does not yet drive JPY equity/FX drift (two trades).",
           "<b>Model risk vs sampling risk:</b> above a few thousand scenarios the uncertainty is in the models, not the random numbers.",
           "<b>Margin modelling is partial:</b> the collateral illustration is variation-margin only, uses a 10-business-day window on a US federal holiday calendar, and has no initial margin (SIMM) or minimum transfer amount.",
           "<b>No wrong-way risk or credit dynamics of the counterparty itself</b>; this is exposure, not a loss estimate (that needs PD and LGD).",
           "<b>Bloomberg data is a single 2026-08-31 snapshot</b> (three days after the 2026-08-28 market data); acceptable for shape and level, disclosed."]))
    add(P("14. Conclusions and recommendations", H1))
    add(B([f"The engine is validated (t=0 self-check, martingale, VaR benchmark, stress test, 82 tests) and reproducible with a single command per stage.",
           f"The uncollateralized book has peak portfolio PFE99 of {m(mpe99)} at {D['rep_dates'][j_mpe]}, versus EE of {m(tot['EE'].max())} and median PFE of {m(tot['MED'].max())}; the spread between these three is the point of reporting all of them.",
           "Risk is short-dated (about four months) and concentrated (one trade, one counterparty).",
           f"CVA on the uncollateralized book is about ${Rc0['cva_total']/1e3:,.0f}k at a BBB proxy (${Rc0['cva_vs_rating']['AA']/1e3:,.0f}k at AA to ${Rc0['cva_vs_rating']['BB']/1e3:,.0f}k at BB); the SA-CVA requirement is ${Rc0['K_sa_cva']/1e6:.2f}M (RWA ${Rc0['RWA']/1e6:.1f}M), dominated by counterparty credit spread risk.",
           f"Greeks are complete for the book and for the exposure measures (Section 9): PFE99 at its peak date falls by about ${abs(g_['equity_all']['delta']['__portfolio__']['PFE'][RG.peak_node(g_)])/1e3:,.0f}k per +1% on all equities and rises by about ${g_['rate_parallel']['delta']['__portfolio__']['PFE'][RG.peak_node(g_)]/1e3:,.0f}k per +1bp on USD rates.",
           "We recommend confirming with Capitolis whether any trade is margined, and on what terms; that fact matters more than any further modelling refinement.",
           "Use Latin Hypercube sampling with N = 5,000 for reporting, N = 1,000 for iteration and N = 10,000 for limit sign-off (Section 5.5).",
           "Next engineering steps: wire the JPY Hull-White factor into JPY equity/FX drift; a two-factor or regime-aware rate model if a long JPY curve history becomes available; a vectorised pricer reimplementation if scenario counts must exceed ~10,000; a model-risk study varying a, vols and correlation."]))
    add(PageBreak())

    add(P("Appendix A. Glossary", H1))
    add(tbl([["Term", "Meaning"],
             ["Counterparty credit risk (CCR)", "Loss risk if the other side of a derivative defaults while the contract is in our favour"],
             ["MTM / NPV", "Mark-to-market / net present value: what the trade is worth today"],
             ["Netting set", "Trades under one legal netting agreement; combined before taking max(V,0)"],
             ["EE, PFE, MPE", "Expected exposure (mean), potential future exposure (percentile), maximum PFE over time"],
             ["Median PFE", "50th percentile of exposure at a date"],
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
             ["MPOR", "Margin period of risk: delay between last margin call and close-out (typically 10 business days)"],
             ["CSA / VM / threshold", "Credit support annex / variation margin / uncollateralized amount before margin is called"],
             ["Delta, gamma", "First and second sensitivity of a value or exposure measure to a market factor (here per +1% spot, per +1bp rate)"],
             ["DV01", "Change in value for a +1bp move of the interest rate curve, parallel or by tenor bucket"],
             ["Vega", "Sensitivity to volatility (here per +1% relative shift)"],
             ["CVA", "Credit valuation adjustment: the market price of counterparty default risk on a derivatives portfolio"],
             ["SA-CVA", "Basel standardised approach for CVA capital: risk-weighted CVA sensitivities aggregated by bucket and risk class (MAR50)"],
             ["Wrong-way risk", "Positive dependence between exposure and the counterparty default probability (not modelled here)"],
             ["SIMM", "ISDA Standard Initial Margin Model: sensitivity-based initial margin for uncleared derivatives, calibrated to a 99% 10-day loss (not implemented here)"],
             ["Pillar dates", "Standard curve tenor points: O/N, T/N, 1W, 2W, 1M ... 10Y"],
             ["Risk-neutral measure", "Pricing measure in which discounted assets are martingales; drift = r - q"]],
            widths=[2.2, 5.5]))
    add(P("Appendix C. Data sources and lineage", H1))
    add(P("Every external input, where it came from, how it was obtained and what it is used for. Raw pulls are stored under data/raw/ (excluded from version control); licensed data is never redistributed."))
    add(tbl([["Input", "Source", "How obtained", "Used for", "Status"],
             ["Trades (16) and underlyings", "Capitolis: trade_data/*.csv", "Supplied files", "Trade definitions, baskets, bonds", "Given"],
             ["Pricing library", "Capitolis: capitolis_pricers", "Supplied package (standard library only)", "All trade valuation (npv), curves, day counts", "Given; independently reviewed"],
             ["USD SOFR futures (SR3, SR1)", "CME Globex via Databento (dataset GLBX.MDP3)", "Paid API; key only in an environment variable", "USD discount curve (bootstrapped by us), Hull-White fit, futures-vol mean-reversion cross-check", "Live, validated against Treasury.gov"],
             ["Treasury par yield curve", "U.S. Treasury (treasury.gov)", "Public download", "Independent check of the SOFR curve", "Validation only"],
             ["Equity spots, dividends, 3y price history (37 names)", "yfinance (Yahoo Finance)", "Public API, keyed by ISIN", "GBM start values and drift, realised volatility, correlation", "Live"],
             ["USDJPY spot and 3y history", "yfinance", "Public API", "FX start value, volatility, correlation", "Live"],
             ["SOFR level history", "FRED (series SOFR)", "Public CSV", "Rate volatility; USD-JPY rate correlation", "From April 2018"],
             ["TONA (JPY overnight rate), 1998 to date", "Bank of Japan Time-Series Data Search API (DB FM01, series STRDCLUCON)", "Public API", "JPY rate volatility; USD-JPY correlation; negative-rate evidence", "Public"],
             ["JGB par yields 1Y-40Y, 1974 to date", "Japan Ministry of Finance", "Public CSV (browser-like request headers)", "Test of JPY mean reversion", "Public"],
             ["JPY OIS par-rate history (MUTKCALM overnight plus 35 OIS tenors, 5 Oct 2011 to 18 Sep 2026)", "Bloomberg (tickers JYSO*, MUTKCALM Index)", "Provided by the project team, saved as data/raw/sources/JPY.xlsx (parsed copy jpy_ois_history.csv)", "JPY zero curve (bootstrapped), JPY volatility, JPY-USD differential, mean-reversion test", "Licensed: derived numbers only in the report"],
             ["USD and JPY swaption cubes; USDJPY forward points", "Bloomberg one-time export, snapshot 2026-08-31", "Provided by the project team", "USD mean reversion; JPY cross-check; FX forwards", "Licensed: derived numbers only in the report"],
             ["Credit spreads by rating and maturity shape", "FRED: ICE BofA US option-adjusted spread indices", "Public CSV", "Counterparty credit spread proxy for CVA", "Public"],
             ["SA-CVA parameters and formulas", "BIS, Basel Framework MAR50 (July 2020 revisions)", "Public PDF", "Risk weights, correlations, aggregation", "Public"],
             ["Equity sector, country, market cap", "yfinance", "Public API", "SA-CVA equity buckets", "Live"]],
            widths=[1.7, 2.0, 1.6, 2.2, 1.2], font=7.0))
    add(P("Assumptions that are not sourced from data: counterparty ratings (BBB), LGD (60%), MPOR (10 business days), the uncollateralized status of the book, the correlation structure being static, and the JPY mean reversion being set at its lower bound (a = 0.001) because every calibration route gives a negative value."))
    add(P("Appendix D. Methodology register", H1))
    add(tbl([["Component", "Method", "Key parameters", "Where (code)"],
             ["USD curve", "Bootstrap of SOFR futures: implied forward rate to chained discount factors, ACT/360", "33 live contracts, about 6.3y coverage, flat extrapolation beyond", "market/sofr.py"],
             ["USD rates", "One-factor Hull-White, shifted Ornstein-Uhlenbeck, exact transition, analytic bond price", "sigma 0.63% (realised SOFR); a 0.0167 (swaption cube)", "models/rates.py"],
             ["Mean reversion", "Regression of ln(vol) on tenor (vol decay); swaption cube preferred, futures and JGB as checks", "USD 0.0167; futures 0.0458; JPY: all routes negative, lower bound 0.001 used", "models/hw_calibration.py"],
             ["JPY factor", "Second Hull-White factor; curve bootstrapped from the JPY OIS par history; overnight volatility from the same file", "sigma 0.267%; a = 0.001; USD-JPY rate correlation -0.04 (not significant)", "models/calibration.py, market/jpy_ois.py"],
             ["Equities and FX", "Correlated geometric Brownian motion, exact log step, drift r-q", "3y realised vols; JPY names via r_USD minus differential (about 2.6%)", "models/equity_fx.py"],
             ["Correlation", "Static 39x39 matrix (613 aligned days), Cholesky; optional PCA factor model", "5 factors explain about 46% of variance", "models/equity_factor_model.py, simulation/engine.py"],
             ["Random numbers", "Latin Hypercube sampling", "N = 5,000 recommended; 3,000 used for the figures", "simulation/random_numbers.py"],
             ["Dates", "Market pillar dates plus every trade event date", "42 nodes for this book", "simulation/engine.py"],
             ["Repricing", "Full repricing of every trade in every scenario and node, 8 worker processes", "About 90 ms per scenario", "simulation/parallel.py"],
             ["Exposure measures", "Netting by counterparty, max(V,0); EE, median PFE, PFE99, MPE", "PFE at the 99th percentile", "exposure/aggregate.py"],
             ["Collateral (hypothetical)", "MPOR look-ahead on the same paths, full variation margin", "10 business days, US federal holidays", "exposure/collateral.py"],
             ["CVA", "Regulatory CVA, MAR50.32; pathwise discounting; credit-triangle PD from spreads", "LGD 60%; BBB proxy; unilateral; independent", "exposure/cva.py, models/credit.py"],
             ["SA-CVA", "CVA bump sensitivities with common random numbers, MAR50 aggregation", "1,000 scenarios; 21 simulations; m_CVA = 1", "exposure/sa_cva.py, scripts/run_sa_cva.py"],
             ["Greeks", "Bump-and-reprice with common random numbers; equity and FX bumps reuse paths (exact GBM rescaling, subset repricing); rate and vol bumps re-simulate", "+1% spot, +1bp rates (parallel and 8 buckets), +1% vol; N = 2,000", "greeks/book.py, greeks/exposure.py, scripts/run_greeks.py"],
             ["Precision", "Bootstrap resampling of a large pool; 1/sqrt(N) extrapolation", "Relative SE of PFE99 about 1.0% at N = 5,000 at the worst date", "scripts/convergence_study_tail.py"],
             ["Validation", "t=0 self-check, martingale test, delta-normal VaR, stress test, unit tests", "82 automated tests", "scripts/, tests/"]],
            widths=[1.2, 2.8, 2.4, 1.9], font=7.0))
    add(P("Appendix E. Code map", H1))
    add(tbl([["Package", "Contents"],
             ["market/", "sofr, equities, fx, vols, correlations (data pulls and inputs); boj, mof_jgb, bloomberg (JPY data); credit_spreads, equity_buckets (CVA inputs)"],
             ["models/", "rates (Hull-White), equity_fx (GBM), calibration and hw_calibration (parameters), equity_factor_model (PCA), credit (PD from spreads)"],
             ["simulation/", "engine (grid, paths, MPOR nodes), random_numbers (five sampling schemes), parallel (multiprocessing repricing)"],
             ["greeks/", "book (t=0 Greeks by trade and netting set), exposure (sensitivities of EE, median PFE, PFE99), bumps (curve and parameter bump helpers)"],
             ["exposure/", "aggregate (netting, EE, median PFE, PFE, MPE), collateral (MPOR-shifted), cva (regulatory CVA), sa_cva (Basel aggregation)"],
             ["scripts/", "run_simulation, run_mpor_comparison, run_sa_cva, generate_report_data, build_report (LaTeX), build_exec_deck, and the convergence, variance-reduction, VaR, martingale and stress benchmarks"],
             ["tests/", "82 tests: engine, time grid, MPOR, negative rates, factor model, BOJ and MOF data, tail convergence, median PFE, CVA and SA-CVA"]],
            widths=[1.2, 6.6]))
    add(P("Appendix B. Reproducing the results", H1))
    add(code("python scripts/generate_report_data.py --scenarios 3000   # ~15 min: simulation, arrays for figures\n"
             "python scripts/build_report.py                            # this PDF\n"
             "python scripts/run_simulation.py --scenarios 3000         # printed EE/PFE99/MPE profiles\n"
             "python scripts/run_mpor_comparison.py                     # hypothetical collateral demo\n"
             "python scripts/run_sa_cva.py --scenarios 1000             # CVA and SA-CVA capital (21 runs)\n"
             "python scripts/run_greeks.py --scenarios 2000             # book and exposure Greeks (about 75 min)\n"
             "python -m pytest tests                                    # 82 tests"))
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
