"""
Calibrates the Hull-White mean-reversion speed `a` from REAL historical
data, replacing the disclosed textbook assumption (a=0.03) flagged in
docs/notes/convergence_study.md as the largest unquantified source of
model uncertainty in the engine.

Why this needed real work, not just a lookup: the standard way to calibrate
`a` is against swaption/cap implied volatilities, which we don't have
access to. Instead, this uses a real, standard alternative: HW1F predicts
that the volatility of the instantaneous forward rate decays exponentially
with time-to-maturity,

    sigma_f(t, T) = sigma * exp(-a * (T - t))

So measuring the REALIZED volatility of several SOFR futures contracts at
different tenors (each contract's implied rate is a proxy for a forward
rate at that tenor) lets `a` be fit from how fast that volatility decays
across tenors -- linear regression of ln(vol) against tenor, slope = -a.
This is a standard alternative calibration route when swaption data isn't
available (sometimes called calibrating to the historical volatility term
structure), not something invented for this project.

Approximation disclosed rather than hidden: each contract's time-to-
maturity shrinks day by day as its own historical window progresses, so
"the tenor" isn't single-valued over the whole history -- this uses each
contract's AVERAGE tenor over its available history as one representative
x-value per contract. A refinement would bucket by tenor across all
contract-days rather than averaging per contract.

The fitted `sigma` from this same regression is NOT used to override
models/rates.py's `sigma` (which comes from realized SOFR spot vol,
vols.py, a more directly interpretable measure of instantaneous rate
vol) -- it's reported alongside as a cross-check. See
build_calibrated_mean_reversion()'s docstring for why.
"""
import math
from datetime import date, timedelta

import numpy as np
import pandas as pd

from ..market.sofr import _client, DATASET, _contract_period

CANDIDATE_CONTRACTS = ["SR3U6", "SR3Z6", "SR3H7", "SR3U7", "SR3H8", "SR3U8", "SR3H9", "SR3H0"]


def fetch_contract_history(symbol, ref_date, lookback_days=730):
    client = _client()
    end = ref_date
    start = end - timedelta(days=lookback_days)
    data = client.timeseries.get_range(
        dataset=DATASET, symbols=[symbol], stype_in="raw_symbol",
        schema="ohlcv-1d", start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(),
    )
    return data.to_df().reset_index()


def realized_vol_and_avg_tenor(symbol, ref_date):
    """Annualized normal vol of the contract's implied rate (100-price),
    and its average time-to-maturity (years) over the available history."""
    df = fetch_contract_history(symbol, ref_date)
    if len(df) < 30:
        return None
    implied_rate = (100.0 - df["close"]) / 100.0
    diffs = implied_rate.diff().dropna()
    vol = float(diffs.std() * math.sqrt(252))

    contract_start, _ = _contract_period(symbol, ref_date)
    ts = df["ts_event"].dt.tz_localize(None).dt.date
    tenors = [(contract_start - d).days / 365.0 for d in ts]
    tenors = [t for t in tenors if t > 0]
    avg_tenor = float(np.mean(tenors)) if tenors else None
    return vol, avg_tenor, len(df)


def calibrate_mean_reversion(ref_date, contracts=CANDIDATE_CONTRACTS, min_contracts=3):
    """Returns {"a": ..., "sigma_from_fit": ..., "r_squared": ..., "contracts": [...]}.
    `a` is the value to actually use in HullWhite1F; `sigma_from_fit` is a
    cross-check only (see module docstring)."""
    rows = []
    for symbol in contracts:
        result = realized_vol_and_avg_tenor(symbol, ref_date)
        if result is None:
            continue
        vol, avg_tenor, n_obs = result
        rows.append({"symbol": symbol, "vol": vol, "avg_tenor": avg_tenor, "n_obs": n_obs})

    if len(rows) < min_contracts:
        raise ValueError(f"Only {len(rows)} contracts had enough history to calibrate "
                          f"(need >= {min_contracts})")

    tenors = np.array([r["avg_tenor"] for r in rows])
    log_vols = np.log([r["vol"] for r in rows])
    A = np.vstack([tenors, np.ones_like(tenors)]).T
    slope, intercept = np.linalg.lstsq(A, log_vols, rcond=None)[0]
    a_fit = -slope
    sigma_fit = math.exp(intercept)

    residuals = log_vols - (slope * tenors + intercept)
    ss_res = np.sum(residuals ** 2)
    ss_tot = np.sum((log_vols - log_vols.mean()) ** 2)
    r_squared = float(1 - ss_res / ss_tot) if ss_tot > 0 else float("nan")

    return {"a": float(a_fit), "sigma_from_fit": float(sigma_fit),
            "r_squared": r_squared, "contracts": rows}


