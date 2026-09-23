"""JPY short-rate factor wired into the simulation, and the USDJPY / JPY-name
drifts it drives (synthetic calibration, no network).

Conventions: X = USDJPY = JPY per USD. Under the USD money-market measure,
  * the JPY bank account valued in USD, B_JPY / X / B_USD, is a martingale;
  * a JPY-listed stock valued in USD, S / X (with dividends reinvested), is
    a martingale after USD discounting.
"""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from capitolis_pricers.curves import flat_curve
from risk_engine.models.equity_fx import CorrelatedGBM
from risk_engine.models.rates import HullWhite1F
from risk_engine.simulation.engine import SimulationEngine, extend_correlation

REF = date(2026, 8, 28)
R_USD, R_JPY = 0.04, 0.01
RHO_S_X = -0.3          # JPY stock vs USDJPY shock correlation
RHO_RATES = -0.04
RHO_JPYRATE_FX = 0.05


class _Trade:
    counterparty = "CPTY_X"
    end_date = date(2028, 8, 28)


def _calib(with_jpy=True, sigma_fx=0.10):
    order = ["JP_STK", "US_STK", "FX_USDJPY", "RATE_USD"]
    corr = np.eye(4)
    corr[0, 2] = corr[2, 0] = RHO_S_X
    corr[0, 1] = corr[1, 0] = 0.3
    corr = pd.DataFrame(corr, index=order, columns=order)
    gbm = CorrelatedGBM(
        factor_names=["JP_STK", "US_STK"],
        spots={"JP_STK": 3000.0, "US_STK": 100.0, "FX_USDJPY": 150.0},
        vols={"JP_STK": 0.25, "US_STK": 0.20, "FX_USDJPY": sigma_fx, "RATE_USD": 0.006},
        currencies={"JP_STK": "JPY", "US_STK": "USD"},
        dividends={"JP_STK": 0.02, "US_STK": 0.01},
        jpy_usd_rate_diff=R_USD - R_JPY)
    c = {"ref_date": REF, "hw": HullWhite1F(flat_curve(REF, R_USD), sigma=0.006, a=0.05),
         "gbm": gbm, "corr_matrix": corr, "factor_order": order,
         "usd_jpy_rate_factor_corr": RHO_RATES, "jpy_rate_corr": {"FX_USDJPY": RHO_JPYRATE_FX}}
    if with_jpy:
        c["hw_jpy"] = HullWhite1F(flat_curve(REF, R_JPY), sigma=0.003, a=0.05)
    return c


def _engine(n=20000, **kw):
    return SimulationEngine(_calib(**kw.pop("calib_kw", {})), {"T": _Trade()}, method="pseudo_random",
                            n_scenarios=n, seed=3, **kw)


def _bank_account(hw, x, times):
    r = np.array([hw.short_rate(x[:, k], times[k]) for k in range(x.shape[1])]).T
    dt = np.diff(times)
    integral = np.concatenate([np.zeros((x.shape[0], 1)),
                               np.cumsum(0.5 * (r[:, :-1] + r[:, 1:]) * dt, axis=1)], axis=1)
    return np.exp(integral)                      # B(t) = exp(int r)


def _z(mean, se, target):
    return (mean - target) / se


def test_engine_adds_a_jpy_factor_and_a_jpy_curve_at_every_node():
    eng = _engine(n=50)
    assert eng.factor_order[-1] == "RATE_JPY" and eng.n_factors == 5
    paths = eng.simulate_paths()
    assert paths["x_jpy"].shape == paths["x_rate"].shape
    assert (paths["x_jpy"][:, 0] == 0).all()
    off = _engine(n=50, jpy_factor=False)
    assert "x_jpy" not in off.simulate_paths()


def test_jpy_rate_reproduces_the_jpy_curve():
    """E[1/B_JPY(T)] = P_JPY(0,T): the JPY factor is fitted to the JPY curve."""
    eng = _engine()
    paths = eng.simulate_paths()
    times = np.array(eng.times)
    disc = 1.0 / _bank_account(eng.hw_jpy, paths["x_jpy"], times)
    k = len(times) - 1
    se = disc[:, k].std() / np.sqrt(disc.shape[0])
    assert abs(disc[:, k].mean() - eng.hw_jpy.discount0(times[k])) < 4 * se + 5e-4


