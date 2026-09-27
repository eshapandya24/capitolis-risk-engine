"""
Stress-scenario definitions for the exposure engine.

A scenario is an INSTANTANEOUS shock to today's market state, followed by the
usual full Monte Carlo of exposure from the shocked state:

    equity_returns  {isin: simple return} applied to every equity spot
    fx_return       simple return of USDJPY (JPY per USD)
    dy              (tenors_years, shifts) zero-rate shift applied to the USD curve

Two families:
  * hypothetical, round-number shocks (transparent, easy to compare across
    books) - see hypothetical();
  * historical replays: the actual per-name equity returns, USDJPY move and
    Treasury yield changes over a real 10-business-day window, chosen by rule
    from history (worst equity window, worst rates-up window, strongest-yen
    window) - see historical_windows().
Equity and FX shocks rescale the simulated GBM paths exactly (no
re-simulation); rate shocks change the Hull-White curve and re-simulate with
the same random numbers.
"""
import math

import numpy as np
import pandas as pd


def shift_curve(curve, tenors, shifts):
    """Copy of `curve` with zero rates shifted by np.interp(t, tenors, shifts)
    (flat beyond the end tenors): ln DF'(t) = ln DF(t) - shift(t) * t."""
    from capitolis_pricers.curves import Curve
    tenors, shifts = np.asarray(tenors, dtype=float), np.asarray(shifts, dtype=float)
    lndf = [y - float(np.interp(t, tenors, shifts)) * t for t, y in zip(curve._t, curve._lndf)]
    return Curve(curve.ref_date, list(curve._t), [math.exp(v) for v in lndf], basis=curve.basis)


def hypothetical(isins):
    """Round-number scenarios: each is a dict(name, kind, description, eq, fx, dy)."""
    flat = lambda r: {i: r for i in isins}
    parallel = lambda bp: ([1.0, 30.0], [bp * 1e-4, bp * 1e-4])
    return [
        dict(name="EQ_DOWN_30", kind="hypothetical", description="All equities -30%", eq=flat(-0.30), fx=0.0, dy=None),
        dict(name="EQ_UP_30", kind="hypothetical", description="All equities +30%", eq=flat(0.30), fx=0.0, dy=None),
        dict(name="JPY_STRONG_15", kind="hypothetical", description="Yen strengthens 15% (USDJPY -15%)", eq={}, fx=-0.15, dy=None),
        dict(name="JPY_WEAK_15", kind="hypothetical", description="Yen weakens 15% (USDJPY +15%)", eq={}, fx=0.15, dy=None),
        dict(name="RATES_UP_200", kind="hypothetical", description="USD zero curve +200bp parallel", eq={}, fx=0.0, dy=parallel(200)),
        dict(name="RATES_DOWN_200", kind="hypothetical", description="USD zero curve -200bp parallel", eq={}, fx=0.0, dy=parallel(-200)),
        dict(name="FLIGHT_TO_QUALITY", kind="hypothetical", description="Equities -25%, USD curve -100bp (bonds rally as equities fall)",
             eq=flat(-0.25), fx=-0.05, dy=parallel(-100)),
        dict(name="STAGFLATION", kind="hypothetical", description="Equities -25%, USD curve +150bp (bonds and equities fall together)",
             eq=flat(-0.25), fx=0.0, dy=parallel(150)),
    ]


def _window_returns(prices, fx, cmt, i0, i1, isins):
    """Simple returns / yield changes between row i0 and i1 of the aligned frames."""
    d0, d1 = prices.index[i0], prices.index[i1]
    eq = {}
    for i in isins:
        if i in prices.columns and np.isfinite(prices[i].iloc[i0]) and np.isfinite(prices[i].iloc[i1]):
            eq[i] = float(prices[i].iloc[i1] / prices[i].iloc[i0] - 1.0)
    med = float(np.median(list(eq.values()))) if eq else 0.0
    eq = {i: eq.get(i, med) for i in isins}            # names without data take the median return
    fxr = float(fx.iloc[i1] / fx.iloc[i0] - 1.0)
    c = cmt[(cmt.index >= d0) & (cmt.index <= d1)]
    dy = None
    if len(c) >= 2:
        ten = {0.25: "DGS3MO", 0.5: "DGS6MO", 1: "DGS1", 2: "DGS2", 5: "DGS5", 10: "DGS10", 20: "DGS20", 30: "DGS30"}
        tt = [t for t, col in ten.items() if col in c.columns]
        dy = (tt, [float(c[ten[t]].iloc[-1] - c[ten[t]].iloc[0]) for t in tt])
    return eq, fxr, dy, str(d0.date()), str(d1.date())


