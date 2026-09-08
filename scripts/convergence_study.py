"""
Empirical convergence study: how many Monte Carlo paths (scenarios) are
needed for an acceptable accuracy/speed tradeoff on the real 16-trade
engine?

Method: simulate one large pool of scenarios (N_POOL) with the validated
latin_hypercube sampler, then bootstrap-resample (without replacement)
subsets of size N' from that pool to empirically measure the standard
error of the portfolio PFE95(1y) and EE(1y) estimators as a function of N'
-- this avoids re-running the expensive repricing step at every N'
(repricing is done ONCE at N_POOL; everything else is array indexing).

Results and the recommended N are written up in
docs/notes/convergence_study.md -- this script is what produced them and
can be re-run if the book, calibration, or sampling method changes.

    python scripts/convergence_study.py
"""
import time
import json
import os
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    from datetime import date
    from risk_engine.models.calibration import build_calibration
    from risk_engine.simulation.engine import SimulationEngine
    from risk_engine.simulation.parallel import reprice_all_parallel
    from risk_engine.exposure.aggregate import netted_exposure_by_counterparty, portfolio_exposure

    N_POOL = 6000
    calib = build_calibration(date(2026, 8, 28))

    from capitolis_pricers.underlyings_loader import load_equities, load_bonds
    from capitolis_pricers.trade_loader import load_equity_trs, load_bond_forward, load_bond_trs
    TD = os.path.join(ROOT, "trade_data")
    U = os.path.join(TD, "underlyings")
    baskets = load_equities(os.path.join(U, "equities.csv"))
    bonds = load_bonds(os.path.join(U, "bonds.csv"))
    trades = {}
    trades.update(load_equity_trs(os.path.join(TD, "equity_trs.csv"), baskets))
    trades.update(load_bond_forward(os.path.join(TD, "bond_forward.csv"), bonds))
    trades.update(load_bond_trs(os.path.join(TD, "bond_trs.csv"), bonds))

    print(f"Simulating pool of N={N_POOL} scenarios (latin_hypercube)...")
    eng = SimulationEngine(calib, trades, method="latin_hypercube", n_scenarios=N_POOL, seed=42)
    paths = eng.simulate_paths()

    t0 = time.perf_counter()
    trade_ids, npv = reprice_all_parallel(eng, paths)
    t1 = time.perf_counter()
    per_scenario_parallel = (t1 - t0) / N_POOL
    print(f"Repriced pool in {t1-t0:.1f}s ({per_scenario_parallel*1000:.2f} ms/scenario, parallel, 8 workers)")

    by_cpty = netted_exposure_by_counterparty(trade_ids, eng.trade_counterparty, npv)
    portfolio = portfolio_exposure(by_cpty)  # (n_nodes, N_POOL)

    node_1y = min(12, len(eng.dates) - 1)
    exposure_1y_full = portfolio[node_1y, :]  # (N_POOL,) -- the full pool for this node

    print(f"\nNode @ ~1y ({eng.dates[node_1y]}): pool PFE95 = {np.quantile(exposure_1y_full, 0.95):,.0f}, "
          f"pool EE = {exposure_1y_full.mean():,.0f}")

    rng = np.random.default_rng(123)
    N_values = [100, 250, 500, 1000, 2000, 3000, 4000, 6000]
    n_bootstrap = 100

    results = []
    for N in N_values:
        pfe_estimates, ee_estimates = [], []
        for _ in range(n_bootstrap):
            idx = rng.choice(N_POOL, size=N, replace=(N > N_POOL))
            sub = exposure_1y_full[idx]
            pfe_estimates.append(np.quantile(sub, 0.95))
            ee_estimates.append(sub.mean())
        pfe_arr, ee_arr = np.array(pfe_estimates), np.array(ee_estimates)
        pfe_mean, pfe_std = pfe_arr.mean(), pfe_arr.std()
        ee_mean, ee_std = ee_arr.mean(), ee_arr.std()

        est_time_serial = N * per_scenario_parallel * 8  # undo the /8 amortization -> serial equiv
        est_time_parallel = 28.7 + N * per_scenario_parallel if N >= 200 else N * per_scenario_parallel * 8

        results.append({
            "N": N,
            "PFE95_mean": float(pfe_mean), "PFE95_std": float(pfe_std),
            "PFE95_relative_se_pct": float(pfe_std / pfe_mean * 100),
            "EE_mean": float(ee_mean), "EE_std": float(ee_std),
            "EE_relative_se_pct": float(ee_std / ee_mean * 100),
            "est_time_serial_s": float(est_time_serial),
            "est_time_parallel_s": float(est_time_parallel),
        })
        print(f"N={N:6d}  PFE95={pfe_mean:12,.0f} (+/-{pfe_std:9,.0f}, {pfe_std/pfe_mean*100:5.2f}%)  "
              f"EE={ee_mean:12,.0f} (+/-{ee_std:9,.0f}, {ee_std/ee_mean*100:5.2f}%)  "
              f"est.time: serial={est_time_serial:6.1f}s parallel={est_time_parallel:6.1f}s")

    out_path = os.path.join(ROOT, "data", "processed", "convergence_study.json")
    with open(out_path, "w") as f:
        json.dump({"N_pool": N_POOL, "per_scenario_parallel_ms": per_scenario_parallel * 1000,
                   "node_1y_date": str(eng.dates[node_1y]), "results": results}, f, indent=2)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
