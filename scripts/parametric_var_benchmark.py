"""
Benchmark test #1: parametric (delta-normal) VaR vs. the full Monte Carlo
engine's own P&L distribution.

Horizon: the first monthly reporting node (~1 month forward). At that
horizon:
  - MC VaR: reprice the whole book at t=0 and at the horizon node for every
    simulated scenario (same paths/repricer as scripts/run_simulation.py),
    take PnL = V(T) - V(0) per scenario, VaR_c = -quantile(PnL, 1-c).
  - Parametric VaR: portfolio dollar-delta to every risk factor (equities,
    USDJPY, short rate) via bump-and-reprice at t=0 (NPV(0) is deterministic,
    so no Monte Carlo needed for the deltas themselves -- same technique as
    scripts/compute_greeks_demo.py Part B), combined with the SAME
    calibrated factor covariance matrix (vols + corr_matrix) the MC engine
    itself simulates from, scaled to the horizon: VaR_c = z_c * sqrt(d'Cd).

This is a standard model-validation check, not an equivalence claim: a
delta-normal VaR is expected to UNDERSTATE the true (MC) VaR whenever the
book has convexity/optionality (bond forwards, TRS financing legs) --
the test is that the two are the same ORDER OF MAGNITUDE and parametric
VaR is not systematically larger (which would flag a sign/scaling bug in
the deltas or the covariance construction), not that they match exactly.
"""
import os
import time
from datetime import date

import numpy as np
from scipy.stats import norm

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


def portfolio_npv(trades, market):
    return sum(t.npv(market, reporting=True) for t in trades.values())


def build_base_market(calib):
    from capitolis_pricers.market import MarketState
    from capitolis_pricers.curves import FxCurve
    fx_curve = FxCurve("USD", "JPY", calib["fx_spot"], calib["usd_curve"])
    return MarketState(
        ref_date=calib["ref_date"], reporting_ccy="USD",
        discount_curves={"USD": calib["usd_curve"]},
        equity_spots=dict(calib["equity_spots"]), equity_dividend_rates=calib["dividends"],
        fx_curves={("USD", "JPY"): fx_curve},
    )


def portfolio_deltas(trades, calib):
    """Dollar-delta of portfolio NPV(0) to every simulated risk factor
    (equity spots, FX spot, short rate level), by bump-and-reprice --
    exact, since NPV(0) is deterministic (no Monte Carlo noise)."""
    from capitolis_pricers.market import MarketState
    from capitolis_pricers.curves import FxCurve, Curve

    deltas = {}
    base_spots = dict(calib["equity_spots"])
    isins_used = sorted(set(p.isin for t in trades.values()
                             if hasattr(t, "positions") for p in t.positions)
                         & set(base_spots))

    for isin in isins_used:
        S0 = base_spots[isin]
        h = 0.01 * S0
        for bump, sign in [(h, 1), (-h, -1)]:
            spots = dict(base_spots)
            spots[isin] = S0 + bump
            market = MarketState(
                ref_date=calib["ref_date"], reporting_ccy="USD",
                discount_curves={"USD": calib["usd_curve"]}, equity_spots=spots,
                equity_dividend_rates=calib["dividends"],
                fx_curves={("USD", "JPY"): FxCurve("USD", "JPY", calib["fx_spot"], calib["usd_curve"])},
            )
            v = portfolio_npv(trades, market)
            if sign == 1:
                v_up = v
            else:
                v_dn = v
        deltas[isin] = (v_up - v_dn) / (2 * h)

    # FX (USDJPY)
    fx0 = calib["fx_spot"]
    h_fx = 0.01 * fx0
    for bump, tag in [(h_fx, "up"), (-h_fx, "dn")]:
        fx_curve = FxCurve("USD", "JPY", fx0 + bump, calib["usd_curve"])
        market = MarketState(
            ref_date=calib["ref_date"], reporting_ccy="USD",
            discount_curves={"USD": calib["usd_curve"]}, equity_spots=base_spots,
            equity_dividend_rates=calib["dividends"], fx_curves={("USD", "JPY"): fx_curve},
        )
        v = portfolio_npv(trades, market)
        if tag == "up":
            v_up = v
        else:
            v_dn = v
    deltas["FX_USDJPY"] = (v_up - v_dn) / (2 * h_fx)

    # Parallel shift of the USD short-rate curve (1bp)
    h_r = 1e-4
    base_curve = calib["usd_curve"]
    pillar_times = base_curve._t[1:]  # skip the t=0 -> DF=1 anchor Curve prepends
    base_dfs = [np.exp(lndf) for lndf in base_curve._lndf[1:]]
    for bump, tag in [(h_r, "up"), (-h_r, "dn")]:
        bumped = Curve(base_curve.ref_date, list(pillar_times),
                        [df * np.exp(-bump * t) for df, t in zip(base_dfs, pillar_times)],
                        basis=base_curve.basis)
        market = MarketState(
            ref_date=calib["ref_date"], reporting_ccy="USD",
            discount_curves={"USD": bumped}, equity_spots=base_spots,
            equity_dividend_rates=calib["dividends"],
            fx_curves={("USD", "JPY"): FxCurve("USD", "JPY", fx0, bumped)},
        )
        v = portfolio_npv(trades, market)
        if tag == "up":
            v_up = v
        else:
            v_dn = v
    deltas["RATE_USD"] = (v_up - v_dn) / (2 * h_r)

    return deltas


