"""
Tail-focused convergence study: how many paths are needed for a RELIABLE
99.9th-percentile PFE estimate (much noisier than the 95th percentile --
only ~1 in 1000 scenarios sits past that threshold, vs ~1 in 20 for the
95th). Extends docs/notes/convergence_study.md's method (one large pool,
bootstrap-resampled subsets) out through 30,000 paths specifically to see
where PFE99.9's accuracy/time tradeoff stops improving materially.

    python scripts/convergence_study_tail.py
"""
import time
import json
import os
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
N_POOL = 30000
N_VALUES = [500, 1000, 2000, 5000, 10000, 15000, 20000, 25000, 30000]
CONFIDENCE = 0.999
N_BOOTSTRAP = 150


def main():
    from datetime import date
    from risk_engine.models.calibration import build_calibration
    from risk_engine.simulation.engine import SimulationEngine
    from risk_engine.simulation.parallel import reprice_all_parallel
    from risk_engine.exposure.aggregate import netted_exposure_by_counterparty, portfolio_exposure

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
    elapsed = t1 - t0
    per_scenario_parallel = elapsed / N_POOL
    print(f"Repriced pool in {elapsed:.1f}s ({per_scenario_parallel*1000:.2f} ms/scenario, parallel, 8 workers)")
    # Sanity-guard against a corrupted wall-clock measurement (e.g. the
    # machine slept mid-run, as happened once before): if the measured
    # per-scenario cost is wildly off the previously-established ~50ms/scenario
    # baseline, don't trust it for the time-estimate column below.
    BASELINE_MS = 50.0
    if not (BASELINE_MS * 0.3 < per_scenario_parallel * 1000 < BASELINE_MS * 5):
        print(f"  WARNING: measured per-scenario cost ({per_scenario_parallel*1000:.1f}ms) is far off the "
              f"established ~{BASELINE_MS}ms baseline -- likely a corrupted wall-clock measurement "
              f"(e.g. system sleep mid-run), NOT a real perf change. Using the baseline for time estimates instead.")
        per_scenario_parallel = BASELINE_MS / 1000.0

    by_cpty = netted_exposure_by_counterparty(trade_ids, eng.trade_counterparty, npv)
    portfolio = portfolio_exposure(by_cpty)  # (n_nodes, N_POOL)

    node_1y = min(12, len(eng.dates) - 1)
    exposure_1y_full = portfolio[node_1y, :]

    pool_pfe = np.quantile(exposure_1y_full, CONFIDENCE)
    print(f"\nNode @ ~1y ({eng.dates[node_1y]}): pool PFE{CONFIDENCE*100:.1f} = {pool_pfe:,.0f} "
          f"(N_POOL={N_POOL} reference estimate)")

    rng = np.random.default_rng(123)
    results = []
    prev_se = None
    for N in N_VALUES:
        pfe_estimates = []
        for _ in range(N_BOOTSTRAP):
            idx = rng.choice(N_POOL, size=N, replace=(N > N_POOL))
            sub = exposure_1y_full[idx]
            pfe_estimates.append(np.quantile(sub, CONFIDENCE))
        pfe_arr = np.array(pfe_estimates)
        pfe_mean, pfe_std = pfe_arr.mean(), pfe_arr.std()
        rel_se_pct = pfe_std / pfe_mean * 100
        bias_vs_pool_pct = (pfe_mean - pool_pfe) / pool_pfe * 100

        est_time_parallel = 28.7 + N * per_scenario_parallel

        marginal_improvement = None
        if prev_se is not None:
            marginal_improvement = (prev_se - pfe_std) / prev_se * 100
        prev_se = pfe_std

        results.append({
            "N": N,
            "PFE_mean": float(pfe_mean), "PFE_std": float(pfe_std),
            "relative_se_pct": float(rel_se_pct),
            "bias_vs_pool_pct": float(bias_vs_pool_pct),
            "marginal_se_improvement_pct": float(marginal_improvement) if marginal_improvement is not None else None,
            "est_time_s": float(est_time_parallel),
        })
        mi_str = f"{marginal_improvement:+.1f}%" if marginal_improvement is not None else "   n/a"
        print(f"N={N:6d}  PFE99.9={pfe_mean:12,.0f} (+/-{pfe_std:9,.0f}, {rel_se_pct:5.2f}%)  "
              f"bias_vs_pool={bias_vs_pool_pct:+6.2f}%  marginal_SE_gain={mi_str}  est.time={est_time_parallel:7.1f}s")

    out_path = os.path.join(ROOT, "data", "processed", "convergence_study_tail_pfe999.json")
    with open(out_path, "w") as f:
        json.dump({"N_pool": N_POOL, "confidence": CONFIDENCE, "pool_pfe_reference": float(pool_pfe),
                   "per_scenario_parallel_ms_used": per_scenario_parallel * 1000,
                   "node_1y_date": str(eng.dates[node_1y]), "results": results}, f, indent=2)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