_TENOR_YEARS = {"1M": 1/12, "2M": 2/12, "3M": 0.25, "6M": 0.5, "1Y": 1, "18M": 1.5,
                "2Y": 2, "3Y": 3, "4Y": 4, "5Y": 5, "6Y": 6, "7Y": 7, "8Y": 8, "9Y": 9,
                "10Y": 10, "12Y": 12, "15Y": 15, "20Y": 20, "25Y": 25, "30Y": 30}


def calibrate_mean_reversion_from_swaptions(expiry="1M", max_tenor_years=15, currency="USD"):
    """Calibrates `a` from a REAL ATM normal swaption volatility cube
    (data/raw/bloomberg/ -- a one-time Bloomberg export the user provided,
    not a live feed; see market/bloomberg.py's module docstring), the
    standard textbook route this project's original docstring above flagged
    as unavailable when it was first written.

    `currency`: "USD" (SOFR, default) or "JPY" (OIS) -- selects which
    swaption vol cube to load. Same method either way; JPY's cube is a
    single 2026-08-31 snapshot rather than a history, which is fine here
    since this fit only ever uses one snapshot's cross-tenor shape anyway.

    Method, disclosed as a real simplification rather than a full 2D
    swaption-cube fit: take ATM normal vol at ONE short expiry (default 1M,
    close to "an option starting almost immediately") across swap tenors,
    and fit the same exponential-decay relationship used for the futures-
    based calibration above:

        vol(tenor) = sigma * exp(-a * tenor)

    A swaption's ATM vol is technically the vol of the underlying SWAP
    RATE observed at the option's expiry, not a point forward rate -- using
    a single short-expiry row as a proxy for "how fast forward-rate vol
    decays with tenor" is standard practice for a quick HW1F alpha
    estimate, but a full rigorous fit would price swaptions under HW1F
    (e.g. via the Jamshidian decomposition) and fit across the WHOLE
    expiry x tenor grid jointly -- a larger undertaking not done here.
    max_tenor_years caps the fit to the tenor range most relevant to this
    book's ~2yr horizon (the far end of the cube, 20-30Y, reflects very
    different market dynamics -- pension-driven long-end flows -- not
    informative for calibrating short-dated CCR exposure).
    """
    from ..market.bloomberg import load_usd_swaption_vols, load_jpy_swaption_vols, available

    if not available():
        raise FileNotFoundError("Bloomberg data export not found under data/raw/bloomberg/")

    loaders = {"USD": load_usd_swaption_vols, "JPY": load_jpy_swaption_vols}
    if currency not in loaders:
        raise ValueError(f"Unsupported currency {currency!r}; expected one of {list(loaders)}")
    cube = loaders[currency]()
    if expiry not in cube.index:
        raise ValueError(f"Expiry {expiry!r} not in swaption cube; available: {list(cube.index)}")
    row = cube.loc[expiry]

    tenors, vols, labels = [], [], []
    for tenor_label, vol in row.items():
        years = _TENOR_YEARS.get(tenor_label)
        if years is None or years > max_tenor_years:
            continue
        tenors.append(years)
        vols.append(float(vol))
        labels.append(tenor_label)

    tenors = np.array(tenors)
    log_vols = np.log(vols)
    A = np.vstack([tenors, np.ones_like(tenors)]).T
    slope, intercept = np.linalg.lstsq(A, log_vols, rcond=None)[0]
    a_fit = -slope
    sigma_fit = math.exp(intercept)

    residuals = log_vols - (slope * tenors + intercept)
    ss_res = np.sum(residuals ** 2)
    ss_tot = np.sum((log_vols - log_vols.mean()) ** 2)
    r_squared = float(1 - ss_res / ss_tot) if ss_tot > 0 else float("nan")

    rows = [{"tenor": lbl, "years": float(t), "vol": float(v)} for lbl, t, v in zip(labels, tenors, vols)]
    return {"a": float(a_fit), "sigma_from_fit": float(sigma_fit), "r_squared": r_squared,
            "currency": currency, "expiry_used": expiry, "max_tenor_years": max_tenor_years,
            "points": rows, "method": "swaption_atm_normal_vol_term_structure"}


