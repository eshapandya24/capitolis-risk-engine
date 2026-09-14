"""
Tests for the Bloomberg-data-backed calibration additions
(market/bloomberg.py, models/hw_calibration.calibrate_mean_reversion_
from_swaptions, market/fx.build_fx_curve, models/calibration.
implied_jpy_usd_rate_diff_from_bloomberg).

All skipped automatically if the Bloomberg data export
(data/raw/bloomberg/) isn't present -- it's a one-time local file the user
provided, not something a fresh clone or CI environment has. Where a test
also needs a live Databento curve (build_fx_curve needs `usd_curve`), it's
marked separately so the Bloomberg-only tests still run without network.
"""
import math
import os

import pytest

from risk_engine.market.bloomberg import available as bbg_available

pytestmark = pytest.mark.skipif(not bbg_available(), reason="Bloomberg data export not present")


def test_swaption_vol_cube_loads_and_is_sane():
    from risk_engine.market.bloomberg import load_usd_swaption_vols
    cube = load_usd_swaption_vols()
    assert "1M" in cube.index
    assert "1Y" in cube.columns
    # ATM normal vols should be small positive decimals (tens of bp), not
    # raw bp integers (a unit-conversion bug would show up as ~50-90 here
    # instead of ~0.005-0.009)
    v = cube.loc["1M", "1Y"]
    assert 0.001 < v < 0.02, f"1M1Y vol {v} looks like a units bug (expected ~0.5-2%)"


def test_swaption_based_hw_calibration_is_sane():
    from risk_engine.models.hw_calibration import calibrate_mean_reversion_from_swaptions
    result = calibrate_mean_reversion_from_swaptions(expiry="1M", max_tenor_years=15)
    assert result["a"] > 0, "mean reversion should be positive (vol should decay with tenor, not grow)"
    assert result["r_squared"] > 0.5, f"weak exponential-decay fit: R^2={result['r_squared']}"
    assert result["method"] == "swaption_atm_normal_vol_term_structure"


def test_jpy_usd_differential_from_bloomberg_curves_is_positive_and_plausible():
    """USD rates are well above JPY rates in this dataset (USD SOFR ~4%,
    JPY OIS ~1.5% at 1Y) -- the differential should be a real positive
    number in a plausible range, not near-zero (which would suggest a
    units or sign bug) and not implausibly large (>10%, a different kind
    of bug)."""
    from risk_engine.models.calibration import implied_jpy_usd_rate_diff_from_bloomberg
    diff = implied_jpy_usd_rate_diff_from_bloomberg(tenor="12M")
    assert 0.005 < diff < 0.10, f"differential {diff} outside plausible range"


def test_jpy_usd_differential_cross_validates_against_forward_points():
    """Two INDEPENDENT real Bloomberg data series -- the zero curves and
    the separately-quoted forward points -- should roughly agree on the
    implied rate differential via covered interest parity. Large
    disagreement would mean one series has a units/scale bug."""
    from risk_engine.models.calibration import implied_jpy_usd_rate_diff_from_bloomberg
    from risk_engine.market.bloomberg import load_usdjpy_forward_points, load_usdjpy_spot

    diff_from_curves = implied_jpy_usd_rate_diff_from_bloomberg(tenor="12M")

    points = load_usdjpy_forward_points()
    spot = load_usdjpy_spot()
    forward_12m = spot + points["12M"]
    diff_from_forwards = -math.log(forward_12m / spot) / 1.0

    assert abs(diff_from_curves - diff_from_forwards) < 0.01, (
        f"Zero-curve differential ({diff_from_curves:.4%}) and forward-points differential "
        f"({diff_from_forwards:.4%}) disagree by more than 100bp -- check for a units bug")


@pytest.mark.skipif(os.environ.get("DATABENTO_API_KEY") is None,
                     reason="build_fx_curve also needs a live USD curve (Databento)")
def test_fx_forward_curve_exactly_reproduces_quoted_points():
    """The whole point of build_fx_curve's implied-JPY-curve construction:
    FxCurve.forward(T) must reproduce the REAL quoted forward at every
    tenor used to build it, by construction (not an approximation)."""
    from datetime import date, timedelta
    from risk_engine.market.sofr import fetch_raw, build_curve
    from risk_engine.market.fx import build_fx_curve, fetch_forward_points
    from risk_engine.market.bloomberg import load_usdjpy_spot
    from capitolis_pricers.daycount import add_months

    ref = date(2026, 8, 28)
    raw = fetch_raw(ref)
    usd_curve = build_curve(ref, raw_df=raw)
    fx_curve = build_fx_curve(ref, usd_curve)

    points = fetch_forward_points()
    spot = load_usdjpy_spot()
    months_map = {"1M": 1, "2M": 2, "3M": 3, "6M": 6, "12M": 12}
    for tenor, months in months_map.items():
        d = add_months(ref, months)
        expected = spot + points[tenor]
        actual = fx_curve.forward(d)
        assert math.isclose(actual, expected, rel_tol=1e-6), (
            f"{tenor}: expected {expected}, got {actual}")
