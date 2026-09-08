"""
Current Exposure (CE) — a snapshot, not simulated exposure.

This is NOT Expected Exposure / Potential Future Exposure / Maximum PFE.
Those require the Monte Carlo simulation engine (src/risk_engine/simulation/,
src/risk_engine/exposure/), which is not implemented yet -- this script only
uses today's real MTMs, no future scenarios.

Current Exposure = what we'd lose today if a counterparty defaulted right
now, which is why exposure is asymmetric: a trade that's a loss to us (MTM
< 0) carries zero credit exposure (we'd owe them, not the other way around)
-- only positive MTM is actually at risk.

  - Trade-level (gross) CE  = max(NPV, 0)
  - Counterparty-level (netted) CE = max(sum of NPVs in that netting set, 0)
    -- assumes a legally enforceable netting agreement per counterparty,
    which is exactly what the `counterparty` field on every trade encodes.

Netted CE <= sum of gross CEs always (netting can only reduce exposure,
never increase it) -- a useful sanity check on the output.

    python scripts/calculate_current_exposure.py
"""
import json
import os
from collections import defaultdict
from datetime import date

from risk_engine.market.sofr import fetch_raw as fetch_sofr_raw, build_curve
from scripts.price_full_book_real_data import build_real_market, DEFAULT_CURVE_DATE

from capitolis_pricers.underlyings_loader import load_equities, load_bonds
from capitolis_pricers.trade_loader import (
    load_equity_trs, load_bond_forward, load_bond_trs)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TD = os.path.join(ROOT, "trade_data")
U = os.path.join(TD, "underlyings")


def main():
    market, missing = build_real_market()

    baskets = load_equities(os.path.join(U, "equities.csv"))
    bonds = load_bonds(os.path.join(U, "bonds.csv"))
    trades = {}
    trades.update(load_equity_trs(os.path.join(TD, "equity_trs.csv"), baskets))
    trades.update(load_bond_forward(os.path.join(TD, "bond_forward.csv"), bonds))
    trades.update(load_bond_trs(os.path.join(TD, "bond_trs.csv"), bonds))

    # counterparty lookup per trade_id (loaders don't expose it on the priced
    # object, so re-read the CSVs directly)
    import csv
    cpty_by_trade = {}
    for fname in ("equity_trs.csv", "bond_forward.csv", "bond_trs.csv"):
        with open(os.path.join(TD, fname), newline="") as f:
            for row in csv.DictReader(f):
                cpty_by_trade[row["trade_id"]] = row["counterparty"]

    npvs = {}
    for tid, p in trades.items():
        npvs[tid] = p.npv(market, reporting=True)

    print(f"CURRENT EXPOSURE  (ref {market.ref_date}, NOT simulated -- see docstring)\n")
    print(f"{'Trade':12s} {'Counterparty':6s} {'NPV (MTM)':>16s} {'Gross CE':>16s}")
    gross_ce_total = 0.0
    by_cpty = defaultdict(list)
    for tid in sorted(npvs, key=lambda t: cpty_by_trade[t]):
        npv = npvs[tid]
        cpty = cpty_by_trade[tid]
        ce = max(npv, 0.0)
        gross_ce_total += ce
        by_cpty[cpty].append(npv)
        print(f"{tid:12s} {cpty:6s} {npv:16,.2f} {ce:16,.2f}")

    print(f"\n{'Sum':12s} {'':6s} {sum(npvs.values()):16,.2f} {gross_ce_total:16,.2f}")

    print(f"\nNETTED CURRENT EXPOSURE BY COUNTERPARTY (assumes enforceable netting)\n")
    print(f"{'Counterparty':14s} {'# Trades':>9s} {'Net MTM':>16s} {'Netted CE':>16s}")
    netted_total = 0.0
    results = {}
    for cpty, npv_list in sorted(by_cpty.items()):
        net_mtm = sum(npv_list)
        netted_ce = max(net_mtm, 0.0)
        netted_total += netted_ce
        results[cpty] = {"n_trades": len(npv_list), "net_mtm": net_mtm, "netted_ce": netted_ce}
        print(f"{cpty:14s} {len(npv_list):9d} {net_mtm:16,.2f} {netted_ce:16,.2f}")

    print(f"\n{'TOTAL':14s} {'':9s} {sum(npvs.values()):16,.2f} {netted_total:16,.2f}")
    print(f"\nGross CE (no netting):    {gross_ce_total:16,.2f}")
    print(f"Netted CE (by cpty):      {netted_total:16,.2f}")
    print(f"Netting benefit:          {gross_ce_total - netted_total:16,.2f}  "
          f"({(1 - netted_total/gross_ce_total)*100:.1f}% reduction)")
    assert netted_total <= gross_ce_total + 1e-6, "netting increased exposure -- bug!"

    out = {
        "ref_date": str(market.ref_date), "as_of_run": str(date.today()),
        "trade_npv": npvs, "trade_counterparty": cpty_by_trade,
        "gross_ce_total": gross_ce_total,
        "netted_ce_by_counterparty": results,
        "netted_ce_total": netted_total,
    }
    out_path = os.path.join(ROOT, "data", "processed", f"current_exposure_{market.ref_date}.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