def test_simulated_shock_correlations_match_the_inputs():
    eng = _engine(n=40000)
    paths = eng.simulate_paths()
    dxu, dxj = np.diff(paths["x_rate"], axis=1)[:, 0], np.diff(paths["x_jpy"], axis=1)[:, 0]
    dfx = np.diff(paths["ln_fx"], axis=1)[:, 0]
    assert np.corrcoef(dxu, dxj)[0, 1] == pytest.approx(RHO_RATES, abs=0.02)
    assert np.corrcoef(dxj, dfx)[0, 1] == pytest.approx(RHO_JPYRATE_FX, abs=0.02)


def test_usdjpy_drifts_down_when_usd_rates_exceed_jpy_rates():
    """Regression for the earlier wrong-sign drift: JPY-per-USD must fall at
    about r_JPY - r_USD + s^2/2 per year, not rise."""
    eng = _engine()
    paths = eng.simulate_paths()
    times = np.array(eng.times)
    k = int(np.argmin(np.abs(times - 1.0)))
    change = (paths["ln_fx"][:, k] - paths["ln_fx"][0, 0]).mean()
    expected = (R_JPY - R_USD + 0.5 * 0.10 ** 2) * times[k]
    assert change < 0
    assert change == pytest.approx(expected, abs=0.01)


def test_jpy_bank_account_in_usd_is_a_martingale():
    """E[ B_JPY(T) / (X_T * B_USD(T)) ] = 1 / X_0."""
    eng = _engine()
    p = eng.simulate_paths()
    times = np.array(eng.times)
    bu, bj = _bank_account(eng.hw, p["x_rate"], times), _bank_account(eng.hw_jpy, p["x_jpy"], times)
    k = len(times) - 1
    x0 = 150.0
    v = x0 * bj[:, k] / (np.exp(p["ln_fx"][:, k]) * bu[:, k])
    assert abs(v.mean() - 1.0) < 4 * v.std() / np.sqrt(len(v)) + 1e-3


def test_jpy_stock_in_usd_is_a_martingale_after_reinvesting_dividends():
    """E[ S_T e^{qT} / (X_T B_USD(T)) ] = S_0 / X_0. Fails if the quanto
    correction rho*s*s_X or the JPY-rate drift is wrong."""
    eng = _engine()
    p = eng.simulate_paths()
    times = np.array(eng.times)
    bu = _bank_account(eng.hw, p["x_rate"], times)
    k = len(times) - 1
    T = times[k]
    q = 0.02
    gain = (np.exp(p["ln_spot"]["JP_STK"][:, k]) * np.exp(q * T)
            / (np.exp(p["ln_fx"][:, k]) * bu[:, k]))
    target = 3000.0 / 150.0
    assert abs(gain.mean() - target) < 4 * gain.std() / np.sqrt(len(gain)) + 5e-3 * target


def test_usd_stock_is_still_a_martingale():
    eng = _engine()
    p = eng.simulate_paths()
    times = np.array(eng.times)
    bu = _bank_account(eng.hw, p["x_rate"], times)
    k = len(times) - 1
    gain = np.exp(p["ln_spot"]["US_STK"][:, k]) * np.exp(0.01 * times[k]) / bu[:, k]
    assert abs(gain.mean() - 100.0) < 4 * gain.std() / np.sqrt(len(gain)) + 0.5


def test_extend_correlation_is_symmetric_with_unit_diagonal():
    base = np.array([[1.0, 0.2, 0.1], [0.2, 1.0, 0.0], [0.1, 0.0, 1.0]])
    ext = extend_correlation(base, ["A", "FX_USDJPY", "RATE_USD"], {"A": 0.1, "FX_USDJPY": -0.2}, -0.04)
    assert ext.shape == (4, 4) and np.allclose(ext, ext.T) and np.allclose(np.diag(ext), 1.0)
    assert list(ext[3, :3]) == [0.1, -0.2, -0.04]
    assert np.linalg.eigvalsh(ext).min() > 0
