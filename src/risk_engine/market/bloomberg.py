"""
Loaders for the Bloomberg data export provided directly by the user
(data/raw/bloomberg/data_bloomberg/) -- NOT a live API, a one-time static
snapshot dated 2026-08-31 (3 days after our Databento/yfinance snapshot of
2026-08-28; close enough for curve-shape/vol calibration purposes, not
close enough to treat as the exact same instant -- disclosed, not hidden).

Per data_bloomberg/metadata/manifest.csv and data_gaps_and_exclusions.csv:
  - USD SOFR: full history, a real market-quote curve, a Bloomberg-built
    zero/discount curve, AND a real ATM normal swaption volatility cube
    (expiry x swap tenor) -- this is what unlocks a genuine swaption-based
    Hull-White calibration (models/hw_calibration.py's own docstring flagged
    this as the standard method we didn't have access to; now we do).
  - JPY OIS: only a single 2026-08-31 snapshot (curve + swaption vols), no
    full history -- fine for today's curve, not for a historical vol study.
  - USDJPY: full history of spot, forward points, and an implied vol
    surface (ATM/25RR/25BF/10RR/10BF).
  - SPX/TOPIX: only a 2026-08-31 implied-vol snapshot, INDEX level, not
    per-single-name -- not directly usable for our 37 individual equity
    names' vols without a separate basis assumption, so not wired in here.

This module only loads/parses; it does not decide what to do with the
data -- see hw_calibration.py and fx.py for the actual model wiring.
"""
import os

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
BBG_ROOT = os.path.join(ROOT, "data", "raw", "bloomberg", "data_bloomberg")
BBG_DATE = "2026-08-31"


def available():
    """Whether the Bloomberg data export is present on disk."""
    return os.path.isdir(BBG_ROOT)


def load_usd_swaption_vols():
    """ATM normal swaption vol cube (expiry x swap tenor), in decimal
    (Bloomberg quotes in bp -- divide by 10000). Returns a DataFrame
    indexed by expiry, columns = swap tenor labels, values = decimal vol."""
    path = os.path.join(BBG_ROOT, "rates", f"usd_sofr_atm_normal_swaption_vol_{BBG_DATE}_wide.csv")
    df = pd.read_csv(path, index_col="expiry")
    return df / 10000.0


def load_usd_bloomberg_zero_curve():
    """Bloomberg's own USD SOFR zero/discount curve (Step Forward, continuous
    compounding). Returns a DataFrame with tenor, zero_rate (decimal),
    discount_factor."""
    path = os.path.join(BBG_ROOT, "rates", f"usd_sofr_bloomberg_zero_discount_curve_{BBG_DATE}.csv")
    df = pd.read_csv(path)
    df["zero_rate"] = df["zero_rate_pct"] / 100.0
    return df[["tenor", "zero_rate", "discount_factor"]]


def load_jpy_bloomberg_zero_curve():
    """Bloomberg's JPY OIS zero/discount curve, same shape as the USD one."""
    path = os.path.join(BBG_ROOT, "rates", f"jpy_ois_bloomberg_zero_discount_curve_{BBG_DATE}.csv")
    df = pd.read_csv(path)
    df["zero_rate"] = df["zero_rate_pct"] / 100.0
    return df[["tenor", "zero_rate", "discount_factor"]]


def load_usdjpy_forward_points():
    """Real USDJPY forward points curve on BBG_DATE (JPY per USD adjustment
    to spot, per tenor). Returns {tenor_label: forward_adjustment_jpy}."""
    path = os.path.join(BBG_ROOT, "fx", f"usdjpy_forward_points_curve_wide_2017-01-01_{BBG_DATE}.csv")
    df = pd.read_csv(path)
    row = df[df["date"] == BBG_DATE]
    if row.empty:
        raise ValueError(f"No forward points row for {BBG_DATE} in {path}")
    row = row.iloc[0]
    out = {}
    for col in df.columns:
        if col == "date":
            continue
        tenor = col.split(" ")[0].replace("JPY", "")  # "JPY1M BGN Curncy" -> "1M"
        out[tenor] = float(row[col]) / 100.0  # FWD_SCALE=2, per manifest
    return out


def load_usdjpy_spot():
    """Real USDJPY spot on BBG_DATE (px_last)."""
    path = os.path.join(BBG_ROOT, "fx", f"usdjpy_spot_2017-01-01_{BBG_DATE}.csv")
    df = pd.read_csv(path)
    row = df[df["date"] == BBG_DATE].iloc[0]
    return float(row["px_last"])
