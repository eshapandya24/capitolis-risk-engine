"""
Tests for the exposure convention in the Capitolis kickoff deck (slides 8-9):
exposure(t) = max( V(t + 10bd) - V(t - 1bd), 0 ), per trade and per
counterparty, PFE = 99th percentile, MPE = peak PFE. No network needed.
"""
from datetime import date

import numpy as np
import pytest

from risk_engine.exposure import spec_exposure as spec
from risk_engine.simulation.engine import add_business_days, build_time_grid


def _node_map(n):
    """Reporting node i sits at grid index 3i+1, with t-1bd at 3i and t+10bd at 3i+2."""
    return {i: {"reporting": 3 * i + 1, "lookahead": 3 * i + 2, "prev": 3 * i} for i in range(n)}


def _prev(nm):
    return {i: m["prev"] for i, m in nm.items()}


def test_exposure_is_the_move_from_the_prior_day_npv_not_the_level():
    """V(t-1)=100, V(t+10)=130 -> exposure 30, not 130 (the whole 100 is
    margined); a fall in value gives zero."""
    nm = _node_map(1)
    net = np.array([[100.0, 100.0], [100.0, 100.0], [130.0, 60.0]])  # (nodes=3, scenarios=2)
    out = spec.window_exposure(net, nm, _prev(nm))
    assert out[0, 0] == pytest.approx(30.0)
    assert out[0, 1] == 0.0


def test_variation_margin_is_signed_when_the_prior_day_npv_is_negative():
    """We posted 50 (V(t-1) = -50); if V(t+10) = -10, we are owed 40 more than
    the collateral position implies: exposure = -10 - (-50) = 40 (a floored
    one-way collateral formula would give 0)."""
    nm = _node_map(1)
    net = np.array([[-50.0], [-50.0], [-10.0]])
    assert spec.window_exposure(net, nm, _prev(nm))[0, 0] == pytest.approx(40.0)


def test_netting_happens_before_the_positive_part():
    """Two trades, one counterparty: +30 and -20 moves net to +10."""
    nm = _node_map(1)
    npv = np.zeros((2, 3, 1))
    npv[0, 2, 0] = 30.0
    npv[1, 2, 0] = -20.0
    out = spec.exposure_by_counterparty(["a", "b"], {"a": "X", "b": "X"}, npv, nm, prev_node=_prev(nm))
    assert out["X"][0, 0] == pytest.approx(10.0)


def test_per_trade_exposures_are_not_netted_and_cover_every_trade():
    nm = _node_map(1)
    npv = np.zeros((2, 3, 1))
    npv[0, 2, 0], npv[1, 2, 0] = 30.0, -20.0
    out = spec.exposure_by_trade(["a", "b"], npv, nm, prev_node=_prev(nm))
    assert set(out) == {"a", "b"}
    assert out["a"][0, 0] == 30.0 and out["b"][0, 0] == 0.0


def test_settlement_inside_the_window_is_not_counted_as_a_market_move():
    """Trade with NPV -80 settles inside the window (V(t+10) = 0): without the
    exclusion the drop looks like an 80 exposure; with it, zero."""
    nm = _node_map(1)
    npv = np.zeros((1, 3, 1))
    npv[0, 0, 0] = npv[0, 1, 0] = -80.0
    dates = [date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 16)]
    exp_date = {"a": date(2026, 9, 10)}
    raw = spec.exposure_by_trade(["a"], npv, nm, prev_node=_prev(nm))
    excl = spec.exposure_by_trade(["a"], npv, nm, prev_node=_prev(nm), trade_expiry=exp_date,
                                  exclude_maturing=True, dates=dates)
    assert raw["a"][0, 0] == pytest.approx(80.0)
    assert excl["a"][0, 0] == 0.0
    cp = spec.exposure_by_counterparty(["a"], {"a": "X"}, npv, nm, prev_node=_prev(nm), trade_expiry=exp_date,
                                       exclude_maturing=True, dates=dates)
    assert cp["X"][0, 0] == 0.0


def test_summary_metrics_and_one_year_mask():
    rng = np.random.default_rng(0)
    arr = np.abs(rng.normal(size=(4, 20000))) * np.array([[1], [3], [2], [10]])
    s_all = spec.summarize(arr, 0.99)
    s_1y = spec.summarize(arr, 0.99, [True, True, True, False])
    assert s_all["MPE"] == pytest.approx(np.quantile(arr[3], 0.99))
    assert s_1y["MPE"] == pytest.approx(np.quantile(arr[1], 0.99))
    assert (s_all["MedianExposure"] <= s_all["PFE"]).all()


class _Trade:
    def __init__(self, end):
        self.end_date = end


def test_grid_has_a_prior_day_node_exactly_one_business_day_before_each_reporting_date():
    ref = date(2026, 8, 28)
    trades = {"t": _Trade(date(2027, 1, 15))}
    dates, times, nm = build_time_grid(ref, trades, mpor_days=10, vm_lag_days=1)
    for i, m in nm.items():
        rd = dates[m["reporting"]]
        if m["prev"] is not None:
            assert dates[m["prev"]] == add_business_days(rd, -1)
            assert dates[m["prev"]] > ref
        if m["lookahead"] is not None:
            assert dates[m["lookahead"]] == add_business_days(rd, 10)
    # the first reporting date (today) has no prior mark on the path
    assert nm[0]["prev"] is None


def test_negative_business_day_offset_rolls_away_from_a_weekend():
    monday = date(2026, 8, 31)
    assert add_business_days(monday, -1) == date(2026, 8, 28)  # the Friday before
