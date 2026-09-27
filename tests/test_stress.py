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


def test_historical_window_in_range_only_looks_inside_the_given_dates():
    px, fx, cmt = _history()
    # two crashes: a bigger one outside the search range, a smaller one inside it
    px.iloc[50:60] = px.iloc[50:60].values * np.linspace(1, 0.5, 10)[:, None]
    px.iloc[60:] = px.iloc[60:].values * 0.5
    px.iloc[200:210] = px.iloc[200:210].values * np.linspace(1, 0.85, 10)[:, None]
    px.iloc[210:] = px.iloc[210:].values * 0.85
    start, end = px.index[190], px.index[230]
    sc = S.historical_window_in_range(px, fx, cmt, ["A", "B", "C"], start, end, "TEST", "test window")
    w0 = pd.Timestamp(sc["window"][0])
    assert start <= w0 <= end
    assert px.index.get_loc(w0) in range(195, 206)          # finds the smaller, in-range crash
    assert sc["eq"]["A"] < 0
    assert sc["n_names_with_data"] == 3 and sc["n_names_total"] == 3


def test_historical_window_in_range_returns_none_without_enough_data():
    px, fx, cmt = _history()
    sc = S.historical_window_in_range(px, fx, cmt, ["A"], "2019-01-01", "2019-01-05", "TEST", "no data here")
    assert sc is None


def test_crisis_windows_skips_episodes_the_data_cannot_support():
    px, fx, cmt = _history()  # starts 2020, so neither named crisis episode (2008, 2015) has any data
    assert S.crisis_windows(px, fx, cmt, ["A", "B", "C"]) == []


def test_crisis_windows_finds_a_planted_2008_crash():
    idx = pd.bdate_range("2007-06-01", periods=400)
    rng = np.random.default_rng(1)
    px = pd.DataFrame({k: 100 * np.exp(np.cumsum(rng.normal(0, 0.008, len(idx)))) for k in ("A", "B")}, index=idx)
    fx = pd.Series(110.0, index=idx)
    cmt = pd.DataFrame({"DGS10": 0.04}, index=idx)
    i0 = idx.get_loc(pd.Timestamp("2008-10-01"))
    px.iloc[i0:i0 + 10] = px.iloc[i0:i0 + 10].values * np.linspace(1, 0.6, 10)[:, None]
    px.iloc[i0 + 10:] = px.iloc[i0 + 10:].values * 0.6
    out = {s["name"]: s for s in S.crisis_windows(px, fx, cmt, ["A", "B"])}
    assert "HIST_GFC_2008" in out
    w0 = pd.Timestamp(out["HIST_GFC_2008"]["window"][0])
    assert pd.Timestamp("2008-09-15") <= w0 <= pd.Timestamp("2008-10-15")
    assert out["HIST_GFC_2008"]["eq"]["A"] < -0.2
    assert "HIST_CHINA_DEVAL_2015" not in out          # 2015 is outside this synthetic history
