"""
Extended (2007-today) daily price history for the 37 equities and USDJPY,
public yfinance data, used ONLY to widen the pool of historical stress
windows (risk_engine/stress/scenarios.py) back through the 2008 financial
crisis and other pre-2014 episodes. data/raw/backtest_prices.csv (2014-today,
used for backtesting the exposure model itself) is left untouched.

Names that don't trade back to 2008 (recent IPOs) simply have NaN there;
scenarios.py already falls back to the cross-sectional median return for a
name with no data in a given window, the same convention used for COVID.

    python scripts/pull_extended_history.py

Writes data/raw/backtest_prices_ext.csv.
"""
import csv
import os
from datetime import date

import pandas as pd

from risk_engine.market.equities import fetch_history
from risk_engine.market.fx import fetch_history as fetch_fx_history

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TD = os.path.join(ROOT, "trade_data")
U = os.path.join(TD, "underlyings")
OUT = os.path.join(ROOT, "data", "raw", "backtest_prices_ext.csv")
START = date(2007, 1, 1)


def _isin_to_ticker():
    mapping = {}
    with open(os.path.join(U, "equities.csv"), newline="") as f:
        for row in csv.DictReader(f):
            if row["isin"]:
                mapping[row["isin"]] = row["ticker"]
    return mapping


def main():
    end = date.today()
    isin_to_ticker = _isin_to_ticker()
    print(f"Pulling {START} .. {end} for {len(isin_to_ticker)} names + USDJPY (yfinance, public)...")
    hist = fetch_history(isin_to_ticker, START, end)
    have_2008 = sum(1 for s in hist.values() if len(s[s.index.tz_localize(None) < pd.Timestamp("2009-01-01")]) > 0)
    print(f"  {len(hist)}/{len(isin_to_ticker)} names returned data; {have_2008} have data before 2009")
    fx = fetch_fx_history(START, end)
    df = pd.DataFrame({isin: s for isin, s in hist.items()})
    df.index = df.index.tz_localize(None).normalize()
    fx.index = fx.index.tz_localize(None).normalize()
    fx = fx[~fx.index.duplicated(keep="last")]
    df = df[~df.index.duplicated(keep="last")]
    df["FX_USDJPY"] = fx.reindex(df.index)
    df.index.name = "date"
    df = df.sort_index()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    df.to_csv(OUT)
    print("wrote", OUT, df.shape)


if __name__ == "__main__":
    main()
