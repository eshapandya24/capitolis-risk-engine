"""
Tests for MPOR-shifted (collateralized) exposure -- src/risk_engine/exposure/
collateral.py and simulation/engine.py's build_time_grid(mpor_days=...).
No network access needed.
"""
from datetime import date, timedelta

import numpy as np

from risk_engine.simulation.engine import build_time_grid
from risk_engine.exposure.collateral import mpor_shifted_exposure_by_counterparty


def _hol():
    from pandas.tseries.holiday import USFederalHolidayCalendar
    return USFederalHolidayCalendar().holidays(start='2020-01-01', end='2040-12-31').values.astype('datetime64[D]')


class _FakeTrade:
    def __init__(self, end_date):
        self.end_date = end_date


def test_time_grid_inserts_lookahead_nodes_exactly_mpor_business_days_later():
    ref = date(2026, 8, 28)
    trades = {"t1": _FakeTrade(date(2027, 1, 15))}
    dates, times, node_map = build_time_grid(ref, trades, mpor_days=10)

    for i, mapping in node_map.items():
        report_date = dates[mapping["reporting"]]
        if mapping["lookahead"] is not None:
            look_date = dates[mapping["lookahead"]]
            assert np.busday_count(report_date, look_date, holidays=_hol()) == 10


def test_last_reporting_node_has_no_lookahead_past_horizon():
    ref = date(2026, 8, 28)
    trades = {"t1": _FakeTrade(date(2026, 9, 5))}  # short horizon, only ~1 week
    dates, times, node_map = build_time_grid(ref, trades, mpor_days=10)
    last = max(node_map)
    assert node_map[last]["lookahead"] is None


def test_mpor_shifted_exposure_matches_hand_calculation():
    """Two nodes, one trade, one counterparty, one scenario -- hand-verify
    the formula: max(V(t+MPOR) - max(V(t) - threshold, 0), 0)."""
    trade_ids = ["t1"]
    trade_counterparty = {"t1": "CPTY_X"}
    # npv shape: (n_trades=1, n_nodes=2, n_scenarios=1)
    # V(t) = 100, V(t+MPOR) = 140
    npv = np.array([[[100.0], [140.0]]])
    node_map = {0: {"reporting": 0, "lookahead": 1}}

    # threshold = 0 (full VM): collateral = max(100-0,0) = 100; exposure = max(140-100,0) = 40
    result = mpor_shifted_exposure_by_counterparty(trade_ids, trade_counterparty, npv, node_map, threshold=0.0)
    assert np.isclose(result["CPTY_X"][0, 0], 40.0)

    # threshold = 1e12 (effectively uncollateralized): collateral = 0; exposure = max(140-0,0) = 140
    result2 = mpor_shifted_exposure_by_counterparty(trade_ids, trade_counterparty, npv, node_map, threshold=1e12)
    assert np.isclose(result2["CPTY_X"][0, 0], 140.0)

    # threshold = 200 (never collateralized here): collateral = max(100-200,0) = 0; exposure = max(140-0,0) = 140
    result3 = mpor_shifted_exposure_by_counterparty(trade_ids, trade_counterparty, npv, node_map, threshold=200.0)
    assert np.isclose(result3["CPTY_X"][0, 0], 140.0)


def test_mpor_shifted_exposure_never_negative():
    """A large drop in value between t and t+MPOR must floor at 0, not go negative."""
    trade_ids = ["t1"]
    trade_counterparty = {"t1": "CPTY_X"}
    npv = np.array([[[100.0], [10.0]]])  # value FELL from 100 to 10
    node_map = {0: {"reporting": 0, "lookahead": 1}}
    result = mpor_shifted_exposure_by_counterparty(trade_ids, trade_counterparty, npv, node_map, threshold=0.0)
    assert result["CPTY_X"][0, 0] == 0.0


def test_business_day_lookahead_spans_more_than_ten_calendar_days_over_weekends():
    from risk_engine.simulation.engine import add_business_days
    fri = date(2026, 8, 28)  # a Friday
    assert add_business_days(fri, 10) == date(2026, 9, 14)  # skips 2 weekends and Labor Day (Sep 7)
    assert (add_business_days(fri, 10) - fri).days == 17
    assert add_business_days(date(2026, 9, 1), 0) == date(2026, 9, 1)
