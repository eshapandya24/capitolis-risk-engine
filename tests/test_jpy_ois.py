"""
Tests for the JPY OIS history (market/jpy_ois.py, data/raw/sources/JPY.xlsx):
bootstrap correctness on synthetic data (always runs) and empirical
findings on the real file (skipped if the licensed file is absent).
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from risk_engine.market import jpy_ois as J


def test_tenor_suffix_map():
    assert J.tenor_years("JYSO5") == 5.0
    assert J.tenor_years("JYSOA") == pytest.approx(1 / 12)
    assert J.tenor_years("JYSOK") == pytest.approx(11 / 12)
    assert J.tenor_years("JYSO2Z") == pytest.approx(2 / 52)
    assert J.tenor_years("JYSO1F") == pytest.approx(1.5)
    assert J.tenor_years("JYSO40") == 40.0


def test_bootstrap_reprices_par_swaps_on_a_synthetic_curve():
    """Annual-pay par swap at the quoted par rate must have zero PV on the
    bootstrapped discount factors."""
    par = {1 / 12: 0.010, 0.5: 0.011, 1.0: 0.012, 2.0: 0.014, 3.0: 0.016, 5.0: 0.019, 10.0: 0.025}
    times, dfs = J.bootstrap_discount_factors(par)
    d = dict(zip(times, dfs))
    for n, rate in ((2, 0.014), (3, 0.016), (5, 0.019), (10, 0.025)):
        annuity = sum(d[float(i)] for i in range(1, n + 1))
        assert 1.0 - rate * annuity - d[float(n)] == pytest.approx(0.0, abs=1e-12)


def test_bootstrap_handles_negative_par_rates():
    par = {1.0: -0.002, 2.0: -0.001, 5.0: 0.001}
    t, d = J.bootstrap_discount_factors(par)
    assert d[0] > 1.0 and all(np.isfinite(d))


needs_data = pytest.mark.skipif(not J.available(), reason="JPY OIS history (data/raw/sources/JPY.xlsx) not present")


@needs_data
def test_history_spans_2011_to_2026_and_contains_negative_rates():
    h = J.load_jpy_ois_history()
    assert h.index.min().year == 2011 and h.index.max().year >= 2026
    assert (h["MUTKCALM"] < 0).sum() > 1000
    assert h.min().min() < -0.2  # deepest negative par rate ~ -0.37%
    assert h.filter(like="JYSO").shape[1] == 35


@needs_data
def test_bootstrapped_zero_curve_matches_bloomberg_zero_curve_within_a_few_bp():
    from risk_engine.market.bloomberg import available, load_jpy_bloomberg_zero_curve, build_curve_from_bloomberg_zero_curve
    if not available():
        pytest.skip("Bloomberg snapshot absent")
    ref = date(2026, 8, 31)
    ours = J.jpy_zero_curve(ref)
    bb = build_curve_from_bloomberg_zero_curve(load_jpy_bloomberg_zero_curve(), ref)
    for y in (1, 2, 5, 10, 20, 30):
        d = ref + timedelta(days=round(365.25 * y))
        assert abs(ours.zero_rate(d) - bb.zero_rate(d)) < 3e-4


@needs_data
def test_jpy_ois_vol_rises_with_tenor_in_every_window_so_fitted_a_is_negative():
    from risk_engine.models.hw_calibration import calibrate_jpy_mean_reversion_from_ois
    for years in (1, 3, 5, 10):
        v = J.realized_vol_by_tenor(date(2026, 8, 28), years)
        assert v[30] > v[10] > v[2] > v[1], f"vol not rising with tenor over {years}y: {v}"
        assert calibrate_jpy_mean_reversion_from_ois(date(2026, 8, 28), years)["a"] < 0


@needs_data
def test_jpy_factor_uses_the_lower_bound_mean_reversion_and_ois_curve():
    from risk_engine.models.calibration import load_or_calibrate_jpy_mean_reversion, JPY_MEAN_REVERSION_FLOOR
    a, detail = load_or_calibrate_jpy_mean_reversion(0.0167, ref_date=date(2026, 8, 28))
    assert a == JPY_MEAN_REVERSION_FLOOR
    assert detail["method"] == "jpy_ois_history_par_rate_vol_term_structure"
