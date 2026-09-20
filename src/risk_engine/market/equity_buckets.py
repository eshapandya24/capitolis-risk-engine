"""
SA-CVA equity buckets (Basel MAR50.70, Table 11) for the 37 reference
equities: size (market cap >= USD 2bn = large), region (advanced vs
emerging economy) and sector, from yfinance. Cached to
data/raw/equity_sa_cva_buckets.json. Names whose data cannot be fetched
fall into bucket 11 (other sector), the conservative default (RW 70%).
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CACHE = os.path.join(ROOT, "data", "raw", "equity_sa_cva_buckets.json")

# yfinance sector -> Basel sector group (A..D as in Table 11's four sector rows)
SECTOR_GROUP = {"Consumer Cyclical": "A", "Consumer Defensive": "A", "Healthcare": "A", "Utilities": "A",
                "Communication Services": "B", "Industrials": "B",
                "Basic Materials": "C", "Energy": "C",
                "Financial Services": "D", "Real Estate": "D", "Technology": "D"}
ADVANCED = {"United States", "Canada", "Mexico", "United Kingdom", "Norway", "Sweden", "Denmark", "Switzerland",
            "Japan", "Australia", "New Zealand", "Singapore", "Hong Kong", "Netherlands", "Germany", "France",
            "Italy", "Spain", "Ireland", "Belgium", "Finland", "Austria", "Portugal", "Luxembourg", "Bermuda"}
# Bucket numbers: large emerging 1-4, large advanced 5-8, small emerging 9, small advanced 10, other 11
RISK_WEIGHT = {1: .55, 2: .60, 3: .45, 4: .55, 5: .30, 6: .35, 7: .40, 8: .50, 9: .70, 10: .50, 11: .70}
VEGA_RW_LARGE, VEGA_RW_OTHER = 0.78, 1.00


def bucket_for(sector, country, mcap):
    if sector not in SECTOR_GROUP or not country or not mcap:
        return 11
    g = "ABCD".index(SECTOR_GROUP[sector])
    adv = country in ADVANCED
    if mcap >= 2e9:
        return (5 if adv else 1) + g
    return 10 if adv else 9


def load_equity_buckets(isin_to_ticker, use_cache=True):
    if use_cache and os.path.exists(CACHE):
        return {k: v for k, v in json.load(open(CACHE)).items()}
    import yfinance as yf
    out = {}
    for isin, tk in isin_to_ticker.items():
        try:
            info = yf.Ticker(tk if tk.endswith(".T") else tk.replace(".", "-")).info
            out[isin] = {"ticker": tk, "sector": info.get("sector"), "country": info.get("country"),
                         "market_cap": info.get("marketCap")}
        except Exception:
            out[isin] = {"ticker": tk, "sector": None, "country": None, "market_cap": None}
        out[isin]["bucket"] = bucket_for(out[isin]["sector"], out[isin]["country"], out[isin]["market_cap"])
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump(out, open(CACHE, "w"), indent=1)
    return out
