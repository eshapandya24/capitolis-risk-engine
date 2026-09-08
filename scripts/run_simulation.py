"""
End-to-end Monte Carlo CCR simulation: calibrate models from real market
data, simulate correlated paths, reprice the full 16-trade book at every
(scenario, time-node), and aggregate into EE / PFE / MPE profiles per
counterparty and for the book.

Validates itself on every run: EE(t=0) (no randomness yet) must match a
direct Current Exposure calculation computed from the EXACT SAME calibrated
market snapshot (not a separately-cached file from a possibly-earlier run,
which can go stale against real intervening market moves -- found exactly
this failure mode once: a ~12hr-old cached comparison file showed 7-15%
"discrepancies" that were entirely real overnight price moves, not a bug;
computing the comparison from the same in-memory snapshot removes that
whole failure mode, since both numbers are now built from identical data).

Heavy imports (calibration, which pulls in databento/yfinance) are done
INSIDE main(), not at module top-level -- required so Windows multiprocessing
workers (spawn re-executes this file's top-level imports) don't each re-pay
that cost; see src/risk_engine/simulation/parallel.py's docstring.

    python scripts/run_simulation.py [--scenarios N] [--serial]
"""
import argparse
import json
import os
import time
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
    parser.add_argument("--scenarios", type=int, default=1000,
                         help="Default 1000: empirically crosses below 0.5% relative standard "
                              "error on portfolio PFE95 in ~73s (8 cores) -- see "
                              "docs/notes/convergence_study.md. Use 2000-3000 for final/reporting "
                              "runs (~0.1-0.3% error, ~2-3 min); beyond ~4000 the dominant error "
                              "is model uncertainty (Hull-White mean reversion, vol proxy), not "
                              "Monte Carlo noise, so more paths stop being the limiting factor.")
    parser.add_argument("--method", default="latin_hypercube",
                         help="Default is latin_hypercube -- validated as the best speed/accuracy "
                              "tradeoff on both a controlled option test and the real 39-factor "
                              "engine, see docs/notes/simulation_engine_and_variance_reduction.md")
    parser.add_argument("--confidence", type=float, default=0.95)
    parser.add_argument("--serial", action="store_true", help="Force serial repricing (skip multiprocessing)")
    parser.add_argument("--curve-date", default="2026-08-28",
                         help="Databento's plan has a short data-availability lag; pin to the last known-good date")
    args = parser.parse_args()

    from risk_engine.models.calibration import build_calibration
    from risk_engine.simulation.engine import SimulationEngine
    from risk_engine.exposure.aggregate import build_profiles
    from capitolis_pricers.market import MarketState
    from capitolis_pricers.curves import FxCurve

    ref_date = date.fromisoformat(args.curve_date)
    calib = build_calibration(ref_date)
    trades = load_trades()

    print(f"\nSimulating {args.scenarios} scenarios, method={args.method}...")
    eng = SimulationEngine(calib, trades, method=args.method, n_scenarios=args.scenarios, seed=42)
    print(f"Time grid: {len(eng.dates)} nodes, {eng.dates[0]} -> {eng.dates[-1]}")

    t0 = time.perf_counter()
    paths = eng.simulate_paths()
    t1 = time.perf_counter()
    print(f"simulate_paths: {t1 - t0:.2f}s")

    t0 = time.perf_counter()
    if args.serial or args.scenarios < 200:
        trade_ids, npv = eng.reprice_all(paths)
    else:
        from risk_engine.simulation.parallel import reprice_all_parallel
        trade_ids, npv = reprice_all_parallel(eng, paths)
    t1 = time.perf_counter()
    print(f"reprice ({'serial' if args.serial else 'parallel'}): {t1 - t0:.2f}s "
          f"({(t1 - t0) / args.scenarios * 1000:.2f} ms/scenario)")

    profiles = build_profiles(trade_ids, eng.trade_counterparty, npv, eng.dates, confidence=args.confidence)

    print(f"\nEE(t=0) by counterparty (cross-check vs Current Exposure):")
    for cpty, p in profiles.items():
        print(f"  {cpty:16s} EE(0)={p['EE'][0]:15,.2f}  PFE{int(args.confidence*100)}(0)={p['PFE'][0]:15,.2f}  MPE={p['MPE']:15,.2f}")

    print(f"\nInternal consistency check (t=0 is deterministic -- EE(0) must match a direct "
          f"reprice off the SAME calibrated snapshot, no live-data staleness possible):")
    direct_npv = {}
    # Use the SAME curve object the engine itself uses at t=0 (the exact
    # analytic FastNodeCurve, not the original fixed-pillar interpolated
    # Curve) -- those two differ by a documented, tiny (~2e-5 discount
    # factor) interpolation gap, which would otherwise show up here as a
    # false ~0.02-0.03% "discrepancy" that isn't actually a bug.
    r0 = calib["hw"].short_rate0()
    t0_curve = calib["hw"].fast_node_curve(calib["ref_date"], 0.0, r0)
    market_t0 = MarketState(
        ref_date=calib["ref_date"], reporting_ccy="USD",
        discount_curves={"USD": t0_curve}, equity_spots=calib["equity_spots"],
        equity_dividend_rates=calib["dividends"],
        fx_curves={("USD", "JPY"): FxCurve("USD", "JPY", calib["fx_spot"], t0_curve)},
    )
    for tid, trade in trades.items():
        direct_npv[tid] = trade.npv(market_t0, reporting=True)
    direct_by_cpty = {}
    for tid, npv in direct_npv.items():
        direct_by_cpty.setdefault(trades[tid].counterparty, 0.0)
        direct_by_cpty[trades[tid].counterparty] += npv
    for cpty, net_mtm in sorted(direct_by_cpty.items()):
        direct_ce = max(net_mtm, 0.0)
        sim_ee0 = profiles[cpty]["EE"][0]
        pct_diff = abs(sim_ee0 - direct_ce) / max(abs(direct_ce), 1.0) * 100
        flag = "OK" if pct_diff < 0.5 else "BUG -- investigate (should match to float precision)"
        print(f"  {cpty:16s} sim EE(0)={sim_ee0:15,.2f}  direct CE={direct_ce:15,.2f}  diff={pct_diff:.4f}%  {flag}")

    print(f"\nFull portfolio EE/PFE{int(args.confidence*100)} profile:")
    port = profiles["__portfolio__"]
    for i, d in enumerate(eng.dates):
        print(f"  {d}  EE={port['EE'][i]:15,.2f}  PFE={port['PFE'][i]:15,.2f}")
    print(f"\nPortfolio MPE: {port['MPE']:,.2f}")

    out = {
        "ref_date": str(ref_date), "n_scenarios": args.scenarios, "method": args.method,
        "confidence": args.confidence, "dates": [str(d) for d in eng.dates],
        "profiles": {cpty: {"EE": p["EE"].tolist(), "PFE": p["PFE"].tolist(), "MPE": p["MPE"]}
                     for cpty, p in profiles.items()},
    }
    out_path = os.path.join(ROOT, "data", "processed", f"exposure_profiles_{ref_date}_{args.method}_{args.scenarios}.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
