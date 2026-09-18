"""
Assembles calibrated models (HullWhite1F + CorrelatedGBM) from real market
data already collected -- no synthetic/made-up numbers except the two
disclosed assumptions named below.

Real data used:
  - Today's USD curve: src/risk_engine/market/sofr.py (Databento SOFR futures)
  - Equity spots/dividends: src/risk_engine/market/equities.py (yfinance)
  - USDJPY spot: src/risk_engine/market/fx.py (yfinance)
  - Volatilities: data/processed/volatilities.csv (src/risk_engine/market/vols.py)
  - Correlation matrix: data/processed/correlation_matrix.csv (correlations.py)

Hull-White mean reversion `a` is CALIBRATED (models/hw_calibration.py) from
the historical volatility term structure of SOFR futures at different
tenors -- not the textbook a=0.03 guess used before that calibration was
built (see docs/notes/convergence_study.md for why that guess was flagged
as the largest unquantified source of model uncertainty). Cached in
data/processed/hull_white_calibration.json; refresh via
scripts/calibrate_hull_white.py. Falls back to the textbook value only if
both the cache and a live recalibration are unavailable.

Remaining disclosed simplification (can't be derived from data we have
access to): JPY equities' drift uses r_USD(t) minus a CONSTANT differential
backed out from real CME JPY futures (6J, via Databento) vs. our own real
USD curve, via covered interest rate parity -- real data, but a
constant-differential simplification rather than a full second stochastic
JPY curve.
"""
import csv
import math
import os
import re
from datetime import date, timedelta

import pandas as pd

from .rates import HullWhite1F
from .equity_fx import CorrelatedGBM
from ..market.sofr import fetch_raw as fetch_sofr_raw, build_curve, _client, DATASET
from ..market.equities import fetch_raw as fetch_equity_raw, clean as clean_equities
from ..market.fx import fetch_spot as fetch_fx_spot

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
TD = os.path.join(ROOT, "trade_data")
U = os.path.join(TD, "underlyings")
PROCESSED = os.path.join(ROOT, "data", "processed")

