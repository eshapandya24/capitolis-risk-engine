"""
MPOR (Margin Period of Risk)-shifted exposure, compared side-by-side
against the plain (uncollateralized-style) exposure the production engine
uses today -- see src/risk_engine/exposure/collateral.py's module
docstring for the method.

The real book is treated as UNCOLLATERALIZED (no CSA terms anywhere in
trade_data/), so this is explicitly a HYPOTHETICAL illustration -- "if a
CSA with a given threshold existed, here's what MPOR-shifted PFE would
look like" -- not a claim about the actual current exposure, which remains
what scripts/run_simulation.py reports.

    python scripts/run_mpor_comparison.py [--scenarios N] [--mpor-days D] [--threshold T]
"""
import argparse
import json
import os
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TD = os.path.join(ROOT, "trade_data")
U = os.path.join(TD, "underlyings")


def load_trades():
    from capitolis_pricers.underlyings_loader import load_equities, load_bonds
    from capitolis_pricers.trade_loader import load_equity_trs, load_bond_forward, load_bond_trs
    baskets = load_equities(os.path.join(U, "equities.csv"))
    bonds = load_bonds(os.path.join(U, "bonds.csv"))
    trades = {}
    trades.update(load_equity_trs(os.path.join(TD, "equity_trs.csv"), baskets))
    trades.update(load_bond_forward(os.path.join(TD, "bond_forward.csv"), bonds))
    trades.update(load_bond_trs(os.path.join(TD, "bond_trs.csv"), bonds))
    return trades


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", type=int, default=1000)
    parser.add_argument("--mpor-days", type=int, default=10,
                         help="BUSINESS days; ISDA SIMM / Basel standard for margined bilateral OTC derivatives")
    parser.add_argument("--threshold", type=float, default=0.0,
                         help="CSA threshold, USD. 0 = full variation margin (isolates the pure "
                              "MPOR effect); a real CSA's threshold would come from Capitolis's "
                              "actual margin agreements, which we don't have -- this is illustrative")
    parser.add_argument("--curve-date", default="2026-08-28")
    args = parser.parse_args()

    from risk_engine.models.calibration import build_calibration
    from risk_engine.simulation.engine import SimulationEngine
    from risk_engine.exposure.collateral import mpor_vs_uncollateralized_comparison

    ref_date = date.fromisoformat(args.curve_date)
    calib = build_calibration(ref_date)
    trades = load_trades()

    print(f"\n*** HYPOTHETICAL comparison -- the real book has no CSA terms; this "
          f"illustrates what MPOR-shifted exposure would look like under an assumed "
          f"threshold=${args.threshold:,.0f} CSA, MPOR={args.mpor_days} days ***\n")

    eng = SimulationEngine(calib, trades, method="latin_hypercube", n_scenarios=args.scenarios,
                            seed=42, mpor_days=args.mpor_days)
    print(f"Time grid: {len(eng.dates)} nodes ({len(eng.node_map)} reporting + look-ahead), "
          f"{eng.dates[0]} -> {eng.dates[-1]}")

    paths = eng.simulate_paths()
    if args.scenarios < 200:
        trade_ids, npv = eng.reprice_all(paths)
    else:
        from risk_engine.simulation.parallel import reprice_all_parallel
        trade_ids, npv = reprice_all_parallel(eng, paths)

    comparison = mpor_vs_uncollateralized_comparison(
        trade_ids, eng.trade_counterparty, npv, eng.node_map, eng.dates, threshold=args.threshold)

    print(f"\n{'Counterparty':14s} {'Uncollateralized MPE':>22s} {'MPOR-shifted MPE':>18s} {'Reduction':>12s}")
    for cpty in comparison["uncollateralized"]:
        u_mpe = comparison["uncollateralized"][cpty]["MPE"]
        m_mpe = comparison["mpor_shifted"][cpty]["MPE"]
        reduction = (1 - m_mpe / u_mpe) * 100 if u_mpe > 0 else 0.0
        print(f"{cpty:14s} {u_mpe:22,.0f} {m_mpe:18,.0f} {reduction:11.1f}%")

    out = {
        "ref_date": str(ref_date), "n_scenarios": args.scenarios,
        "mpor_days": args.mpor_days, "threshold": args.threshold,
        "note": "HYPOTHETICAL -- real book is uncollateralized, no CSA data available",
        "dates": [str(d) for d in comparison["dates"]],
        "uncollateralized": {c: {"EE": v["EE"].tolist(), "PFE": v["PFE"].tolist(), "MPE": v["MPE"]}
                              for c, v in comparison["uncollateralized"].items()},
        "mpor_shifted": {c: {"EE": v["EE"].tolist(), "PFE": v["PFE"].tolist(), "MPE": v["MPE"]}
                         for c, v in comparison["mpor_shifted"].items()},
    }
    out_path = os.path.join(ROOT, "data", "processed", f"mpor_comparison_{ref_date}.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
