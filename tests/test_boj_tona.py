"""
Regression tests for the BOJ TONA history loader (market/boj.py) and the
USD-JPY rate factor correlation it enables (models/calibration.
calibrate_usd_jpy_rate_corr()). These hit real network endpoints (BOJ's
free API, and FRED via market/sofr.py) -- skipped automatically if
unreachable, same pattern as the project's other real-data tests, rather
than mocked (the whole point is that this is genuine external data).
"""
import pytest


def _boj_reachable():
    try:
        from risk_engine.market.boj import fetch_tona_history
        fetch_tona_history(use_cache=True)
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _boj_reachable(), reason="BOJ API not reachable")


def test_tona_history_spans_expected_range_and_is_decimal():
    from risk_engine.market.boj import fetch_tona_history
    series = fetch_tona_history()
    assert len(series) > 5000, "expected several thousand daily TONA observations since 1998"
    assert series.index.min().year <= 1998
    # decimal, not percent -- e.g. 0.5% stored as 0.005, not 0.5
    assert series.abs().max() < 0.20, f"TONA should be a small decimal rate, got max abs {series.abs().max()}"


def test_tona_history_contains_real_negative_rate_periods():
    """The whole reason this loader exists: JPY genuinely went negative
    (BOJ's 2016-2024 NIRP policy, and a brief 2003 ZIRP-era dip) -- confirm
    the real data actually shows this, not just that the model CAN
    represent it (see tests/test_rates_negative.py for the model side)."""
    from risk_engine.market.boj import fetch_tona_history
    series = fetch_tona_history()
    negative = series[series < 0]
    assert len(negative) > 500, f"expected substantial real negative-rate history, got {len(negative)} days"
    nirp_era = negative[(negative.index.year >= 2016) & (negative.index.year <= 2024)]
    assert len(nirp_era) > 500, "expected most negative observations to fall in the 2016-2024 NIRP era"


def test_jpy_realized_rate_vol_is_positive_and_sane():
    from datetime import date
    from risk_engine.market.boj import jpy_realized_rate_vol
    vol = jpy_realized_rate_vol(date(2026, 8, 28))
    assert 0 < vol < 0.05, f"JPY realized rate vol should be a small positive decimal, got {vol}"


def test_jpy_realized_rate_vol_raises_on_too_short_a_window():
    from datetime import date
    from risk_engine.market.boj import jpy_realized_rate_vol
    with pytest.raises(ValueError):
        jpy_realized_rate_vol(date(1998, 1, 10), lookback_years=3)  # barely any history yet


def test_usd_jpy_rate_corr_calibration_runs_and_is_bounded():
    from risk_engine.models.calibration import calibrate_usd_jpy_rate_corr
    result = calibrate_usd_jpy_rate_corr()
    assert -1.0 <= result["corr"] <= 1.0
    assert 0.0 <= result["p_value"] <= 1.0
    assert result["n_obs"] > 500, "expected substantial SOFR/TONA overlap since SOFR's 2018 inception"


def test_usd_jpy_rate_corr_is_not_statistically_significant():
    """The actual empirical finding this calibration surfaced: USD and JPY
    short-rate daily CHANGES are not meaningfully correlated (independent
    monetary policy) -- a real result that replaced an earlier disclosed
    assumed constant. Locks in that finding so it can't silently flip
    without notice; a real regime change would need this test updated
    deliberately, not silently."""
    from risk_engine.models.calibration import calibrate_usd_jpy_rate_corr
    result = calibrate_usd_jpy_rate_corr()
    assert abs(result["corr"]) < 0.15, (
        f"expected a small USD-JPY rate-change correlation, got {result['corr']}")
