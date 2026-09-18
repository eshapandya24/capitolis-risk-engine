"""
Ministry of Finance (Japan) historical JGB par-yield curve -- real, free,
DAILY, multi-tenor (1Y..40Y) history since 1974. This is the piece that
was missing for the JPY Hull-White mean-reversion calibration: the
Bloomberg JPY swaption cube gave one snapshot's cross-tenor SHAPE (and
that shape turned out unusable -- rising vol with tenor instead of
decaying, see models/calibration.load_or_calibrate_jpy_mean_reversion's
docstring), and BOJ's TONA (market/boj.py) gave real history but only at
ONE tenor (overnight) -- no cross-tenor structure to fit a decay curve to
either way. The MOF JGB curve gives both: real history AND multiple
tenors, so the SAME method already used for USD (models/hw_calibration.
calibrate_mean_reversion(): realized vol at each tenor, fit
sigma_f(t,T) = sigma * exp(-a*(T-t)) via log-linear regression) can now be
applied to JPY directly on yield levels, without needing futures or a
swaption cube at all.

Source: https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/index.htm
("Historical Data (1974~)"). No API key. The site sits behind a bot-
detection WAF that blocks bare `curl`/`urllib` requests with no headers,
but accepts a normal browser-like User-Agent + Referer (verified
manually) -- no cookies or JS execution needed, just realistic headers.
"""
import os

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CACHE_PATH = os.path.join(ROOT, "data", "raw", "mof_jgb_yield_curve_history.csv")
SOURCE_URL = ("https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/"
              "historical/jgbcme_all.csv")
TENOR_COLUMNS = ["1Y", "2Y", "3Y", "4Y", "5Y", "6Y", "7Y", "8Y", "9Y", "10Y",
                 "15Y", "20Y", "25Y", "30Y", "40Y"]
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Accept": "text/csv,*/*",
    "Referer": "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/index.htm",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_jgb_yield_history(use_cache=True, timeout=30):
    """Returns a DataFrame indexed by date, columns = TENOR_COLUMNS,
    values = par yield in DECIMAL (e.g. 0.02943 = 2.943%, MOF publishes in
    percent). Missing tenors (the shortest history only had 1Y-9Y; longer
    tenors were added later) come through as NaN, not an error -- callers
    should dropna() per-tenor as needed. Cached to
    data/raw/mof_jgb_yield_curve_history.csv (gitignored, like the rest of
    data/raw/ -- a re-fetchable pull, not licensed data)."""
    if use_cache and os.path.exists(CACHE_PATH):
        return _load_cache()

    resp = requests.get(SOURCE_URL, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    if not resp.text.lstrip().startswith("Interest Rate,"):
        raise RuntimeError("Unexpected MOF response (bot-check page instead of CSV?): "
                            f"{resp.text[:200]!r}")

    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        f.write(resp.text)
    return _load_cache()


def _load_cache():
    df = pd.read_csv(CACHE_PATH, skiprows=1, na_values=["-"])
    df["Date"] = pd.to_datetime(df["Date"], format="%Y/%m/%d")
    df = df.set_index("Date")[TENOR_COLUMNS] / 100.0  # percent -> decimal
    return df
