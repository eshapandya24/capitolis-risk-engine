"""Stress scenario helpers (synthetic data, no network)."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from capitolis_pricers.curves import zero_curve
from risk_engine.stress import scenarios as S

REF = date(2026, 8, 28)


def test_shift_curve_moves_zero_rates_by_the_interpolated_shift():
    c = zero_curve(REF, [1, 5, 10, 20, 30], [0.04] * 5)
    up = S.shift_curve(c, [1.0, 30.0], [0.02, 0.02])
    from datetime import timedelta
    for y in (1, 5, 20):
        d = REF + timedelta(days=round(365 * y))
        assert up.zero_rate(d) - c.zero_rate(d) == pytest.approx(0.02, abs=1e-9)
    twist = S.shift_curve(c, [1.0, 10.0], [0.0, 0.01])
    d5, d10 = REF + timedelta(days=5 * 365), REF + timedelta(days=10 * 365)
    assert twist.zero_rate(d10) - c.zero_rate(d10) == pytest.approx(0.01, abs=1e-9)
    assert 0 < twist.zero_rate(d5) - c.zero_rate(d5) < 0.01


def test_hypothetical_scenarios_cover_equity_fx_rates_and_combinations():
    sc = {s["name"]: s for s in S.hypothetical(["A", "B"])}
    assert sc["EQ_DOWN_30"]["eq"] == {"A": -0.30, "B": -0.30} and sc["EQ_DOWN_30"]["dy"] is None
    assert sc["RATES_UP_200"]["dy"][1][0] == pytest.approx(0.02)
    assert sc["FLIGHT_TO_QUALITY"]["dy"][1][0] < 0 and sc["FLIGHT_TO_QUALITY"]["eq"]["A"] < 0
    assert sc["STAGFLATION"]["dy"][1][0] > 0 and sc["STAGFLATION"]["eq"]["A"] < 0


def _history(n=400, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-01", periods=n)
    px = pd.DataFrame({k: 100 * np.exp(np.cumsum(rng.normal(0, 0.008, n))) for k in ("A", "B", "C")}, index=idx)
    fx = pd.Series(110 * np.exp(np.cumsum(rng.normal(0, 0.004, n))), index=idx)
    cmt = pd.DataFrame({c: 0.03 + np.cumsum(rng.normal(0, 0.0005, n)) for c in ("DGS3MO", "DGS1", "DGS2", "DGS5", "DGS10", "DGS30")}, index=idx)
    return px, fx, cmt


def test_historical_windows_pick_the_planted_extremes():
    px, fx, cmt = _history()
    px.iloc[200:210] = px.iloc[200:210].values * np.linspace(1, 0.6, 10)[:, None]         # crash in every name
    px.iloc[210:] = px.iloc[210:].values * 0.6
    fx.iloc[300:310] = fx.iloc[300:310].values * np.linspace(1, 0.85, 10)
    fx.iloc[310:] = fx.iloc[310:].values * 0.85
    cmt.iloc[100:110, :] = cmt.iloc[100:110].values + np.linspace(0, 0.03, 10)[:, None]
    cmt.iloc[110:] = cmt.iloc[110:].values + 0.03
    ws = {w["name"]: w for w in S.historical_windows(px, fx, cmt, ["A", "B", "C", "D"])}
    assert px.index.get_loc(pd.Timestamp(ws["HIST_EQUITY_CRASH"]["window"][0])) in range(195, 206)
    assert ws["HIST_EQUITY_CRASH"]["eq"]["A"] < -0.2
    assert ws["HIST_EQUITY_CRASH"]["eq"]["D"] == pytest.approx(np.median([ws["HIST_EQUITY_CRASH"]["eq"][k] for k in "ABC"]))   # missing name -> median
    assert ws["HIST_RATES_SPIKE"]["dy"][1][tuple(ws["HIST_RATES_SPIKE"]["dy"][0]).index(10)] > 0.02
    assert ws["HIST_YEN_SURGE"]["fx"] < -0.1
