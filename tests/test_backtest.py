"""Kupiec / Christoffersen tests and the rolling backtests (synthetic data, no network)."""
import numpy as np
import pandas as pd
import pytest
from scipy import stats

from risk_engine.validation import backtest as B


def test_kupiec_matches_the_textbook_statistic():
    # 4 exceptions in 250 at 99%
    x, n, p = 4, 250, 0.01
    lr = -2 * (246 * np.log(0.99) + 4 * np.log(0.01)) + 2 * (246 * np.log(1 - 4 / 250) + 4 * np.log(4 / 250))
    got = B.kupiec_pof(x, n, p)
    assert got["lr"] == pytest.approx(lr, rel=1e-12)
    assert got["p_value"] == pytest.approx(1 - stats.chi2.cdf(lr, 1), rel=1e-12)
    assert got["expected"] == pytest.approx(2.5)


def test_kupiec_zero_exceptions_and_exact_rate_edge_cases():
    z = B.kupiec_pof(0, 100, 0.01)                       # 0 ln 0 handled
    assert np.isfinite(z["lr"]) and z["lr"] == pytest.approx(-2 * 100 * np.log(0.99))
    assert B.kupiec_pof(1, 100, 0.01)["lr"] == pytest.approx(0.0, abs=1e-12)   # exactly the expected rate
    assert B.kupiec_pof(0, 0, 0.01)["n"] == 0


def test_kupiec_rejects_a_model_that_is_far_off():
    assert B.kupiec_pof(15, 200, 0.01)["p_value"] < 1e-4
    assert B.kupiec_pof(2, 200, 0.01)["p_value"] > 0.05


def test_christoffersen_flags_clustered_exceptions():
    clustered = np.zeros(200, dtype=int)
    clustered[50:60] = 1
    spread = np.zeros(200, dtype=int)
    spread[::20] = 1
    assert B.christoffersen_independence(clustered)[1] < 0.01
    assert B.christoffersen_independence(spread)[1] > 0.05


def _synthetic_prices(n=1500, vol=0.20, seed=3):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2018-01-01", periods=n)
    lp = pd.DataFrame({"A": np.cumsum(rng.normal(0, vol / np.sqrt(252), n)) + np.log(100.0),
                       "B": np.cumsum(rng.normal(0, vol / np.sqrt(252), n)) + np.log(50.0)}, index=idx)
    lfx = pd.Series(np.log(150.0) + np.cumsum(rng.normal(0, 0.08 / np.sqrt(252), n)), index=idx)
    return lp, lfx


def test_equity_backtest_is_calibrated_when_the_model_is_right():
    """Data generated from the model's own world (constant vol, independent
    names): exception rates near nominal and Kupiec does not reject."""
    lp, lfx = _synthetic_prices(n=3500)
    res = B.equity_book_backtest(lp, lfx, {"A": 1000.0, "B": -800.0}, {"A": False, "B": False},
                                 window=504, n_draws=8000)
    for c in (0.95, 0.99):
        s = B.summarize_hits(res[c]["hits"], c)
        assert s["n"] > 250
        assert s["pass_5pct"], (c, s)


def test_equity_backtest_rejects_a_model_that_understates_vol():
    """Vol triples after the calibration window: exceptions explode, Kupiec rejects at 99%."""
    lp, lfx = _synthetic_prices(n=2600)
    rng = np.random.default_rng(9)
    shock = np.zeros(len(lp))
    shock[1500:] = rng.normal(0, 0.40 / np.sqrt(252), len(lp) - 1500)
    lp = lp + np.cumsum(shock)[:, None]
    res = B.equity_book_backtest(lp, lfx, {"A": 1000.0, "B": 500.0}, {"A": False, "B": False},
                                 window=504, n_draws=8000)
    assert B.summarize_hits(res[0.99]["hits"], 0.99)["p_value"] < 0.05


def test_jpy_name_is_valued_through_usdjpy():
    """A JPY-quoted name whose local price is flat but whose currency moves must show a USD move."""
    idx = pd.bdate_range("2020-01-01", periods=1400)
    rng = np.random.default_rng(1)
    lp = pd.DataFrame({"J": np.full(len(idx), np.log(3000.0))}, index=idx)
    lfx = pd.Series(np.log(110.0) + np.cumsum(rng.normal(0, 0.10 / np.sqrt(252), len(idx))), index=idx)
    res = B.equity_book_backtest(lp, lfx, {"J": 10.0}, {"J": True}, window=504, n_draws=5000)
    assert np.abs(res[0.99]["real"]).max() > 0.0


def test_rates_backtest_detects_an_understated_sigma():
    rng = np.random.default_rng(4)
    n, sig_true, a = 3600, 0.0090, 0.0167
    dy = rng.normal(0, sig_true / np.sqrt(252), n)
    y = pd.Series(0.04 + np.cumsum(dy), index=pd.bdate_range("2010-01-01", periods=n))
    f5 = (1 - np.exp(-a * 5)) / (a * 5)
    sd_true = B.hw_yield_move_sd(sig_true, a, 5.0)
    assert sd_true == pytest.approx(sig_true * np.sqrt(10 / 252) * f5, rel=0.01)
    ok = B.rates_backtest(y, 5.0, lambda t: sig_true / f5, a, window=504)
    low = B.rates_backtest(y, 5.0, lambda t: 0.0063, a, window=504)
    up_ok = B.summarize_hits(ok[0.99]["up"], 0.99)
    up_low = B.summarize_hits(low[0.99]["up"], 0.99)
    assert up_ok["pass_5pct"] and up_low["rate"] > up_ok["rate"]
    assert not B.summarize_hits(low[0.95]["up"], 0.95)["pass_5pct"]
