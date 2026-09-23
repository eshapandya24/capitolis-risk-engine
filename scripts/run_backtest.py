"""
Kupiec backtest of the simulated 10-business-day exposure quantiles
(validation/backtest.py) on real history.

  * equity/FX leg: the ESF book's equity TRS positions per counterparty, static
    shares, model calibrated on the trailing 3 years at each as-of date;
  * rates leg: 10-day changes of the 5y/10y/20y Treasury yields against the
    one-factor Hull-White distribution, sigma from (a) overnight SOFR realised
    vol (the earlier calibration) and (b) the long-end fit now in use.

Long price histories come from yfinance (public), cached in
data/raw/backtest_prices.csv; yields from FRED (data/raw/ust_cmt_history.csv).

    python scripts/run_backtest.py
"""
import json
import os
import sys
from datetime import date

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "processed", "backtest_results.json")
START, END = "2014-06-01", "2026-08-31"
PHASES = range(10)
CONFS = (0.95, 0.99)


def load_prices():
    path = os.path.join(RAW, "backtest_prices.csv")
    if os.path.exists(path):
        return pd.read_csv(path, index_col=0, parse_dates=True)
    from risk_engine.models.calibration import _isin_to_ticker
    from risk_engine.market.equities import fetch_history as fetch_eq
    from risk_engine.market.fx import fetch_history as fetch_fx
    hist = fetch_eq(_isin_to_ticker(), START, END)
    ok = {i: s.tz_localize(None).groupby(s.tz_localize(None).index.date).last() for i, s in hist.items() if s is not None and len(s)}
    df = pd.DataFrame(ok)
    fx = fetch_fx(START, END)
    fx = fx.tz_localize(None).groupby(fx.tz_localize(None).index.date).last()
    df["FX_USDJPY"] = fx
    df.index = pd.to_datetime(df.index)
    df.index.name = "date"
    df.to_csv(path)
    return df


def equity_positions(trades):
    """{cpty: {isin: signed shares}} from the equity TRS trades (receive equity +, pay equity -)."""
    out = {}
    for tid, t in trades.items():
        if not hasattr(t, "positions"):
            continue
        sign = 1.0 if t.direction == "receive_equity" else -1.0
        d = out.setdefault(t.counterparty, {})
        for p in t.positions:
            d[p.isin] = d.get(p.isin, 0.0) + sign * p.shares
    return out


