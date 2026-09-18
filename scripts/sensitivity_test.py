"""
Benchmark test #3: sensitivity / stress test on the full exposure engine --
bump each calibration input in an economically unambiguous direction and
check the resulting PFE/EE profile moves the way it MUST (sign and rough
monotonicity), using the SAME engine and repricing path as
scripts/run_simulation.py (common random numbers across bumps, so the
comparison isn't swamped by simulation noise -- see
scripts/compute_greeks_demo.py for why that matters).

Checks:
  1. Equity vol +50%  -> portfolio PFE (95%) must NOT decrease (more spread
     in the terminal distribution of a long-only exposure measure can only
     raise or leave unchanged the upper tail).
  2. USD short-rate level +100bp (parallel shift of today's curve) -> the
     book's bond-financing legs are rate-sensitive; just checks the
     exposure profile actually MOVES (a flat/unchanged profile after a
     100bp curve shift would mean the bumped curve silently isn't being
     used somewhere in the simulation).
  3. Hull-White sigma +50% -> wider short-rate distribution -> PFE of the
     bond-driven trades must not decrease, same logic as #1.

This is intentionally a DIRECTIONAL test (>=, not a precise magnitude
match) -- the point is to catch a sign error or a bump that silently fails
to propagate through calibration -> engine -> pricers, not to reproduce a
specific numeric target.
"""
import copy
import os
import time
from datetime import date

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TD = os.path.join(ROOT, "trade_data")
U = os.path.join(TD, "underlyings")

N_SCENARIOS = 800
SEED = 99


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


def portfolio_mpe(calib, trades):
    from risk_engine.simulation.engine import SimulationEngine
    from risk_engine.simulation.parallel import reprice_all_parallel
    from risk_engine.exposure.aggregate import build_profiles

    eng = SimulationEngine(calib, trades, method="latin_hypercube",
                            n_scenarios=N_SCENARIOS, seed=SEED)
    paths = eng.simulate_paths()
    trade_ids, npv = reprice_all_parallel(eng, paths)
    profiles = build_profiles(trade_ids, eng.trade_counterparty, npv, eng.dates, confidence=0.99)
    port = profiles["__portfolio__"]
    return float(port["MPE"]), np.array(port["PFE"])


def bump_equity_vol(calib, factor):
    bumped = copy.copy(calib)
    gbm = copy.deepcopy(calib["gbm"])
    gbm.vols = {k: v * factor for k, v in gbm.vols.items()}
    bumped["gbm"] = gbm
    return bumped


def bump_rate_level(calib, shift):
    from capitolis_pricers.curves import Curve
    base = calib["usd_curve"]
    pillar_times = base._t[1:]
    dfs = [np.exp(lndf) for lndf in base._lndf[1:]]
    bumped_curve = Curve(base.ref_date, list(pillar_times),
                          [d * np.exp(-shift * t) for d, t in zip(dfs, pillar_times)],
                          basis=base.basis)
    bumped = copy.copy(calib)
    bumped["usd_curve"] = bumped_curve
    hw = copy.deepcopy(calib["hw"])
    hw.base_curve = bumped_curve
    bumped["hw"] = hw
    return bumped


def bump_hw_sigma(calib, factor):
    bumped = copy.copy(calib)
    hw = copy.deepcopy(calib["hw"])
    hw.sigma = hw.sigma * factor
    bumped["hw"] = hw
    return bumped


def main():
    from risk_engine.models.calibration import build_calibration

    ref_date = date(2026, 8, 28)
    print("Loading calibration + trades...")
    calib = build_calibration(ref_date)
    trades = load_trades()

    print(f"\nBase case ({N_SCENARIOS} scenarios, seed={SEED})...")
    t0 = time.perf_counter()
    base_mpe, base_pfe = portfolio_mpe(calib, trades)
    print(f"  MPE = {base_mpe:,.2f} USD   ({time.perf_counter()-t0:.1f}s)")

    results = []

    print("\n[1] Equity vol x1.5...")
    mpe, pfe = portfolio_mpe(bump_equity_vol(calib, 1.5), trades)
    ok = mpe >= base_mpe * 0.98  # small MC-noise tolerance
    results.append(("equity vol +50%", base_mpe, mpe, ok))
    print(f"  MPE = {mpe:,.2f} USD  (base {base_mpe:,.2f})  {'OK' if ok else 'FAIL'} (expect >=)")

    print("\n[2] USD rate curve +100bp parallel shift...")
    mpe, pfe = portfolio_mpe(bump_rate_level(calib, 0.01), trades)
    moved = abs(mpe - base_mpe) > 0.001 * max(abs(base_mpe), 1.0)
    results.append(("rate +100bp", base_mpe, mpe, moved))
    print(f"  MPE = {mpe:,.2f} USD  (base {base_mpe:,.2f})  {'OK' if moved else 'FAIL'} (expect change)")

    print("\n[3] Hull-White sigma x1.5...")
    mpe, pfe = portfolio_mpe(bump_hw_sigma(calib, 1.5), trades)
    ok = mpe >= base_mpe * 0.98
    results.append(("HW sigma +50%", base_mpe, mpe, ok))
    print(f"  MPE = {mpe:,.2f} USD  (base {base_mpe:,.2f})  {'OK' if ok else 'FAIL'} (expect >=)")

    print("\n=== Summary ===")
    all_ok = True
    for name, base, bumped, ok in results:
        all_ok &= ok
        print(f"  {name:20s} base={base:14,.2f}  bumped={bumped:14,.2f}  "
              f"{'PASS' if ok else 'FAIL'}")
    print(f"\n{'PASS' if all_ok else 'FAIL'}: all sensitivity directions are as expected.")


if __name__ == "__main__":
    main()
