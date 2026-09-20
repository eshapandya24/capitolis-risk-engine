"""
Proxy credit spreads from public bond-index data (FRED / ICE BofA option-
adjusted spreads). No CDS data is available for Capitolis' counterparties,
so counterparty credit spreads are proxied from the bond market by credit
rating, which is what Basel MAR50.32(3) prescribes for illiquid names
(a proxy that discriminates on credit quality, industry and region; here
credit quality only, because sector and region are not known).

Term structure: the rating-level OAS is a single number (the index's
average maturity). A maturity shape is taken from the ICE BofA US
Corporate index OAS by maturity bucket (1-3y, 3-5y, 5-7y, 7-10y), scaled
to the overall corporate OAS, and applied to every rating. Disclosed
simplification: the shape is not rating-specific.
"""
import os
from io import StringIO

import numpy as np
import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CACHE = os.path.join(ROOT, "data", "raw", "fred_credit_oas.csv")
RATING_SERIES = {"AAA": "BAMLC0A1CAAA", "AA": "BAMLC0A2CAA", "A": "BAMLC0A3CA", "BBB": "BAMLC0A4CBBB",
                 "BB": "BAMLH0A1HYBB", "B": "BAMLH0A2HYB"}
SHAPE_SERIES = {"ALL": "BAMLC0A0CM", 2.0: "BAMLC1A0C13Y", 4.0: "BAMLC2A0C35Y", 6.0: "BAMLC3A0C57Y", 8.5: "BAMLC4A0C710Y"}
INVESTMENT_GRADE = {"AAA", "AA", "A", "BBB"}


def _fetch(series_id):
    r = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}", timeout=30)
    r.raise_for_status()
    df = pd.read_csv(StringIO(r.text), na_values=["."])
    df.columns = ["date", "v"]
    df["date"] = pd.to_datetime(df["date"])
    return df.dropna().set_index("date")["v"] / 100.0  # percent -> decimal


def load_oas(use_cache=True):
    """DataFrame of daily OAS (decimal) for every series used here."""
    if use_cache and os.path.exists(CACHE):
        return pd.read_csv(CACHE, index_col=0, parse_dates=True)
    cols = {**{k: v for k, v in RATING_SERIES.items()}, **{str(k): v for k, v in SHAPE_SERIES.items()}}
    df = pd.DataFrame({name: _fetch(sid) for name, sid in cols.items()})
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    df.to_csv(CACHE)
    return df


def rating_spread_curve(rating, ref_date, tenors=(0.5, 1, 3, 5, 10), use_cache=True):
    """Proxy credit spread curve (decimal, absolute) at `tenors` for a
    rating bucket, as of ref_date (last observation on or before it)."""
    if rating not in RATING_SERIES:
        raise ValueError(f"rating must be one of {list(RATING_SERIES)}")
    df = load_oas(use_cache)
    row = df[df.index <= pd.Timestamp(ref_date)].iloc[-1]
    base = float(row[rating])
    mids = [2.0, 4.0, 6.0, 8.5]
    shape = np.array([row[str(m)] / row["ALL"] for m in mids])
    ratio = np.interp(tenors, mids, shape)  # flat extrapolation outside 2-8.5y
    return np.array(tenors, dtype=float), base * ratio