_JPY_FUT_RE = re.compile(r"^6J[FGHJKMNQUVXZ]\d$")
_MONTH_CODE = {"F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
               "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12}


def _isin_to_ticker():
    mapping = {}
    with open(os.path.join(U, "equities.csv"), newline="") as f:
        for row in csv.DictReader(f):
            if row["isin"]:
                mapping[row["isin"]] = row["ticker"]
    return mapping


def _isin_currency():
    out = {}
    with open(os.path.join(U, "equities.csv"), newline="") as f:
        for row in csv.DictReader(f):
            if row["isin"]:
                out[row["isin"]] = row["currency"]
    return out


def implied_jpy_usd_rate_diff_from_bloomberg(tenor="12M"):
    """Preferred route: the JPY-USD rate differential read directly off two
    REAL Bloomberg-built zero curves (data/raw/bloomberg/ -- see
    market/bloomberg.py) at a matching tenor, rather than backed out from a
    single CME JPY futures contract. More precise: an actual quoted curve
    point on each side, not a covered-interest-parity inversion of one
    futures price. Raises if the Bloomberg data isn't available (caller
    falls back to implied_jpy_usd_rate_diff below)."""
    from ..market.bloomberg import load_usd_bloomberg_zero_curve, load_jpy_bloomberg_zero_curve, available
    if not available():
        raise FileNotFoundError("Bloomberg data export not found under data/raw/bloomberg/")
    usd = load_usd_bloomberg_zero_curve().set_index("tenor")
    jpy = load_jpy_bloomberg_zero_curve().set_index("tenor")
    if tenor not in usd.index or tenor not in jpy.index:
        raise ValueError(f"Tenor {tenor!r} not present in both Bloomberg curves")
    diff = float(usd.loc[tenor, "zero_rate"] - jpy.loc[tenor, "zero_rate"])
    print(f"  JPY-USD rate differential from real Bloomberg curves (tenor={tenor}): {diff:.4%}")
    return diff


def implied_jpy_usd_rate_diff(ref_date, usd_curve, fx_spot):
    """Back out a constant (r_USD - r_JPY) differential from REAL data:
    the nearest ~1y outright CME JPY futures contract (6J, Databento, same
    dataset as SOFR) vs. our own real USD curve, via covered interest
    parity: F/S = P_JPY(0,T) / P_USD(0,T).

    6J quotes USD per JPY (inverse of our JPY-per-USD convention) -- must
    invert before using. Falls back to 0.0 (assume no differential) if the
    Databento call fails, so simulation isn't hard-blocked on this one
    secondary lookup; logs a warning either way.
    """
    try:
        client = _client()
        end = ref_date if isinstance(ref_date, date) else date.fromisoformat(str(ref_date))
        start = end - timedelta(days=5)
        data = client.timeseries.get_range(
            dataset=DATASET, symbols=["6J.FUT"], stype_in="parent",
            schema="ohlcv-1d", start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(),
        )
        df = data.to_df().reset_index()
        df = df[df["symbol"].apply(lambda s: bool(_JPY_FUT_RE.match(s)))]
        df = df.sort_values("ts_event").groupby("symbol", as_index=False).last()

        def contract_years_out(symbol):
            month = _MONTH_CODE[symbol[2]]
            year_digit = int(symbol[3])
            year = end.year - (end.year % 10) + year_digit
            from calendar import monthrange
            fw, _ = monthrange(year, month)
            third_wed = date(year, month, 1 + (2 - fw) % 7 + 14)
            if third_wed < end:
                return None
            return (third_wed - end).days / 365.0, third_wed

        candidates = []
        for _, row in df.iterrows():
            r = contract_years_out(row["symbol"])
            if r is not None:
                candidates.append((abs(r[0] - 1.0), r[0], row["close"]))
        if not candidates:
            raise ValueError("no usable live 6J contract found")
        candidates.sort(key=lambda c: c[0])
        _, T, usd_per_jpy = candidates[0]

        jpy_per_usd_fwd = 1.0 / usd_per_jpy
        p_usd_T = usd_curve.discount(ref_date + timedelta(days=round(T * 365)))
        p_jpy_T = p_usd_T * (jpy_per_usd_fwd / fx_spot)
        r_usd_T = -math.log(p_usd_T) / T
        r_jpy_T = -math.log(p_jpy_T) / T
        diff = r_usd_T - r_jpy_T
        print(f"  JPY-USD rate differential from 6J futures (T={T:.2f}y): {diff:.4%}")
        return diff
    except Exception as exc:
        print(f"  WARN: could not derive JPY-USD rate differential from 6J futures ({exc}); "
              f"falling back to 0.0 (equity/FX drift will ignore the JPY/USD rate gap)")
        return 0.0


def load_vol_table():
    return pd.read_csv(os.path.join(PROCESSED, "volatilities.csv"), index_col="factor")["volatility"].to_dict()


def load_correlation_matrix():
    return pd.read_csv(os.path.join(PROCESSED, "correlation_matrix.csv"), index_col=0)


HW_CALIBRATION_CACHE = os.path.join(PROCESSED, "hull_white_calibration.json")
HW_CALIBRATION_CACHE_SWAPTION = os.path.join(PROCESSED, "hull_white_calibration_swaption.json")
DEFAULT_MEAN_REVERSION_FALLBACK = 0.03  # only used if no calibration route is available at all


def load_or_calibrate_mean_reversion(ref_date, use_cache=True):
    """Hull-White mean reversion `a`. Preference order, each real data,
    highest-quality first:

      1. Swaption-based (models/hw_calibration.calibrate_mean_reversion_
         from_swaptions) -- the genuine industry-standard calibration route,
         using the real ATM normal swaption vol cube from the user's
         Bloomberg data export (data/raw/bloomberg/). Cached separately
         (HW_CALIBRATION_CACHE_SWAPTION) since that data is a static local
         file, not a live fetch, so "caching" is really just avoiding
         re-parsing CSVs every run.
      2. Futures-vol-decay proxy (calibrate_mean_reversion) -- the original
         route, used when the Bloomberg swaption data isn't available.
         Cached to disk (HW_CALIBRATION_CACHE) since it fetches ~2 years of
         history for 8 contracts via Databento -- too slow to redo on every
         simulation run.
      3. The disclosed textbook constant, only if neither real route works.

    Both real calibrations disagree somewhat (swaption: a~0.017; futures
    proxy: a~0.046) -- expected, since they use different instruments and
    methods; see docs/notes/hull_white_calibration.md for the full
    comparison and why the swaption route is preferred when available.
    """
    import json

    if use_cache and os.path.exists(HW_CALIBRATION_CACHE_SWAPTION):
        with open(HW_CALIBRATION_CACHE_SWAPTION) as f:
            cached = json.load(f)
        return cached["a"], cached

    try:
        from .hw_calibration import calibrate_mean_reversion_from_swaptions
        from ..market.bloomberg import available as bbg_available
        if bbg_available():
            print("  Hull-White mean reversion (calibrating from real USD swaption vol cube, Bloomberg data)...")
            result = calibrate_mean_reversion_from_swaptions()
            os.makedirs(PROCESSED, exist_ok=True)
            with open(HW_CALIBRATION_CACHE_SWAPTION, "w") as f:
                json.dump(result, f, indent=2)
            return result["a"], result
    except Exception as exc:
        print(f"  WARN: swaption-based Hull-White calibration failed ({exc}); "
              f"falling back to the SOFR-futures-vol-decay proxy")

    if use_cache and os.path.exists(HW_CALIBRATION_CACHE):
        with open(HW_CALIBRATION_CACHE) as f:
            cached = json.load(f)
        return cached["a"], cached

    print("  Hull-White mean reversion (calibrating from SOFR futures history, no cache found)...")
    try:
        from .hw_calibration import calibrate_mean_reversion
        result = calibrate_mean_reversion(ref_date)
        os.makedirs(PROCESSED, exist_ok=True)
        with open(HW_CALIBRATION_CACHE, "w") as f:
            json.dump(result, f, indent=2)
        return result["a"], result
    except Exception as exc:
        print(f"  WARN: Hull-White calibration failed ({exc}); falling back to disclosed "
              f"assumption a={DEFAULT_MEAN_REVERSION_FALLBACK} (see models/rates.py)")
        return DEFAULT_MEAN_REVERSION_FALLBACK, None


# Disclosed assumption: no historical JPY OIS time series exists in our
# Bloomberg export (only the single 2026-08-31 snapshot -- see
# data/raw/bloomberg/data_bloomberg/metadata/data_gaps_and_exclusions.csv),
# so a USD-JPY short-rate factor correlation cannot be calibrated from real
# data. This constant is a disclosed simplification (a modest positive
# value, reflecting the general co-movement most G10 rate pairs show), not
# a fitted number.
USD_JPY_RATE_FACTOR_CORR_ASSUMPTION = 0.3


def load_or_calibrate_jpy_mean_reversion(usd_mean_reversion_a):
    """JPY Hull-White mean reversion `a`. Tries the same swaption-decay
    method used for USD (hw_calibration.calibrate_mean_reversion_from_
    swaptions), but with a real finding disclosed rather than hidden: unlike
    USD's cube, the JPY ATM normal swaption vol in our snapshot RISES with
    swap tenor instead of decaying (plausibly a BOJ policy-normalization-era
    pricing effect specific to this one 2026-08-31 snapshot, not a generic
    property of JPY rates) -- fitting exp(-a*tenor) to a rising curve
    produces a negative `a`, which isn't a usable mean-reversion speed (it
    would mean the short rate diverges rather than reverts). When that
    happens, this falls back to reusing the USD-calibrated `a` for the JPY
    factor too: both are still Gaussian Hull-White short-rate models, so a
    shared, physically valid mean-reversion speed is a more honest choice
    than forcing an invalid fit.
    """
    from .hw_calibration import calibrate_mean_reversion_from_swaptions
    try:
        result = calibrate_mean_reversion_from_swaptions(currency="JPY")
        if result["a"] > 0:
            return result["a"], result
        print(f"  WARN: JPY swaption-implied mean reversion is negative (a={result['a']:.4f} -- "
              f"the JPY vol cube's tenor shape rises rather than decays here); falling back to "
              f"the USD-calibrated a={usd_mean_reversion_a:.4f} for the JPY factor too "
              f"(disclosed simplification, see calibration.py)")
        return usd_mean_reversion_a, result
    except Exception as exc:
        print(f"  WARN: JPY swaption-based Hull-White calibration failed ({exc}); "
              f"falling back to the USD-calibrated a={usd_mean_reversion_a:.4f}")
        return usd_mean_reversion_a, None


def build_jpy_hull_white(ref_date, usd_mean_reversion_a):
    """A genuine second Hull-White factor for JPY, built off the REAL JPY
    OIS curve (Bloomberg, 2026-08-31 snapshot) -- Gaussian, so it natively
    supports negative short rates with no floor, unlike CIR/Black-Karasinski
    -- the right structural choice given JPY's real NIRP-era history (see
    tests/test_rates.py's negative-rate regression). Replaces treating JPY
    only as "USD minus a constant differential" with an actual simulatable
    JPY rate model; calibration.py's `hw_jpy` is not yet wired into the
    simulation engine's path generation (engine.py currently only steps the
    USD factor) -- that's the next step, tracked separately.
    """
    from ..market.bloomberg import load_jpy_bloomberg_zero_curve, build_curve_from_bloomberg_zero_curve, available
    if not available():
        raise FileNotFoundError("Bloomberg data export not found under data/raw/bloomberg/ -- "
                                 "the JPY Hull-White factor needs the real JPY OIS curve")
    jpy_curve = build_curve_from_bloomberg_zero_curve(load_jpy_bloomberg_zero_curve(), ref_date)
    a_jpy, calib_detail = load_or_calibrate_jpy_mean_reversion(usd_mean_reversion_a)
    # sigma: prefer the JPY swaption fit's own level (real data, even when its
    # `a` isn't usable -- the vol LEVEL from the fit is still informative,
    # only the tenor-decay slope was the problem); fall back to a small
    # disclosed constant if no swaption-based detail is available at all.
    sigma_jpy = calib_detail["sigma_from_fit"] if calib_detail else 0.01
    hw_jpy = HullWhite1F(jpy_curve, sigma=sigma_jpy, a=a_jpy)
    return hw_jpy, {"a": a_jpy, "sigma": sigma_jpy, "calibration_detail": calib_detail}


def build_calibration(ref_date):
    """Returns a dict with everything the simulation engine needs:
    hw (HullWhite1F), gbm (CorrelatedGBM), corr_matrix (DataFrame, ordered),
    factor_order (list[str], the correlation matrix's own column order),
    equity_spots, dividends, fx_spot, usd_curve.
    """
    print(f"Calibrating models as of {ref_date}...")
    print("  USD curve (Databento SOFR futures)...")
    sofr_raw = fetch_sofr_raw(ref_date)
    usd_curve = build_curve(ref_date, raw_df=sofr_raw)

    print("  Equity spots + dividends (yfinance)...")
    isin_to_ticker = _isin_to_ticker()
    eq_clean = clean_equities(fetch_equity_raw(isin_to_ticker))
    equity_spots = {isin: spot for isin, (spot, _) in eq_clean.items()}
    dividends = {isin: div for isin, (_, div) in eq_clean.items()}

    print("  USDJPY spot (yfinance)...")
    fx_spot = fetch_fx_spot()

    vol_table = load_vol_table()
    corr_matrix = load_correlation_matrix()
    factor_order = list(corr_matrix.columns)  # ISINs..., FX_USDJPY, RATE_USD

    try:
        jpy_diff = implied_jpy_usd_rate_diff_from_bloomberg()
    except Exception as exc:
        print(f"  WARN: Bloomberg-curve JPY-USD differential unavailable ({exc}); "
              f"falling back to the 6J-futures-implied route")
        jpy_diff = implied_jpy_usd_rate_diff(ref_date, usd_curve, fx_spot)

    rate_vol = vol_table["RATE_USD"]
    mean_reversion_a, hw_calib_detail = load_or_calibrate_mean_reversion(ref_date)
    hw = HullWhite1F(usd_curve, sigma=rate_vol, a=mean_reversion_a)

    try:
        hw_jpy, hw_jpy_detail = build_jpy_hull_white(ref_date, mean_reversion_a)
        print(f"  JPY Hull-White factor built (real JPY OIS curve, a={hw_jpy_detail['a']:.4f}, "
              f"sigma={hw_jpy_detail['sigma']:.4%}) -- Gaussian, so it natively supports negative "
              f"rates like JPY saw historically, no floor")
    except Exception as exc:
        print(f"  WARN: could not build JPY Hull-White factor ({exc}); JPY equities/FX keep using "
              f"the constant rate-differential approximation only")
        hw_jpy, hw_jpy_detail = None, None

    equity_factor_names = [f for f in factor_order if f not in ("FX_USDJPY", "RATE_USD")]
    currencies = _isin_currency()
    gbm = CorrelatedGBM(
        factor_names=equity_factor_names,
        spots={**equity_spots, "FX_USDJPY": fx_spot},
        vols=vol_table,
        currencies=currencies,
        dividends=dividends,
        jpy_usd_rate_diff=jpy_diff,
    )

    return {
        "ref_date": usd_curve.ref_date,
        "usd_curve": usd_curve,
        "hw": hw,
        "hw_jpy": hw_jpy,
        "hw_jpy_detail": hw_jpy_detail,
        "usd_jpy_rate_factor_corr_assumption": USD_JPY_RATE_FACTOR_CORR_ASSUMPTION,
        "gbm": gbm,
        "corr_matrix": corr_matrix,
        "factor_order": factor_order,
        "equity_spots": equity_spots,
        "dividends": dividends,
        "fx_spot": fx_spot,
        "jpy_usd_rate_diff": jpy_diff,
        "hw_mean_reversion_a": mean_reversion_a,
        "hw_calibration_detail": hw_calib_detail,
    }