def calibrate_jpy_mean_reversion_from_jgb_yields(ref_date, lookback_years=3, max_tenor_years=30):
    """A second, INDEPENDENT attempt at JPY mean reversion `a`, using real
    multi-tenor JGB yield history from Japan's Ministry of Finance
    (market/mof_jgb.py -- daily, 1Y-40Y, since 1974) instead of the single-
    snapshot Bloomberg swaption cube. Same method as calibrate_mean_
    reversion() (the USD futures-vol-decay approach): realized vol of the
    yield LEVEL at each tenor over the lookback window, fit
    sigma(tenor) = sigma * exp(-a * tenor) via log-linear regression.

    Real finding (the reason this function exists, and why it's still not
    what gets used, per load_or_calibrate_jpy_mean_reversion()): JGB
    realized vol RISES with tenor here too -- 1Y vol is consistently the
    SMALLEST and 30-40Y the LARGEST, at every lookback window tested
    (1y, 2y, 5y, 10y) -- the opposite of the decay this model needs, and
    the same qualitative shape the Bloomberg swaption cube showed. This
    independently corroborates, using a completely different real 52-year
    dataset, that the issue isn't one bad snapshot -- JPY's realized-vol
    term structure genuinely doesn't fit a single-factor HW's exponential-
    decay assumption over the historical period covered here (plausibly
    because BOJ suppressed short-end vol for decades via ZIRP/NIRP/YCC,
    while longer tenors moved more freely -- the reverse of what drives
    USD's decay). This is disclosed as a genuine data finding, not
    something the fallback in load_or_calibrate_jpy_mean_reversion() is
    trying to paper over.
    """
    from ..market.mof_jgb import fetch_jgb_yield_history, TENOR_COLUMNS

    yields = fetch_jgb_yield_history()
    end = yields.index.max() if ref_date is None else pd.Timestamp(ref_date)
    start = end - pd.DateOffset(years=lookback_years)
    window = yields[(yields.index > start) & (yields.index <= end)]

    tenor_years_map = {"1Y": 1, "2Y": 2, "3Y": 3, "4Y": 4, "5Y": 5, "6Y": 6, "7Y": 7,
                        "8Y": 8, "9Y": 9, "10Y": 10, "15Y": 15, "20Y": 20, "25Y": 25,
                        "30Y": 30, "40Y": 40}

    tenors, vols, labels = [], [], []
    for col in TENOR_COLUMNS:
        t = tenor_years_map[col]
        if t > max_tenor_years:
            continue
        series = window[col].dropna()
        diffs = series.diff().dropna()
        if len(diffs) < 30:
            continue
        vol = float(diffs.std() * math.sqrt(252))
        if vol <= 0:
            continue
        tenors.append(t)
        vols.append(vol)
        labels.append(col)

    if len(tenors) < 3:
        raise ValueError(f"Only {len(tenors)} usable JGB tenors in the {lookback_years}y "
                          f"window ending {end.date()} -- too few to fit a decay curve")

    tenors_arr = np.array(tenors, dtype=float)
    log_vols = np.log(vols)
    A = np.vstack([tenors_arr, np.ones_like(tenors_arr)]).T
    slope, intercept = np.linalg.lstsq(A, log_vols, rcond=None)[0]
    a_fit = -slope
    sigma_fit = math.exp(intercept)

    residuals = log_vols - (slope * tenors_arr + intercept)
    ss_res = np.sum(residuals ** 2)
    ss_tot = np.sum((log_vols - log_vols.mean()) ** 2)
    r_squared = float(1 - ss_res / ss_tot) if ss_tot > 0 else float("nan")

    rows = [{"tenor": lbl, "years": float(t), "vol": float(v)} for lbl, t, v in zip(labels, tenors, vols)]
    return {"a": float(a_fit), "sigma_from_fit": float(sigma_fit), "r_squared": r_squared,
            "lookback_years": lookback_years, "max_tenor_years": max_tenor_years,
            "points": rows, "method": "jgb_realized_yield_vol_term_structure"}
