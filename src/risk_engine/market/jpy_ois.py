"""
Full daily JPY OIS (TONA swap) par-rate history, 2011-10-05 to 2026-09-18,
35 tenors from 1 week to 40 years, plus the overnight call rate
(MUTKCALM) -- a Bloomberg export provided by the project team, saved in
data/raw/sources/ (JPY.xlsx; jpy_ois_history.csv is the parsed copy).
This is the multi-tenor, multi-year JPY history that the earlier one-day
Bloomberg snapshot lacked, and it includes the whole negative-rate era
(par rates below zero out to 5 years, minimum -0.373%).

Bloomberg ticker suffixes: 1Z/2Z/3Z = 1/2/3 weeks, A..K = 1..11 months,
1 = 1 year, 1C/1F/1I = 15/18/21 months, then whole years (2..12, 15, 20,
25, 30, 35, 40). Values are percent per annum.

Licensed data: derived numbers only leave this repository (never the raw
series).
"""
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SRC = os.path.join(ROOT, "data", "raw", "sources")
CSV = os.path.join(SRC, "jpy_ois_history.csv")
XLSX = os.path.join(SRC, "JPY.xlsx")

_WEEKS = {"1Z": 1, "2Z": 2, "3Z": 3}
_MONTHS = {c: i + 1 for i, c in enumerate("ABCDEFGHIJK")}
_ODD = {"1C": 15 / 12, "1F": 18 / 12, "1I": 21 / 12}
_YEARS = {str(y): float(y) for y in list(range(1, 13)) + [15, 20, 25, 30, 35, 40]}


def tenor_years(code):
    """'JYSO5' -> 5.0, 'JYSOA' -> 1/12, 'JYSO2Z' -> 2/52 (Bloomberg suffix map)."""
    suf = code.replace("JYSO", "")
    if suf in _WEEKS:
        return _WEEKS[suf] / 52.0
    if suf in _MONTHS:
        return _MONTHS[suf] / 12.0
    if suf in _ODD:
        return _ODD[suf]
    return _YEARS[suf]


def available():
    return os.path.exists(CSV) or os.path.exists(XLSX)


def load_jpy_ois_history():
    """DataFrame indexed by date; columns MUTKCALM and JYSO* (percent)."""
    if os.path.exists(CSV):
        return pd.read_csv(CSV, index_col=0, parse_dates=True)
    import openpyxl
    rows = list(openpyxl.load_workbook(XLSX, data_only=True).active.iter_rows(values_only=True))
    df = pd.DataFrame(rows[6:], columns=["date"] + [h.split()[0] for h in rows[3][1:]]).dropna(subset=["date"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").astype(float)
    df.to_csv(CSV)
    return df


def par_curve(ref_date, hist=None):
    """{tenor_years: par rate (decimal)} on the last date <= ref_date."""
    hist = load_jpy_ois_history() if hist is None else hist
    row = hist[hist.index <= pd.Timestamp(ref_date)].iloc[-1]
    return {tenor_years(c): float(row[c]) / 100.0 for c in hist.columns if c.startswith("JYSO")}


def bootstrap_discount_factors(par):
    """Zero-coupon discount factors from OIS par rates. Up to 1 year: one
    payment, DF = 1/(1 + r T). Beyond: annual fixed payments (tau = 1) on an
    annual grid (par rates linearly interpolated between quoted tenors),
    DF_n = (1 - r_n * sum_{i<n} DF_i) / (1 + r_n). Returns (times, dfs)."""
    ts = sorted(par)
    short = [(t, par[t]) for t in ts if t <= 1.0 + 1e-9]
    times = [t for t, _ in short]
    dfs = [1.0 / (1.0 + r * t) for t, r in short]
    annual = [t for t in ts if t >= 1.0 - 1e-9 and abs(t - round(t)) < 1e-9]
    rates = [par[t] for t in annual]
    grid = np.arange(2, int(max(annual)) + 1)
    r_grid = np.interp(grid, annual, rates)
    df_prev = [dfs[-1]]  # DF(1)
    for n, r in zip(grid, r_grid):
        d = (1.0 - r * sum(df_prev)) / (1.0 + r)
        df_prev.append(d)
        times.append(float(n))
        dfs.append(d)
    return times, dfs


def jpy_zero_curve(ref_date, hist=None):
    """capitolis_pricers Curve bootstrapped from the OIS par curve on ref_date."""
    from capitolis_pricers.curves import Curve
    from capitolis_pricers.daycount import to_date
    t, d = bootstrap_discount_factors(par_curve(ref_date, hist))
    return Curve(to_date(ref_date), t, d, basis="ACT/365F")


def realized_vol_by_tenor(ref_date, lookback_years=3, tenors=(1, 2, 3, 5, 7, 10, 15, 20, 30), hist=None):
    """Annualised normal vol (decimal per year) of daily OIS par-rate changes
    at each tenor over the window ending ref_date."""
    hist = load_jpy_ois_history() if hist is None else hist
    end = pd.Timestamp(ref_date)
    w = hist[(hist.index > end - pd.DateOffset(years=lookback_years)) & (hist.index <= end)]
    out = {}
    for t in tenors:
        col = next(c for c in hist.columns if c.startswith("JYSO") and abs(tenor_years(c) - t) < 1e-9)
        out[t] = float(w[col].diff().dropna().std() * np.sqrt(252) / 100.0)
    return out


def overnight_vol(ref_date, lookback_years=3, hist=None):
    """Annualised normal vol of the overnight call rate (MUTKCALM)."""
    hist = load_jpy_ois_history() if hist is None else hist
    end = pd.Timestamp(ref_date)
    w = hist[(hist.index > end - pd.DateOffset(years=lookback_years)) & (hist.index <= end)]
    return float(w["MUTKCALM"].diff().dropna().std() * np.sqrt(252) / 100.0)