def historical_window_in_range(prices, fx, cmt, isins, start, end, name, description, horizon=10, rule="worst_equity"):
    """One real `horizon`-business-day window, chosen by `rule` WITHIN
    [start, end] only (a named historical episode, e.g. the 2008 crisis),
    instead of the single global extremum historical_windows() picks over
    the whole available history. `rule` is "worst_equity" (lowest median
    return across `isins`) or "yen_surge" (largest fall in USDJPY). Returns
    one scenario dict, or None if the range has no usable data."""
    idx = prices.index
    win = idx[(idx >= pd.Timestamp(start)) & (idx <= pd.Timestamp(end))]
    if len(win) <= horizon:
        return None
    have = [i for i in isins if i in prices.columns]
    sub = prices.loc[win, have]
    if rule == "worst_equity":
        logp = np.log(sub)
        ret = (logp.shift(-horizon) - logp).iloc[:-horizon]
        med = ret.median(axis=1).dropna()
        if med.empty:
            return None
        i0 = idx.get_loc(med.idxmin())
    elif rule == "yen_surge":
        sub_fx = fx.loc[win]
        fxr = (np.log(sub_fx).shift(-horizon) - np.log(sub_fx)).iloc[:-horizon].dropna()
        if fxr.empty:
            return None
        i0 = idx.get_loc(fxr.idxmin())
    else:
        raise ValueError(f"unknown rule {rule!r}")
    n_have = sum(1 for i in isins if i in prices.columns and np.isfinite(prices[i].iloc[i0]) and np.isfinite(prices[i].iloc[i0 + horizon]))
    eq, f, dy, a, b = _window_returns(prices, fx, cmt, i0, i0 + horizon, isins)
    return dict(name=name, kind="historical", description=f"{description}: {a} to {b}", eq=eq, fx=f, dy=dy,
               window=(a, b), n_names_with_data=n_have, n_names_total=len(isins))


def historical_windows(prices, fx, cmt, isins, horizon=10):
    """Three real 10-business-day windows chosen by rule:
      HIST_EQUITY_CRASH   the window with the lowest median return across the book's names;
      HIST_RATES_SPIKE    the window with the largest rise in the 10-year yield;
      HIST_YEN_SURGE      the window with the largest fall in USDJPY.
    prices: DataFrame of local-currency closes (dates x isin); fx: Series USDJPY;
    cmt: DataFrame of Treasury CMT yields (decimal). Windows do not overlap
    the history edges. Returns a list of scenario dicts."""
    idx = prices.index
    have = [i for i in isins if i in prices.columns]
    logp = np.log(prices[have])
    ret = (logp.shift(-horizon) - logp).iloc[:-horizon]
    med = ret.median(axis=1).dropna()
    i_eq = idx.get_loc(med.idxmin())
    y10 = cmt["DGS10"].reindex(idx).ffill()
    dy10 = (y10.shift(-horizon) - y10).iloc[:-horizon].dropna()
    i_r = idx.get_loc(dy10.idxmax())
    fxr = (np.log(fx).shift(-horizon) - np.log(fx)).iloc[:-horizon].dropna()
    i_y = idx.get_loc(fxr.idxmin())
    out = []
    for name, i0, desc in (("HIST_EQUITY_CRASH", i_eq, "Worst 10-day equity window in the history"),
                           ("HIST_RATES_SPIKE", i_r, "Largest 10-day rise in the 10-year Treasury yield"),
                           ("HIST_YEN_SURGE", i_y, "Largest 10-day fall in USDJPY (yen surge)")):
        eq, f, dy, a, b = _window_returns(prices, fx, cmt, i0, i0 + horizon, isins)
        out.append(dict(name=name, kind="historical", description=f"{desc}: {a} to {b}", eq=eq, fx=f, dy=dy, window=(a, b)))
    return out


def crisis_windows(prices_ext, fx_ext, cmt, isins, horizon=10):
    """Additional NAMED historical episodes, before the 2014 start of the
    engine's primary price history (data/raw/backtest_prices.csv), sourced
    from the wider public price file data/raw/backtest_prices_ext.csv
    (2007-today, yfinance). Not every name traded that far back; a name
    without data in the window takes the cross-sectional median return, the
    same fallback historical_windows() uses (n_names_with_data / n_names_total
    on the returned scenario discloses the coverage).

      HIST_GFC_2008          worst 10-day equity window, Sep-Dec 2008 (Lehman and aftermath)
      HIST_CHINA_DEVAL_2015  worst 10-day equity window, Aug-Sep 2015 (RMB devaluation, global selloff)

    Returns a list of scenario dicts (an episode is skipped, not fatal, if
    the data doesn't support it)."""
    episodes = [
        ("HIST_GFC_2008", "2008-09-01", "2008-12-31", "Worst 10-day equity window, 2008 financial crisis (Lehman and aftermath)"),
        ("HIST_CHINA_DEVAL_2015", "2015-08-01", "2015-09-30", "Worst 10-day equity window, Aug 2015 RMB devaluation / global selloff"),
    ]
    out = []
    for name, start, end, desc in episodes:
        sc = historical_window_in_range(prices_ext, fx_ext, cmt, isins, start, end, name, desc, horizon=horizon)
        if sc is not None:
            out.append(sc)
    return out
