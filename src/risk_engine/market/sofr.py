"""
USD OIS (SOFR) discount curve — fetch/clean/cache.

Pillars and conventions: data/MARKET_DATA.md §1 (O/N, T/N, 1W...10Y, ACT/360).

Databento does not publish a ready-made SOFR/OIS swap curve -- it only has
the underlying futures. So this builds the curve ourselves from CME SOFR
futures settlement prices (SR3 = 3-month SOFR futures, the standard curve-
building instrument; SR1 = 1-month, useful for the very short end):

    futures price -> implied forward rate -> discount factor per pillar

Requires a Databento API key in the DATABENTO_API_KEY environment variable
(never hardcode it here or pass it in chat/logs). Get one from
https://databento.com -- this project uses paid access already provisioned.
"""
import os
import re
from calendar import monthrange
from datetime import date, timedelta
from io import StringIO

import databento as db
import pandas as pd
import requests

from capitolis_pricers.curves import Curve
from capitolis_pricers.daycount import add_months, year_fraction

DATASET = "GLBX.MDP3"        # CME Globex MDP 3.0
SR3_PARENT = "SR3.FUT"       # 3-month SOFR futures, all live contracts
SR1_PARENT = "SR1.FUT"       # 1-month SOFR futures

# Outright futures only, e.g. "SR3Z6" (product + month code + 1-digit year).
# The "parent" symbology also returns spreads/butterflies (e.g. "SR3Z6-SR3U0",
# "SR3:AB 03Y U6") which must be filtered out before use as curve pillars.
_OUTRIGHT_RE = re.compile(r"^(SR3|SR1)[FGHJKMNQUVXZ]\d$")

# Standard futures month codes -> calendar month number.
_MONTH_CODE = {"F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
               "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12}


def _client():
    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        raise RuntimeError(
            "DATABENTO_API_KEY not set. Set it as an environment variable "
            "(e.g. `setx DATABENTO_API_KEY ...` on Windows, then restart the "
            "shell) -- never pass the key inline in code or chat."
        )
    return db.Historical(key=key)


def fetch_raw(ref_date, parent=SR3_PARENT, lookback_days=5):
    """Pull the most recent daily settlement (close) price for every live
    outright SR3 (or SR1) contract as of `ref_date` (spreads/butterflies
    filtered out).

    Returns a pandas DataFrame with one row per contract: symbol,
    close (settlement price), ts_event.
    """
    client = _client()
    end = ref_date if isinstance(ref_date, date) else date.fromisoformat(str(ref_date))
    start = end - timedelta(days=lookback_days)
    data = client.timeseries.get_range(
        dataset=DATASET,
        symbols=[parent],
        stype_in="parent",
        schema="ohlcv-1d",
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),
    )
    df = data.to_df().reset_index()   # ts_event is the index in the raw response
    if df.empty:
        raise ValueError(f"No {parent} data returned for {start}..{end}")
    df = df[df["symbol"].apply(lambda s: bool(_OUTRIGHT_RE.match(s)))]
    if df.empty:
        raise ValueError(f"No outright contracts matched for {parent} in {start}..{end}")
    # keep the latest bar per contract
    df = df.sort_values("ts_event").groupby("symbol", as_index=False).last()
    return df[["symbol", "close", "ts_event"]]


def clean(raw_df):
    """Convert SOFR futures settlement prices into (contract, implied_rate) pairs.
    CME rate futures quote as `100 - rate`, so rate = 100 - settlement_price
    (as a percentage; divide by 100 for a decimal rate)."""
    out = []
    for _, row in raw_df.iterrows():
        implied_rate = (100.0 - row["close"]) / 100.0
        out.append({"symbol": row["symbol"], "implied_rate": implied_rate,
                     "ts_event": row["ts_event"]})
    return out


def _third_wednesday(year, month):
    """CME IMM date: the third Wednesday of the month."""
    first_weekday, _ = monthrange(year, month)  # first_weekday: Mon=0..Sun=6
    first_wednesday_day = 1 + (2 - first_weekday) % 7
    return date(year, month, first_wednesday_day + 14)


_MAX_PLAUSIBLE_EXPIRY_LAG_DAYS = 400  # see _contract_period docstring


