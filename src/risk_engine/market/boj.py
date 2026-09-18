"""
Bank of Japan Time-Series Data Search API -- real, free, historical TONA
(Tokyo Overnight Average Rate, the JPY OIS reference rate) daily history,
1998-01-05 to present.

Why this exists: the Bloomberg export (market/bloomberg.py) only has a
SINGLE JPY OIS snapshot (2026-08-31) -- no history -- which is why the JPY
Hull-White factor's `sigma` (models/calibration.build_jpy_hull_white)
originally had to fall back to the swaption-implied fit's vol LEVEL rather
than a true realized-vol estimate (the way RATE_USD's sigma is computed in
vols.py from real SOFR history). TONA is overnight-only, not a full curve,
but that's exactly the input a short-rate-level realized-vol estimate
needs -- the same role SOFR spot vol plays for the USD factor.

No API key needed -- a plain public HTTPS GET. Series code STRDCLUCON =
"Call Rate, Uncollateralized Overnight, Average (Daily)", DB=FM01. Manual:
https://www.stat-search.boj.or.jp/info/api_manual_en.pdf

This real history includes JPY's genuine negative-rate periods -- both the
2003 near-zero/negative ZIRP dip and the 2016-2024 NIRP era (BOJ's -0.10%
policy rate) -- concrete evidence for the "JPY needs a negative-rate-
capable model" premise this whole rates.py/calibration.py effort is built
on, not just a hypothetical.
"""
import csv
import gzip
import os
import urllib.request

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CACHE_PATH = os.path.join(ROOT, "data", "raw", "boj_tona_history.csv")
API_URL = ("https://www.stat-search.boj.or.jp/api/v1/getDataCode"
           "?format=csv&lang=en&db=FM01&code=STRDCLUCON&startDate={start}&endDate={end}")
SERIES_CODE = "STRDCLUCON"


def _fetch_from_api(start, end, timeout):
    url = API_URL.format(start=start, end=end)
    req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        encoding = resp.headers.get("Content-Encoding", "")
    if encoding == "gzip" or raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    text = raw.decode("utf-8")

    lines = text.splitlines()
    if lines and lines[0].startswith("STATUS,4"):
        raise RuntimeError(f"BOJ API returned an error: {text[:300]}")
    header_idx = next(i for i, l in enumerate(lines) if l.startswith("SERIES_CODE,"))
    reader = csv.DictReader(lines[header_idx:])

    dates, values = [], []
    for row in reader:
        v = row["VALUES"]
        if v in (None, "", "null"):
            continue  # weekends/holidays: BOJ reports "null", not a gap to fill
        dates.append(row["SURVEY_DATES"])
        values.append(float(v) / 100.0)  # percent per annum -> decimal

    series = pd.Series(values, index=pd.to_datetime(dates, format="%Y%m%d"), name="TONA")
    return series.sort_index()


def fetch_tona_history(start="199801", end="203001", use_cache=True, timeout=30):
    """Returns a pandas Series of TONA (decimal, e.g. 0.001 = 0.10%) indexed
    by date -- real daily BOJ data, including the genuine ZIRP (2003) and
    NIRP (2016-2024) negative-rate periods. Cached to
    data/raw/boj_tona_history.csv (gitignored like the rest of data/raw/ --
    a re-fetchable pull, not licensed data)."""
    if use_cache and os.path.exists(CACHE_PATH):
        df = pd.read_csv(CACHE_PATH, index_col=0, parse_dates=True)
        return df["TONA"]

    series = _fetch_from_api(start, end, timeout)
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    series.to_csv(CACHE_PATH, header=True)
    return series


def jpy_realized_rate_vol(ref_date, lookback_years=3, use_cache=True):
    """Annualized normal (absolute) realized vol of TONA over the
    `lookback_years` window ending at ref_date -- mirrors vols.py's
    rate_vol() calc for RATE_USD exactly (same simple-differences-of-level
    method, appropriate near/below zero where log returns aren't
    meaningful), applied to real JPY data now that TONA history is
    available instead of only a single Bloomberg snapshot."""
    from .vols import rate_vol
    series = fetch_tona_history(use_cache=use_cache)
    end = pd.Timestamp(ref_date)
    start = end - pd.DateOffset(years=lookback_years)
    window = series[(series.index > start) & (series.index <= end)]
    if len(window) < 30:
        raise ValueError(f"Not enough TONA history in the {lookback_years}y window "
                          f"ending {ref_date} ({len(window)} points)")
    return rate_vol(window)
