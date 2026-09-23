"""G2++ two-factor model: curve fit, martingale property, calibration (no network)."""
import math
from datetime import date

import numpy as np
import pytest

from capitolis_pricers.curves import flat_curve
from risk_engine.models.g2pp import G2PP, calibrate_to_yield_covariance, model_zero_rate_cov

REF = date(2026, 8, 28)


def _model(rho=-0.5):
    return G2PP(flat_curve(REF, 0.04), sigma=0.006, a=0.05, eta=0.008, b=0.6, rho=rho)


def test_reproduces_todays_curve_at_t0():
    m = _model()
    for T in (0.5, 2.0, 10.0):
        assert m.bond_price(0.0, T, 0.0, 0.0) == pytest.approx(m.discount0(T), rel=1e-12)


def test_short_rate_at_zero_is_todays_forward():
    m = _model()
    assert m.short_rate(0.0, 0.0) == pytest.approx(m.short_rate0(), abs=1e-12)
    assert m.short_rate0() == pytest.approx(0.04, abs=1e-4)


def test_bond_price_is_a_martingale_after_money_market_discounting():
    """E[ exp(-int_0^t r) P(t,T) ] = P(0,T): tests phi(t), the exact (x,y) transition
    and the bond-price formula together, for correlated factors."""
    m = _model(rho=-0.6)
    rng = np.random.default_rng(5)
    n, steps, t_end, T = 40000, 24, 2.0, 7.0
    dt = t_end / steps
    x = np.zeros(n)
    y = np.zeros(n)
    integ = np.zeros(n)
    r_prev = np.full(n, m.short_rate0())
    for k in range(steps):
        z1, z2 = rng.standard_normal(n), rng.standard_normal(n)
        # vectorised exact step
        s, a, e, b, r = m.sigma, m.a, m.eta, m.b, m.rho
        sd_x = s * math.sqrt((1 - math.exp(-2 * a * dt)) / (2 * a))
        sd_y = e * math.sqrt((1 - math.exp(-2 * b * dt)) / (2 * b))
        c = r * s * e * (1 - math.exp(-(a + b) * dt)) / (a + b) / (sd_x * sd_y)
        xn = x * math.exp(-a * dt) + sd_x * z1
        yn = y * math.exp(-b * dt) + sd_y * (c * z1 + math.sqrt(1 - c * c) * z2)
        x, y = xn, yn
        r_now = x + y + m.alpha((k + 1) * dt)
        integ += 0.5 * (r_prev + r_now) * dt
        r_prev = r_now
    price = np.array([m.bond_price(t_end, T, xi, yi) for xi, yi in zip(x[:6000], y[:6000])])
    val = np.exp(-integ[:6000]) * price
    assert abs(val.mean() - m.discount0(T)) < 4 * val.std() / math.sqrt(len(val)) + 2e-4


def test_second_factor_gives_curve_twists_the_one_factor_model_cannot():
    """Holding the level factor fixed and moving y changes the long rate by less than
    the short rate (a slope move); in one-factor models all tenors move together."""
    m = _model()
    base = [m.bond_price(1.0, 1.0 + T, 0.0, 0.0) for T in (0.5, 10.0)]
    up = [m.bond_price(1.0, 1.0 + T, 0.0, 0.01) for T in (0.5, 10.0)]
    dz = [-(math.log(u) - math.log(b)) / T for u, b, T in zip(up, base, (0.5, 10.0))]
    assert dz[0] > 3 * dz[1] > 0


def test_calibration_recovers_parameters_from_a_model_covariance():
    tenors = [1, 2, 5, 10, 20, 30]
    truth = (0.006, 0.03, 0.007, 0.5, -0.6)
    cov = model_zero_rate_cov(truth, tenors)
    fit = calibrate_to_yield_covariance(cov, tenors)
    assert fit["rel_error"] < 1e-3
    assert np.allclose(fit["model_cov"], cov, rtol=2e-2, atol=1e-8)


def test_invalid_parameters_are_rejected():
    with pytest.raises(ValueError):
        G2PP(flat_curve(REF, 0.04), 0.006, 0.0, 0.008, 0.6, 0.0)
    with pytest.raises(ValueError):
        G2PP(flat_curve(REF, 0.04), 0.006, 0.05, 0.008, 0.6, 1.0)


def _engine_calib():
    from tests.test_jpy_factor import _calib
    c = _calib(with_jpy=True)
    c["g2"] = G2PP(c["hw"].base_curve, sigma=0.006, a=0.04, eta=0.007, b=0.5, rho=-0.5)
    return c


def test_engine_runs_the_two_factor_model_and_reproduces_the_curve():
    from tests.test_jpy_factor import _Trade
    from risk_engine.simulation.engine import SimulationEngine
    eng = SimulationEngine(_engine_calib(), {"T": _Trade()}, method="pseudo_random", n_scenarios=20000,
                           seed=2, rates_model="g2pp")
    assert eng.factor_order[-1] == "RATE_USD_2" and eng.rm is eng.g2
    p = eng.simulate_paths()
    assert p["y_rate"].shape == p["x_rate"].shape
    times = np.array(eng.times)
    r = np.array([eng.rm.short_rate(p["x_rate"][:, k], times[k]) for k in range(len(times))]).T
    integ = np.concatenate([np.zeros((r.shape[0], 1)), np.cumsum(0.5 * (r[:, :-1] + r[:, 1:]) * np.diff(times), axis=1)], axis=1)
    disc = np.exp(-integ[:, -1])
    assert abs(disc.mean() - eng.g2.discount0(times[-1])) < 4 * disc.std() / np.sqrt(len(disc)) + 5e-4


def test_engine_default_is_still_one_factor():
    from tests.test_jpy_factor import _Trade, _calib
    from risk_engine.simulation.engine import SimulationEngine
    eng = SimulationEngine(_calib(), {"T": _Trade()}, method="pseudo_random", n_scenarios=50, seed=2)
    assert eng.g2 is None and "y_rate" not in eng.simulate_paths()
