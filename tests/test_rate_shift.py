"""Exact rate-bump repricing without resimulation (greeks/rate_shift.py),
on synthetic curves and paths (no network, no Monte Carlo)."""
from datetime import date

import numpy as np
import pytest

from capitolis_pricers.curves import zero_curve
from risk_engine.greeks.bumps import bump_curve
from risk_engine.greeks.rate_shift import _cum_alpha_offset, fast_rate_bump_paths
from risk_engine.models.rates import HullWhite1F

REF = date(2026, 8, 28)
TENORS = [0.25, 0.5, 1, 2, 3, 5, 10, 30]


def _hw(shift_bp=0.0, a=0.02, sigma=0.01):
    curve = zero_curve(REF, TENORS, [0.03 + 0.001 * t + shift_bp * 1e-4 for t in TENORS])
    return HullWhite1F(curve, sigma=sigma, a=a)


def test_cum_alpha_offset_is_zero_when_curves_match():
    hw = _hw()
    times = np.linspace(0, 5, 21)
    cum = _cum_alpha_offset(hw, hw, times)
    assert cum[0] == 0.0
    assert np.allclose(cum, 0.0, atol=1e-12)


def test_cum_alpha_offset_of_a_parallel_bump_accumulates_at_the_bump_size():
    """A pure parallel shift makes alpha_bumped - alpha_base a constant equal
    to the shift (forward rates all move by the same amount), so the
    cumulative offset at time T is exactly shift * T."""
    base = _hw()
    bumped_curve = bump_curve(base.base_curve, None, 1e-4)
    bumped = HullWhite1F(bumped_curve, sigma=base.sigma, a=base.a)
    times = np.linspace(0, 5, 21)
    cum = _cum_alpha_offset(base, bumped, times)
    for k, t in enumerate(times):
        assert cum[k] == pytest.approx(1e-4 * t, abs=2e-5)


def test_fast_rate_bump_paths_shifts_usd_names_and_fx_oppositely_and_leaves_jpy_unchanged():
    n_scen, n_nodes = 50, 6
    times = np.linspace(0, 2.0, n_nodes)
    rng = np.random.default_rng(0)
    ln_us = rng.normal(size=(n_scen, n_nodes))
    ln_jp = rng.normal(size=(n_scen, n_nodes))
    ln_fx = rng.normal(size=(n_scen, n_nodes))
    x_rate = rng.normal(size=(n_scen, n_nodes))
    base_paths = {"ln_spot": {"US_NAME": ln_us, "JP_NAME": ln_jp}, "ln_fx": ln_fx, "x_rate": x_rate, "_times": times}
    currencies = {"US_NAME": "USD", "JP_NAME": "JPY"}

    hw_base = _hw()
    hw_bumped = _hw(shift_bp=1.0)
    out = fast_rate_bump_paths(base_paths, hw_base, hw_bumped, currencies)

    cum = _cum_alpha_offset(hw_base, hw_bumped, times)
    assert np.any(cum != 0.0)
    assert np.allclose(out["ln_spot"]["US_NAME"], ln_us + cum[np.newaxis, :])
    assert np.allclose(out["ln_spot"]["JP_NAME"], ln_jp)               # unaffected
    assert np.allclose(out["ln_fx"], ln_fx - cum[np.newaxis, :])       # opposite sign
    assert np.allclose(out["x_rate"], x_rate)                          # stochastic factor reused unchanged


def test_fast_rate_bump_paths_requires_the_time_grid():
    with pytest.raises(ValueError):
        fast_rate_bump_paths({"ln_spot": {}, "ln_fx": np.zeros((1, 1)), "x_rate": np.zeros((1, 1))},
                             _hw(), _hw(1.0), {})
