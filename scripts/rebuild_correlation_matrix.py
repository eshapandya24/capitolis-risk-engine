"""
Rebuild data/processed/correlation_matrix.csv with the USD rate factor's
daily shocks measured on the 10-year Treasury CMT yield (FRED DGS10) instead
of the overnight SOFR fixing.

The Hull-White factor drives the whole USD curve and is now calibrated to
long-end realised vol (market/treasury.py), so its correlations with equities
and USDJPY should use a yield that responds to market news day by day; SOFR
fixings move in steps on Fed days and correlate with nothing. Equity and FX
histories are the cached 3-year files from pull_historical_data.py.

    python scripts/rebuild_correlation_matrix.py
"""
import os
import shutil

import pandas as pd

from risk_engine.market.correlations import build_correlation_matrix, is_positive_semidefinite
from risk_engine.market.treasury import load_cmt_history

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, "data", "processed")


def main():
    eq = pd.read_csv(os.path.join(P, "history_equities.csv"), index_col=0, parse_dates=True)
    fx = pd.read_csv(os.path.join(P, "history_usdjpy.csv"), index_col=0, parse_dates=True)["USDJPY"]
    y10 = load_cmt_history()["DGS10"]
    old_path = os.path.join(P, "correlation_matrix.csv")
    old = pd.read_csv(old_path, index_col=0)
    keep = os.path.join(P, "correlation_matrix_sofr.csv")
    if not os.path.exists(keep):
        shutil.copy(old_path, keep)
    new = build_correlation_matrix(eq, fx, y10)
    ok, min_eig = is_positive_semidefinite(new)
    new = new.loc[old.index, old.columns]
    block = [c for c in old.columns if c != "RATE_USD"]
    print(f"PSD: {ok} (min eigenvalue {min_eig:.2e}); max change in the equity/FX block: "
          f"{(new.loc[block, block] - old.loc[block, block]).abs().values.max():.3f}")
    r_old, r_new = old["RATE_USD"].drop("RATE_USD"), new["RATE_USD"].drop("RATE_USD")
    print(f"RATE_USD correlations: SOFR-based range {r_old.min():+.3f}..{r_old.max():+.3f}; "
          f"10y-yield-based {r_new.min():+.3f}..{r_new.max():+.3f}")
    new.to_csv(old_path)
    print("wrote", old_path)


if __name__ == "__main__":
    main()
