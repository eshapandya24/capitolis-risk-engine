"""Tests for CVA and SA-CVA aggregation (no network needed)."""
import numpy as np
import pytest

from risk_engine.exposure import sa_cva as S
from risk_engine.exposure.cva import cva
from risk_engine.models.credit import LGD, marginal_pd, survival_prob


def test_marginal_pds_sum_to_one_minus_terminal_survival():
    t = np.array([0.0, 0.5, 1, 2, 3])
    pd_ = marginal_pd(t, [0.5, 3.0], [0.01, 0.02])
    assert pd_.sum() == pytest.approx(1 - survival_prob(3.0, [0.5, 3.0], [0.01, 0.02]))
    assert (pd_ > 0).all()


def test_cva_closed_form_for_flat_exposure():
    """Flat EE, flat spread, no discounting: CVA ~= EE * (1 - exp(-s T/LGD)) * LGD."""
    t = np.linspace(0, 5, 101)
    ee = np.full_like(t, 10.0)
    s = 0.02
    got = cva(ee, t, [1.0, 10.0], [s, s])
    expected = LGD * 10.0 * (1 - np.exp(-s * 5 / LGD))
    assert got == pytest.approx(expected, rel=1e-6)


def test_cva_zero_when_spread_zero_or_exposure_zero():
    t = np.array([0, 1, 2.0])
    assert cva(np.array([5, 5, 5.0]), t, [1.0], [0.0]) == 0.0
    assert cva(np.zeros(3), t, [1.0], [0.02]) == 0.0


def test_single_factor_bucket_capital_is_abs_weighted_sensitivity():
    K, Kb = S.aggregate({1: [0.3]}, {1: np.eye(1)}, 0.15, m=1.0)
    assert K == pytest.approx(0.3) and Kb[1] == pytest.approx(0.3)


def test_perfectly_correlated_factors_add_linearly_and_uncorrelated_in_quadrature():
    ws = [3.0, 4.0]
    assert S.bucket_K(ws, np.eye(2)) == pytest.approx(5.0)
    assert S.bucket_K(ws, np.ones((2, 2))) == pytest.approx(7.0)


def test_cross_bucket_diversification_and_multiplier():
    ws = {1: [1.0], 2: [1.0]}
    rho = {1: np.eye(1), 2: np.eye(1)}
    K0, _ = S.aggregate(ws, rho, 0.0)
    K1, _ = S.aggregate(ws, rho, 1.0)
    assert K0 == pytest.approx(np.sqrt(2)) and K1 == pytest.approx(2.0)
    K125, _ = S.aggregate(ws, rho, 0.0, m=1.25)
    assert K125 == pytest.approx(1.25 * np.sqrt(2))


def test_ir_correlation_matrix_is_symmetric_positive_definite():
    assert np.allclose(S.IR_RHO, S.IR_RHO.T)
    assert np.linalg.eigvalsh(S.IR_RHO).min() > 0


def test_ccs_correlation_structure():
    keys, R = S.ccs_rho(["A", "B"], [1, 3])
    idx = {k: i for i, k in enumerate(keys)}
    assert R[idx[("A", 1)], idx[("A", 3)]] == pytest.approx(0.9)
    assert R[idx[("A", 1)], idx[("B", 1)]] == pytest.approx(0.5)
    assert R[idx[("A", 1)], idx[("B", 3)]] == pytest.approx(0.45)
    assert np.linalg.eigvalsh(R).min() > 0


def test_path_discount_factors_match_curve_when_paths_are_deterministic():
    """With x=0 (no shocks) the trapezoid discount factor must reproduce the
    fitted curve's P(0,t) closely (grid-integration error only)."""
    from capitolis_pricers.curves import flat_curve
    from risk_engine.models.rates import HullWhite1F
    from risk_engine.exposure.cva import path_discount_factors
    hw = HullWhite1F(flat_curve("2026-08-28", 0.04), sigma=1e-9, a=0.05)
    times = np.linspace(0, 3, 37)
    d = path_discount_factors(np.zeros((1, len(times))), times, hw)[0]
    for t, dv in zip(times, d):
        assert dv == pytest.approx(hw.discount0(t), abs=2e-5)


def test_ccs_rating_curves_order_by_credit_quality():
    from risk_engine.market.credit_spreads import rating_spread_curve
    from datetime import date
    s = {r: rating_spread_curve(r, date(2026, 8, 28))[1][2] for r in ("AA", "A", "BBB", "BB")}
    assert s["AA"] < s["A"] < s["BBB"] < s["BB"]