def parametric_var(deltas, calib, T, confidence):
    """Delta-normal VaR: z_c * sqrt(d' Cov d), Cov built from the SAME
    per-factor vols (gbm.vols / fx_vol / hw.sigma) and corr_matrix the MC
    engine itself uses, scaled to horizon T (years)."""
    gbm, hw = calib["gbm"], calib["hw"]
    factor_order = [f for f in calib["factor_order"] if f in deltas]
    d = np.array([deltas[f] for f in factor_order])

    sigma_dollar = []
    for f in factor_order:
        if f == "RATE_USD":
            sigma_dollar.append(hw.sigma * np.sqrt(T))  # already an absolute (dollar-per-unit-rate) vol
        elif f == "FX_USDJPY":
            sigma_dollar.append(gbm.fx_vol * calib["fx_spot"] * np.sqrt(T))  # lognormal -> normal approx
        else:
            sigma_dollar.append(gbm.vols[f] * calib["equity_spots"][f] * np.sqrt(T))
    sigma_dollar = np.array(sigma_dollar)

    corr = calib["corr_matrix"].loc[factor_order, factor_order].values
    cov = np.outer(sigma_dollar, sigma_dollar) * corr
    variance = float(d @ cov @ d)
    z = norm.ppf(confidence)
    return z * np.sqrt(max(variance, 0.0)), d, sigma_dollar


def main():
    from risk_engine.models.calibration import build_calibration
    from risk_engine.simulation.engine import SimulationEngine

    ref_date = date(2026, 8, 28)
    n_scenarios = 1500
    confidence = 0.99

    print("Loading calibration + trades...")
    calib = build_calibration(ref_date)
    trades = load_trades()

    eng = SimulationEngine(calib, trades, method="latin_hypercube", n_scenarios=n_scenarios, seed=7)
    horizon_idx = 1  # first monthly node past t=0
    T = eng.times[horizon_idx]
    print(f"Horizon: node {horizon_idx} = {eng.dates[horizon_idx]} (T={T:.4f}y)")

    t0 = time.perf_counter()
    paths = eng.simulate_paths()
    from risk_engine.simulation.parallel import reprice_all_parallel
    trade_ids, npv = reprice_all_parallel(eng, paths)
    print(f"MC simulate+reprice: {time.perf_counter()-t0:.1f}s")

    v0 = npv[:, 0, :].sum(axis=0)          # (n_scenarios,) -- deterministic, all equal
    vT = npv[:, horizon_idx, :].sum(axis=0)
    pnl = vT - v0[0]
    mc_var = {c: -np.quantile(pnl, 1 - c) for c in (0.95, 0.99)}

    print(f"\nPortfolio NPV(0) = {v0[0]:,.2f} USD")
    print(f"MC P&L distribution at T: mean={pnl.mean():,.2f}  std={pnl.std():,.2f}")
    for c, var in mc_var.items():
        print(f"  MC VaR{int(c*100)} = {var:,.2f} USD")

    print("\nComputing bump-and-reprice deltas for parametric VaR...")
    deltas = portfolio_deltas(trades, calib)
    for f, d in sorted(deltas.items(), key=lambda kv: -abs(kv[1]))[:8]:
        print(f"  delta[{f:12s}] = {d:14,.2f} USD per unit")

    param_var, d_vec, sig_vec = parametric_var(deltas, calib, T, confidence)
    print(f"\nParametric (delta-normal) VaR{int(confidence*100)} = {param_var:,.2f} USD")
    print(f"MC VaR{int(confidence*100)}                          = {mc_var[confidence]:,.2f} USD")
    ratio = param_var / mc_var[confidence] if mc_var[confidence] else float("nan")
    print(f"ratio (parametric / MC) = {ratio:.2f}")
    print("\nExpectation: ratio in roughly [0.3, 1.3] -- parametric VaR should be the same "
          "order of magnitude as MC and typically somewhat SMALLER (it ignores convexity/"
          "optionality that MC captures); a wildly larger or negative parametric VaR would "
          "flag a sign or scaling bug in the deltas or covariance construction.")
    ok = 0.2 <= ratio <= 1.5
    print(f"\n{'PASS' if ok else 'FAIL'}: parametric VaR is {'within' if ok else 'outside'} "
          f"the expected range of MC VaR.")


if __name__ == "__main__":
    main()
