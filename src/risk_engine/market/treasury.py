"""
US Treasury constant-maturity yield history (FRED DGS series, public) and
the Hull-White short-rate volatility implied by REALISED long-end yield moves.

Why: the USD Hull-White factor's sigma used to be the realised vol of the
overnight SOFR fixing (about 63bp). Overnight fixings move in steps on Fed
days, so that number understates how far the 2y-30y yields the book depends
on (the 2049 Treasury underlying BF_0003 above all) actually move: over the
last three years the 10-business-day change of the 20y yield had a standard
deviation of about 15bp, against about 11bp implied by sigma = 63bp. A
Kupiec-style backtest of the rates leg (validation/backtest.py) confirms it.

In a one-factor Hull-White model the zero rate at tenor T has normal vol

    sigma_y(T) = sigma * (1 - exp(-a T)) / (a T)

so sigma is fitted by least squares to the realised normal vols of the
2y-30y CMT yields over the same 3-year window used for every other realised
vol, with `a` held at its swaption-calibrated value. The fit uses zero-rate
vol as a stand-in for par-yield vol (second-order for these tenors).
"""
import os
from io import StringIO

import numpy as np
import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CACHE = os.path.join(ROOT, "data", "raw", "ust_cmt_history.csv")
SERIES = {0.25: "DGS3MO", 0.5: "DGS6MO", 1: "DGS1", 2: "DGS2", 5: "DGS5", 10: "DGS10", 20: "DGS20", 30: "DGS30"}
FIT_TENORS = (2, 5, 10, 20, 30)
TRADING_DAYS = 252


def _fetch(series_id):
    r = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}", timeout=30)
    r.raise_for_status()
    df = pd.read_csv(StringIO(r.text), na_values=["."])
    df.columns = ["date", "v"]
    df["date"] = pd.to_datetime(df["date"])
    return df.dropna().set_index("date")["v"] / 100.0


def load_cmt_history(use_cache=True):
    """DataFrame of daily CMT yields (decimal), columns DGS1..DGS30."""
    if use_cache and os.path.exists(CACHE):
        return pd.read_csv(CACHE, index_col=0, parse_dates=True)
    df = pd.DataFrame({s: _fetch(s) for s in SERIES.values()}).dropna()
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    df.to_csv(CACHE)
    return df


def realized_vols(ref_date, lookback_years=3, hist=None):
    """{tenor_years: annualised normal vol (decimal)} of daily yield changes."""
    hist = load_cmt_history() if hist is None else hist
    end = pd.Timestamp(ref_date)
    w = hist[(hist.index > end - pd.DateOffset(years=lookback_years)) & (hist.index <= end)]
    return {t: float(w[s].diff().dropna().std() * np.sqrt(TRADING_DAYS)) for t, s in SERIES.items()}


def hw_yield_vol(sigma, a, tenor):
    """Normal vol of the zero rate at `tenor` in a one-factor Hull-White model."""
    return sigma if a < 1e-10 else sigma * (1.0 - np.exp(-a * tenor)) / (a * tenor)


def fit_hw_sigma(a, vols, tenors=FIT_TENORS):
    """Least-squares Hull-White sigma to realised yield vols at `tenors`."""
    f = np.array([hw_yield_vol(1.0, a, t) for t in tenors])
    v = np.array([vols[t] for t in tenors])
    return float(f @ v / (f @ f))
