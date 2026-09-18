"""
Regression tests for the MOF JGB yield history loader (market/mof_jgb.py)
and the JGB-based JPY mean-reversion calibration attempt
(models/hw_calibration.calibrate_jpy_mean_reversion_from_jgb_yields).
Hits the real MOF endpoint -- skipped automatically if unreachable, same
pattern as the project's other real-data tests.
"""
import pytest


def _mof_reachable():
    try:
        from risk_engine.market.mof_jgb import fetch_jgb_yield_history
        fetch_jgb_yield_history(use_cache=True)
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _mof_reachable(), reason="MOF JGB endpoint not reachable")


def test_jgb_history_spans_expected_range_and_tenors():
    from risk_engine.market.mof_jgb import fetch_jgb_yield_history, TENOR_COLUMNS
    df = fetch_jgb_yield_history()
    assert len(df) > 10000, "expected ~50 years of daily observations since 1974"
    assert df.index.min().year <= 1975
    assert list(df.columns) == TENOR_COLUMNS
    # decimal, not percent
    assert df["10Y"].dropna().abs().max() < 0.20


def test_jgb_yield_realized_vol_rises_with_tenor():
    """The core empirical finding this loader exists to surface: JPY's
    realized yield vol RISES with tenor (opposite of USD's decay), robust
    across lookback windows -- corroborating the Bloomberg swaption cube's
    finding with a completely independent, much longer real dataset. This
    is what makes exp(-a*tenor) calibration structurally unusable for JPY,
    not a one-off data glitch."""
    import numpy as np
    from risk_engine.market.mof_jgb import fetch_jgb_yield_history

    df = fetch_jgb_yield_history()
    end = df.index.max()
    import pandas as pd
    start = end - pd.DateOffset(years=3)
    window = df[(df.index > start) & (df.index <= end)]

    short_vol = window["1Y"].dropna().diff().dropna().std()
    long_vol = window["30Y"].dropna().diff().dropna().std()
    assert long_vol > short_vol, (
        f"expected 30Y realized vol ({long_vol}) > 1Y realized vol ({short_vol}) -- "
        f"if this flips, JPY's term structure shape may have changed and the "
        f"calibration fallback logic in calibration.py should be revisited")


def test_calibrate_jpy_mean_reversion_from_jgb_yields_runs():
    from datetime import date
    from risk_engine.models.hw_calibration import calibrate_jpy_mean_reversion_from_jgb_yields
    result = calibrate_jpy_mean_reversion_from_jgb_yields(date(2026, 8, 28))
    assert "a" in result and "sigma_from_fit" in result
    assert len(result["points"]) >= 3


def test_calibrate_jpy_mean_reversion_from_jgb_yields_gives_negative_a():
    """Locks in the actual finding (not just that the function runs): the
    fit's `a` comes out negative/invalid, consistent with the rising-vol
    shape above. If real JPY market dynamics genuinely shift so this
    becomes usable, this test should be revisited deliberately."""
    from datetime import date
    from risk_engine.models.hw_calibration import calibrate_jpy_mean_reversion_from_jgb_yields
    result = calibrate_jpy_mean_reversion_from_jgb_yields(date(2026, 8, 28))
    assert result["a"] < 0, f"expected the JGB-based fit to reproduce the known-invalid negative a, got {result['a']}"


def test_calibrate_jpy_mean_reversion_from_jgb_yields_raises_on_too_short_history():
    from datetime import date
    from risk_engine.models.hw_calibration import calibrate_jpy_mean_reversion_from_jgb_yields
    with pytest.raises(ValueError):
        calibrate_jpy_mean_reversion_from_jgb_yields(date(1974, 10, 1), lookback_years=1)
