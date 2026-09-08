"""
Regression tests for the SR3 contract -> curve pillar mapping. Two distinct
decade-resolution bugs were found and fixed here, both via the
Treasury-yield cross-check (data/MARKET_DATA.md #1) or while calibrating
Hull-White (data/processed/hull_white_calibration.json):

  1. A recently-expired serial contract (e.g. 'SR3Q6') must resolve to its
     own (past) IMM date, not get wrapped a decade forward -- wrapping
     silently created a multi-year gap in the curve.
  2. A genuinely far-future contract (e.g. 'SR3H0', quoted in 2026 meaning
     March 2030) must WRAP forward a decade -- naively resolving to the
     same decade as ref_date gives March 2020, which is implausible for a
     contract still live on the exchange, and got it silently dropped as
     "expired" by build_curve()'s filter, quietly truncating the curve's
     usable range. The first fix (removing wrapping entirely) fixed bug 1
     but caused bug 2; the current logic distinguishes the two cases by
     how far in the past the same-decade resolution lands.

No network access needed -- exercises _contract_period() directly.
"""
from datetime import date

from risk_engine.market.sofr import _contract_period


def test_expired_serial_contract_resolves_to_its_own_decade():
    # ref_date is after SR3Q6's (Aug 2026) IMM date -- it must NOT wrap to 2036.
    ref = date(2026, 8, 28)
    start, end = _contract_period("SR3Q6", ref)
    assert start.year == 2026
    assert start.month == 8
    assert end.year == 2026

    # A contract further out in the same decade should resolve normally too.
    start2, end2 = _contract_period("SR3Z6", ref)
    assert start2.year == 2026
    assert start2.month == 12


def test_far_dated_contract_wraps_to_next_decade():
    # SR3H0 quoted alongside 2026 contracts must mean March 2030, not the
    # implausible March 2020 (>6 years stale for a still-live quote).
    ref = date(2026, 8, 28)
    start, end = _contract_period("SR3H0", ref)
    assert start.year == 2030
    assert start.month == 3
    assert start > ref, "a live far-dated contract must resolve to the future, not the past"

    # Several more digits below ref_date's own decade digit (6) should all wrap.
    for symbol, expected_year in [("SR3U0", 2030), ("SR3H1", 2031), ("SR3H2", 2032)]:
        start_i, _ = _contract_period(symbol, ref)
        assert start_i.year == expected_year, f"{symbol} resolved to {start_i}, expected year {expected_year}"


def test_no_gap_between_consecutive_quarterly_contracts():
    ref = date(2026, 8, 28)
    _, end_u2 = _contract_period("SR3U2", ref)
    start_z2, _ = _contract_period("SR3Z2", ref)
    gap_days = (start_z2 - end_u2).days
    assert abs(gap_days) <= 1, f"unexpected gap of {gap_days} days between consecutive quarterly contracts"
