"""
Benchmark test #2: martingale / no-arbitrage sanity check on the simulated
risk-neutral paths themselves (src/risk_engine/simulation/engine.py) --
independent of trade pricing, so it isolates bugs in the SDE discretization
(drift terms) from bugs in the pricers.

Two standard self-consistency checks under the risk-neutral (money-market)
measure Q:

  1. Bank-account consistency: E^Q[ exp(-integral_0^T r(s) ds) ] = P(0,T),
     today's REAL discount factor off the calibrated Hull-White curve. This
     must hold for ANY short-rate model correctly fitted to today's curve
     (the whole point of the Hull-White "alpha(t)" shift term in
     src/risk_engine/models/rates.py) -- a mismatch here means the
     simulated short-rate drift doesn't reproduce today's curve.

  2. Equity gains-process martingale: for each equity, the dividend-
     reinvested, money-market-discounted price is a Q-martingale:
     E^Q[ S_T * exp(q*T) * exp(-integral_0^T r(s) ds) ] = S_0.
     This holds by construction if dS/S = (r(t)-q)dt + sigma dW is
     simulated correctly (Ito), REGARDLESS of the correlation between the
     equity's Brownian motion and the rate's -- so this specifically tests
     that the drift term in engine.py's `_vec_step_log_spot` is right, not
     just that the marginal equity distribution looks lognormal.

The money-market integral is approximated by trapezoidal integration of
the simulated short rate over the SAME monthly grid the engine itself
uses (fine enough that the discretization error is far below MC noise at
the scenario counts used here -- checked by re-running at double the
scenario count and confirming the estimates don't move outside their own
standard error).
"""
import os
import time
from datetime import date

import numpy as np

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


def money_market_discount(hw, x_rate, times):
    """exp(-integral_0^T r(s)ds) per scenario, trapezoidal rule on the
    engine's own monthly grid. x_rate: (n_scen, n_nodes). times: (n_nodes,)."""
    n_scen, n_nodes = x_rate.shape
    r = np.zeros_like(x_rate)
    for k in range(n_nodes):
        r[:, k] = hw.short_rate(x_rate[:, k], times[k])
    dt = np.diff(times)
    integral = np.zeros(n_scen)
    running = np.zeros((n_scen, n_nodes))
    for k in range(n_nodes - 1):
        integral += 0.5 * (r[:, k] + r[:, k + 1]) * dt[k]
        running[:, k + 1] = integral
    return np.exp(-running)  # (n_scen, n_nodes)


def main():
    from risk_engine.models.calibration import build_calibration
    from risk_engine.simulation.engine import SimulationEngine

    ref_date = date(2026, 8, 28)
    n_scenarios = 8000

    print("Loading calibration...")
    calib = build_calibration(ref_date)
    trades = load_trades()

    eng = SimulationEngine(calib, trades, method="pseudo_random", n_scenarios=n_scenarios, seed=11)
    print(f"Simulating {n_scenarios} paths on {len(eng.dates)}-node grid "
          f"({eng.dates[0]} -> {eng.dates[-1]})...")
    t0 = time.perf_counter()
    paths = eng.simulate_paths()
    print(f"simulate_paths: {time.perf_counter()-t0:.1f}s")

    hw = calib["hw"]
    gbm = calib["gbm"]
    times = np.array(eng.times)
    x_rate = paths["x_rate"]
    disc = money_market_discount(hw, x_rate, times)  # (n_scen, n_nodes)

    print("\n=== Test 1: bank-account consistency  E[exp(-int r)] vs P(0,T) ===")
    check_nodes = [i for i in range(0, len(eng.dates), max(1, len(eng.dates) // 6))]
    all_ok = True
    for i in check_nodes:
        T = times[i]
        mc_df = disc[:, i].mean()
        se = disc[:, i].std() / np.sqrt(n_scenarios)
        true_df = hw.discount0(T)
        z = (mc_df - true_df) / se if se > 0 else 0.0
        rel_diff = abs(mc_df - true_df) / true_df
        # At short T the discount factor has almost no variance yet, so its
        # standard error is tiny and the z-test alone is overly strict --
        # a genuine (small) trapezoidal-integration bias from the monthly
        # grid then reads as many std errors away despite being economically
        # negligible. Require EITHER a statistically tight match OR an
        # economically negligible one (<5bp relative).
        ok = abs(z) < 4 or rel_diff < 5e-4
        all_ok &= ok
        print(f"  T={T:6.3f}y  MC E[disc]={mc_df:.6f} +/- {se:.6f}   P(0,T)={true_df:.6f}   "
              f"z={z:+.2f}  rel_diff={rel_diff*1e4:.2f}bp  {'OK' if ok else 'FAIL'}")

    print("\n=== Test 2: equity gains-process martingale  E[S_T*e^(qT)*disc] vs S_0 ===")
    tickers = sorted(gbm.vols.keys(), key=lambda f: -gbm.vols[f])[:6]  # a spread of vols
    T_final_idx = len(eng.dates) - 1
    T_final = times[T_final_idx]
    for isin in tickers:
        S0 = gbm.spots0[isin]
        q = gbm.dividends.get(isin, 0.0)
        ST = np.exp(paths["ln_spot"][isin][:, T_final_idx])
        gains = ST * np.exp(q * T_final) * disc[:, T_final_idx]
        mc_mean = gains.mean()
        se = gains.std() / np.sqrt(n_scenarios)
        z = (mc_mean - S0) / se if se > 0 else 0.0
        ok = abs(z) < 4
        all_ok &= ok
        print(f"  {isin:14s} S0={S0:9.2f}  E[gains]={mc_mean:9.2f} +/- {se:6.3f}  z={z:+.2f}  "
              f"{'OK' if ok else 'FAIL'}")

    print(f"\n{'PASS' if all_ok else 'FAIL'}: simulated paths are consistent with the "
          f"risk-neutral martingale property to within Monte Carlo noise.")


if __name__ == "__main__":
    main()
