"""
Compares the 5 random-number-generation techniques in
src/risk_engine/simulation/random_numbers.py for speed vs. accuracy, on two
levels:

  1. A controlled European call option under GBM, using ONE of our real
     calibrated equity names' actual spot/vol (not arbitrary numbers) and a
     KNOWN Black-Scholes closed-form answer -- the standard textbook test
     case for comparing Monte Carlo variance-reduction techniques, because
     it lets us measure true bias and true estimator variance against a
     ground truth, cheaply enough to repeat hundreds of times per method.

  2. A confirmatory check that the SAME ranking holds on the real 39-factor,
     16-trade engine (fewer repeats, since each is much more expensive) --
     showing the option-pricing result isn't a toy-example artifact.

Run: python scripts/benchmark_variance_reduction.py
"""
import math
import time
import json
import os

import numpy as np


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
METHODS = ["pseudo_random", "antithetic", "moment_matched", "sobol", "latin_hypercube"]


def call_option_study(S0, K, r, q, sigma, T, n_scenarios=2000, n_repeats=200):
    from risk_engine.simulation.random_numbers import generate
    from risk_engine.simulation.black_scholes import bs_call_price

    truth = bs_call_price(S0, K, r, q, sigma, T)
    print(f"\n=== European call option study ===")
    print(f"S0={S0:.2f} K={K:.2f} r={r:.4f} q={q:.4f} sigma={sigma:.4f} T={T}")
    print(f"Black-Scholes truth: {truth:.6f}\n")

    results = {}
    for method in METHODS:
        estimates = []
        t0 = time.perf_counter()
        for trial in range(n_repeats):
            z = generate(method, n_scenarios, 1, 1, seed=1000 + trial).reshape(n_scenarios)
            ST = S0 * np.exp((r - q - 0.5 * sigma ** 2) * T + sigma * math.sqrt(T) * z)
            payoff = np.maximum(ST - K, 0.0) * math.exp(-r * T)
            estimates.append(payoff.mean())
        elapsed = time.perf_counter() - t0

        estimates = np.array(estimates)
        mean_est = estimates.mean()
        bias = mean_est - truth
        std_est = estimates.std()
        rmse = math.sqrt(bias ** 2 + std_est ** 2)
        time_per_trial_ms = elapsed / n_repeats * 1000

        results[method] = {
            "mean_estimate": float(mean_est), "bias": float(bias), "std": float(std_est),
            "rmse": float(rmse), "ms_per_trial": float(time_per_trial_ms),
        }
        print(f"{method:16s}  mean={mean_est:9.5f}  bias={bias:+.5f}  std={std_est:.5f}  "
              f"RMSE={rmse:.5f}  {time_per_trial_ms:.3f} ms/trial")

    print("\nRanking by RMSE (lower is better, at equal n_scenarios and n_repeats):")
    for method in sorted(results, key=lambda m: results[m]["rmse"]):
        print(f"  {method:16s} RMSE={results[method]['rmse']:.5f}")

    return truth, results


def real_engine_confirmatory_check(n_scenarios=120, n_repeats=4):
    """Confirms the ranking pattern (roughly) carries to the real engine.
    Far fewer repeats than the option study -- each full 16-trade reprice
    is orders of magnitude more expensive than one option-payoff vector."""
    from datetime import date
    from risk_engine.models.calibration import build_calibration
    from risk_engine.simulation.engine import SimulationEngine
    from risk_engine.exposure.aggregate import build_profiles

    print(f"\n=== Real-engine confirmatory check "
          f"({n_scenarios} scenarios x {n_repeats} repeats per method) ===")
    print("(Serial repricing -- small N here specifically to keep this check fast; "
          "the production run uses the parallel path at higher N, see run_simulation.py)\n")

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

    results = {}
    for method in METHODS:
        pfe_1y_estimates = []
        t0 = time.perf_counter()
        for trial in range(n_repeats):
            eng = SimulationEngine(calib, trades, method=method, n_scenarios=n_scenarios, seed=2000 + trial)
            paths = eng.simulate_paths()
            trade_ids, npv = eng.reprice_all(paths)
            profiles = build_profiles(trade_ids, eng.trade_counterparty, npv, eng.dates, confidence=0.95)
            # 1-year-ish node: index for the node closest to +1y (node 12 with monthly grid)
            node_1y = min(12, len(eng.dates) - 1)
            pfe_1y_estimates.append(profiles["__portfolio__"]["PFE"][node_1y])
        elapsed = time.perf_counter() - t0

        arr = np.array(pfe_1y_estimates)
        results[method] = {"mean": float(arr.mean()), "std": float(arr.std()),
                            "sec_per_trial": elapsed / n_repeats}
        print(f"{method:16s} PFE(1y) mean={arr.mean():14,.0f}  std={arr.std():12,.0f}  "
              f"({elapsed/n_repeats:.1f}s/trial)")

    print("\nRanking by estimator std across methods (lower = more stable PFE estimate "
          "at equal scenario count):")
    for method in sorted(results, key=lambda m: results[m]["std"]):
        print(f"  {method:16s} std={results[method]['std']:,.0f}")

    return results


def main():
    calib_date_note = "Using AAPL's real calibrated spot/vol from data already collected."
    print(calib_date_note)

    import csv
    from risk_engine.models.calibration import load_vol_table, _isin_to_ticker
    from risk_engine.market.equities import fetch_raw, clean

    isin_to_ticker = _isin_to_ticker()
    aapl_isin = next(isin for isin, tk in isin_to_ticker.items() if tk == "AAPL")
    raw = fetch_raw({aapl_isin: "AAPL"})
    spot, div = clean(raw)[aapl_isin]
    vol_table = load_vol_table()
    sigma = vol_table[aapl_isin]
    r = 0.038  # representative short rate, matches current curve's short end

    truth, option_results = call_option_study(
        S0=spot, K=spot, r=r, q=div, sigma=sigma, T=1.0,
        n_scenarios=2000, n_repeats=200,
    )

    engine_results = real_engine_confirmatory_check(n_scenarios=120, n_repeats=4)

    out = {"option_study": {"truth": truth, "results": option_results},
           "real_engine_check": engine_results}
    out_path = os.path.join(ROOT, "data", "processed", "variance_reduction_benchmark.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