def _contract_period(symbol, ref_date):
    """Map an outright symbol (e.g. 'SR3Z6') to its 3-month reference period
    (start, end), both `date`s. Period runs IMM-date to IMM-date + 3 months.

    The year code is a single digit (last digit of the year) and is
    genuinely ambiguous across decades -- two real, distinct situations
    produce a "same-decade" resolution that lands in the past, and they
    must be told apart, not treated identically:

      (a) A recently-expired serial contract still lingering in the feed
          (e.g. 'SR3Q6' quoted alongside 2026 contracts, expiring within
          the current decade) -- correctly a past date; build_curve()'s
          "already covered" check filters these out, which is the right
          outcome, achieved by NOT wrapping.
      (b) A genuinely far-future contract whose digit wraps to the NEXT
          decade (e.g. 'SR3H0' quoted in 2026 meaning March 2030, not
          March 2020) -- an earlier version of this function never wrapped
          at all, which fixed (a) but silently broke (b): far-dated real
          contracts (digits below ref_date's own decade digit) resolved a
          full decade too early and got wrongly dropped as "expired",
          quietly truncating the curve's usable maturity range.

    Distinguished by how far in the past the same-decade resolution lands:
    within `_MAX_PLAUSIBLE_EXPIRY_LAG_DAYS` (~400 days) is treated as case
    (a) (recently expired -- believable for a contract genuinely still in
    the feed); anything further is case (b) (implausible for a live quote
    -- must mean the next decade), and gets wrapped forward by exactly one
    decade."""
    if not _OUTRIGHT_RE.match(symbol):
        raise ValueError(f"Not an outright SR3/SR1 symbol: {symbol!r}")
    month = _MONTH_CODE[symbol[3]]
    year_digit = int(symbol[4])
    base_decade = ref_date.year - (ref_date.year % 10)

    same_decade_start = _third_wednesday(base_decade + year_digit, month)
    days_in_past = (ref_date - same_decade_start).days
    if days_in_past > _MAX_PLAUSIBLE_EXPIRY_LAG_DAYS:
        start = _third_wednesday(base_decade + 10 + year_digit, month)
    else:
        start = same_decade_start

    end = add_months(start, 3)
    return start, end


def build_curve(ref_date, raw_df=None, basis="ACT/365F"):
    """Bootstrap a capitolis_pricers.curves.Curve from SR3 futures.

    Each contract's implied rate is treated as the (simply-compounded, ACT/360)
    forward SOFR rate over its own 3-month reference period. Discount factors
    are chained sequentially from `ref_date` through each period in turn; any
    gap between `ref_date` and the first contract's start is back-filled flat
    at that first contract's rate. This is a reasonable, standard first-pass
    bootstrap -- not a full OIS-convexity-adjusted curve (a refinement for
    later, not needed to unblock pricing).
    """
    ref_date = ref_date if isinstance(ref_date, date) else date.fromisoformat(str(ref_date))
    if raw_df is None:
        raw_df = fetch_raw(ref_date)
    cleaned = clean(raw_df)

    periods = []
    for row in cleaned:
        start, end = _contract_period(row["symbol"], ref_date)
        periods.append((start, end, row["implied_rate"]))
    periods.sort(key=lambda p: p[0])

    pillar_times, discount_factors = [0.0], [1.0]
    df = 1.0
    prev_end = ref_date
    for start, end, rate in periods:
        if end <= prev_end:
            continue  # already covered / stale contract, skip
        tau = year_fraction(prev_end, end, "ACT/360")
        df = df / (1.0 + rate * tau)               # simply-compounded SOFR convention
        pillar_times.append(year_fraction(ref_date, end, basis))
        discount_factors.append(df)
        prev_end = end

    return Curve(ref_date, pillar_times, discount_factors, basis)


FRED_SOFR_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=SOFR"


def fetch_history(start, end):
    """Daily SOFR *level* history (short-rate proxy, not a full curve) for
    vol/correlation calibration (data/MARKET_DATA.md #5). Free via FRED, no
    API key needed -- separate from the futures-based curve build above,
    which needs today's curve shape, not history of one point on it.
    Returns a pandas Series of decimal rates indexed by date."""
    resp = requests.get(FRED_SOFR_CSV, timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(StringIO(resp.text), parse_dates=["observation_date"])
    df = df.set_index("observation_date")["SOFR"] / 100.0
    return df.loc[str(start):str(end)]