def main():
    from run_simulation import load_trades
    from risk_engine.models.calibration import _isin_currency
    from risk_engine.validation import backtest as B
    from risk_engine.market import treasury
    from risk_engine.market.sofr import fetch_history as fetch_sofr

    trades = load_trades()
    cur = _isin_currency()
    px = load_prices()
    lfx = np.log(px["FX_USDJPY"].dropna())
    # US and Tokyo names trade on different holidays: carry the last close over non-trading days
    lp = np.log(px.drop(columns="FX_USDJPY")).ffill(limit=5)
    lfx = lfx.reindex(lp.index).ffill(limit=5).dropna()
    lp = lp.loc[lfx.index]
    pos = equity_positions(trades)

    res = {"config": {"window_days": 756, "horizon_days": 10, "non_overlapping": True, "phases": len(PHASES),
                      "history": [str(px.index.min().date()), str(px.index.max().date())]},
           "equity": {}, "rates": {}}

    print("equity/FX leg", flush=True)
    for cpty, p in sorted(pos.items()):
        is_jpy = {i: cur.get(i) == "JPY" for i in p}
        series = {ph: B.equity_book_backtest(lp, lfx, p, is_jpy, window=756, horizon=10, phase=ph, n_draws=10000) for ph in PHASES}
        row = {"n_names": len(p), "confidences": {}}
        for c in CONFS:
            s0 = B.summarize_hits(series[0][c]["hits"], c)
            allp = [B.summarize_hits(series[ph][c]["hits"], c) for ph in PHASES]
            row["confidences"][str(c)] = {
                **{k: s0[k] for k in ("x", "n", "rate", "expected", "lr", "p_value", "independence_p", "pass_5pct")},
                "phases_rejecting": int(sum(not r["pass_5pct"] for r in allp)),
                "phases_mean_rate": float(np.mean([r["rate"] for r in allp])),
                "phases_total_x": int(sum(r["x"] for r in allp)), "phases_total_n": int(sum(r["n"] for r in allp))}
            print(f"  {cpty} {c:.0%}: x={s0['x']}/{s0['n']} (expected {s0['expected']:.1f}) p={s0['p_value']:.3f}; "
                  f"phases rejecting {row['confidences'][str(c)]['phases_rejecting']}/10, mean rate {row['confidences'][str(c)]['phases_mean_rate']:.3f}", flush=True)
        row["series_99"] = {"dates": series[0][0.99]["dates"], "pred": series[0][0.99]["pred"],
                            "real": series[0][0.99]["real"], "hits": series[0][0.99]["hits"].tolist()}
        res["equity"][cpty] = row

    print("rates leg", flush=True)
    cmt = treasury.load_cmt_history()
    sofr = fetch_sofr("2018-04-01", "2030-01-01").dropna()
    a = 0.01665618495809116                      # swaption-calibrated mean reversion (held fixed)
    dsofr = sofr.diff().dropna()
    y_index = cmt.index

    def sigma_sofr(t0):
        d = y_index[t0]
        w = dsofr[(dsofr.index > d - pd.DateOffset(years=3)) & (dsofr.index <= d)]
        return float(w.std() * np.sqrt(252)) if len(w) > 500 else np.nan

    def sigma_fit(t0):
        return treasury.fit_hw_sigma(a, treasury.realized_vols(y_index[t0], 3, cmt))

    first_ok = next(i for i in range(756, len(y_index)) if np.isfinite(sigma_sofr(i)))
    for tenor, col in ((5, "DGS5"), (10, "DGS10"), (20, "DGS20")):
        res["rates"][str(tenor)] = {}
        for name, fn in (("sofr_overnight", sigma_sofr), ("long_end_fit", sigma_fit)):
            sig_cache = {}

            def sig(t0, fn=fn, cache=sig_cache):
                if t0 not in cache:
                    cache[t0] = fn(t0)
                return cache[t0]

            per_phase = []
            for ph in PHASES:
                r = B.rates_backtest(cmt[col], tenor, sig, a, window=first_ok, horizon=10, phase=ph)
                per_phase.append(r)
            row = {}
            for c in CONFS:
                for tail in ("up", "down"):
                    s0 = B.summarize_hits(per_phase[0][c][tail], c)
                    allp = [B.summarize_hits(pp[c][tail], c) for pp in per_phase]
                    row[f"{c}_{tail}"] = {**{k: s0[k] for k in ("x", "n", "rate", "expected", "lr", "p_value", "pass_5pct")},
                                          "phases_rejecting": int(sum(not r_["pass_5pct"] for r_ in allp)),
                                          "phases_mean_rate": float(np.mean([r_["rate"] for r_ in allp]))}
            res["rates"][str(tenor)][name] = row
            r99 = row["0.99_up"]
            r95 = row["0.95_up"]
            print(f"  {tenor}y {name:15s}: 99% up x={r99['x']}/{r99['n']} p={r99['p_value']:.3f} (phases rej {r99['phases_rejecting']}/10, mean rate {r99['phases_mean_rate']:.3f}); "
                  f"95% up p={r95['p_value']:.3f} (rate {r95['phases_mean_rate']:.3f})", flush=True)
    res["rates_config"] = {"first_asof": str(y_index[first_ok].date()), "a": a, "sigma_now_sofr": sigma_sofr(len(y_index) - 11),
                           "sigma_now_fit": sigma_fit(len(y_index) - 11)}
    json.dump(res, open(OUT, "w"), indent=1, default=float)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
