"""Par-instrument (Jacobian) rate-curve helpers, on a synthetic curve (no network)."""
from datetime import date, timedelta

import numpy as np
import pytest

from capitolis_pricers.curves import zero_curve
from risk_engine.greeks.rate_jacobian import bucket_native_pillars, bump_curve_native_pillars, jacobian_zero_to_pillar

REF = date(2026, 8, 28)
PILLARS = [0.25, 0.5, 1, 2, 3, 5, 10, 20, 30]


def _curve():
    return zero_curve(REF, PILLARS, [0.03 + 0.001 * t for t in PILLARS])


def test_bumping_one_native_pillar_changes_only_nearby_zero_rates():
    c = _curve()
    up = bump_curve_native_pillars(c, [5], 0.01)  # pillar index 5 -> t=3 (index 0 is the curve's own t=0 anchor)
    for t in (3,):
        d = REF + timedelta(days=round(365.25 * t))
        assert up.zero_rate(d) - c.zero_rate(d) == pytest.approx(0.01, abs=2e-3)
    for t in (4.0, 2.5):     # strictly between the bumped pillar (3) and its neighbours (2, 5): interpolated, partial move
        d = REF + timedelta(days=round(365.25 * t))
        diff = up.zero_rate(d) - c.zero_rate(d)
        assert 0 < abs(diff) < 0.01
    for t in (0.25, 0.5, 1, 2, 5, 10, 20, 30):     # every OTHER pillar's own zero rate is untouched (exact lookup, not interpolation)
        d = REF + timedelta(days=round(365.25 * t))
        assert up.zero_rate(d) - c.zero_rate(d) == pytest.approx(0.0, abs=1e-6)


def test_bumping_every_pillar_together_is_a_parallel_shift():
    c = _curve()
    up = bump_curve_native_pillars(c, range(len(c._t)), 0.01)
    for t in PILLARS:
        d = REF + timedelta(days=round(365.25 * t))
        assert up.zero_rate(d) - c.zero_rate(d) == pytest.approx(0.01, abs=1e-6)


def test_bucket_native_pillars_partitions_every_pillar_exactly_once():
    c = _curve()
    report_tenors = (0.25, 0.5, 1, 2, 3, 5, 10, 30)
    buckets = bucket_native_pillars(c, report_tenors)
    all_idx = sorted(i for idxs in buckets.values() for i in idxs)
    expected = [i for i, t in enumerate(c._t) if t > 0]
    assert all_idx == expected            # every t>0 pillar assigned exactly once, t=0 excluded
    # each pillar goes to its nearest report tenor
    for t_rep, idxs in buckets.items():
        for i in idxs:
            t = c._t[i]
            assert min(report_tenors, key=lambda r: abs(r - t)) == t_rep


def test_bucketed_bumps_sum_to_the_parallel_bump():
    """Bumping each bucket's pillars separately and summing the zero-rate
    effect at a report tenor must reproduce the all-pillars parallel bump,
    since the buckets partition the pillars exactly."""
    c = _curve()
    report_tenors = (0.25, 0.5, 1, 2, 3, 5, 10, 30)
    buckets = bucket_native_pillars(c, report_tenors)
    d = REF + timedelta(days=round(365.25 * 3))
    total = 0.0
    for idxs in buckets.values():
        bumped = bump_curve_native_pillars(c, idxs, 0.0001)
        total += bumped.zero_rate(d) - c.zero_rate(d)
    parallel = bump_curve_native_pillars(c, range(len(c._t)), 0.0001)
    assert total == pytest.approx(parallel.zero_rate(d) - c.zero_rate(d), abs=1e-9)


def test_jacobian_rows_are_nonzero_only_near_their_own_pillar():
    c = _curve()
    report_tenors = (0.25, 0.5, 1, 2, 3, 5, 10, 30)
    J = jacobian_zero_to_pillar(c, report_tenors)
    assert J.shape == (len(c._t), len(report_tenors))
    # the pillar at t=3 (index 4) should load almost entirely on the report tenor 3
    i3 = 1 + PILLARS.index(3)   # +1 for the curve's own t=0 anchor at index 0
    j3 = report_tenors.index(3)
    row = J[i3]
    assert row[j3] == pytest.approx(1.0, abs=5e-3)
    assert np.sum(np.abs(row)) == pytest.approx(row[j3], abs=1e-3)


def test_jacobian_row_for_t0_pillar_is_zero():
    c = _curve()
    report_tenors = (0.25, 0.5, 1, 2, 3, 5, 10, 30)
    J = jacobian_zero_to_pillar(c, report_tenors)
    assert np.allclose(J[0], 0.0)   # curve._t[0] == 0.0, excluded by construction
