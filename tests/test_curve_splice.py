"""Bloomberg long-end splice of the SOFR-futures curve (synthetic data, no network)."""
import math
from datetime import date, timedelta

import pandas as pd
import pytest

from capitolis_pricers.curves import zero_curve
from risk_engine.market import bloomberg as bbg
from risk_engine.market.sofr import extend_long_end

REF = date(2026, 8, 28)


def _fut_curve():
    return zero_curve(REF, [1, 3, 6], [0.040, 0.041, 0.042])


def _fake_bbg(monkeypatch):
    tenors = ["5Y", "6Y", "7Y", "10Y", "20Y", "30Y"]
    zr = [0.042, 0.0425, 0.043, 0.045, 0.048, 0.047]
    yrs = [5, 6, 7, 10, 20, 30]
    df = pd.DataFrame({"tenor": tenors, "zero_rate": zr,
                       "discount_factor": [math.exp(-z * t) for z, t in zip(zr, yrs)]})
    monkeypatch.setattr(bbg, "available", lambda: True)
    monkeypatch.setattr(bbg, "load_usd_bloomberg_zero_curve", lambda: df)
    return dict(zip(yrs, zr))


def _z(c, y):
    return c.zero_rate(REF + timedelta(days=round(y * 365)))


def test_inside_the_futures_range_is_unchanged(monkeypatch):
    _fake_bbg(monkeypatch)
    old, new = _fut_curve(), extend_long_end(_fut_curve())
    for y in (0.5, 2, 4, 6):
        assert _z(new, y) == pytest.approx(_z(old, y), abs=1e-12)


def test_flat_extrapolation_is_replaced_by_bloomberg_shape(monkeypatch):
    _fake_bbg(monkeypatch)
    old, new = _fut_curve(), extend_long_end(_fut_curve())
    assert _z(old, 20) == pytest.approx(0.042)          # flat
    assert _z(new, 20) > 0.046                          # follows Bloomberg's upward slope
    assert _z(new, 20) > _z(new, 10) > _z(new, 7)


def test_continuous_at_the_join_and_forwards_match_bloomberg(monkeypatch):
    _fake_bbg(monkeypatch)
    new = extend_long_end(_fut_curve())
    eps = 1e-4
    assert abs(_z(new, 6 + eps) - _z(new, 6 - eps)) < 1e-5
    # forward between 10y and 20y equals Bloomberg's (levels differ at the join, forwards do not)
    d = lambda y: new.discount(REF + timedelta(days=round(y * 365)))
    fwd = math.log(d(10) / d(20)) / 10
    assert fwd == pytest.approx((0.048 * 20 - 0.045 * 10) / 10, abs=2e-4)


def test_falls_back_to_the_futures_curve_without_bloomberg(monkeypatch):
    monkeypatch.setattr(bbg, "available", lambda: False)
    c = _fut_curve()
    assert extend_long_end(c) is c
