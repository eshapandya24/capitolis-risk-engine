"""Tests for the Greeks machinery (no network): bump helpers, t=0 book
Greeks against analytic values on a synthetic trade, exposure measures."""
from datetime import date, timedelta

import numpy as np
import pytest

from capitolis_pricers.curves import flat_curve
from risk_engine.greeks.book import book_greeks, netting_set_totals
from risk_engine.greeks.bumps import DEFAULT_TENORS, bump_curve
from risk_engine.greeks.exposure import apply_rows, diff_measures, measures
from risk_engine.models.rates import HullWhite1F

REF = date(2026, 8, 28)


class _Trade:
    """Linear toy trade: 1,000 shares of EQ1 minus 5,000,000 paid in one year,
    plus 1e5 USD-per-JPY-unit FX exposure. Counterparty CPTY_X."""
    counterparty = "CPTY_X"

    def npv(self, market, reporting=False):
        df = market.discount("USD").discount(REF + timedelta(days=365))
        return 1000.0 * market.equity_spot("EQ1") - 5_000_000.0 * df + 1e5 * market.fx("USD", "JPY")


def _calib():
    hw = HullWhite1F(flat_curve(REF, 0.04), sigma=0.006, a=0.02)
    return {"hw": hw, "ref_date": REF, "equity_spots": {"EQ1": 100.0}, "dividends": {"EQ1": 0.0}, "fx_spot": 150.0}


def test_bucket_bumps_partition_the_parallel_bump():
    c = flat_curve(REF, 0.03)
    par = bump_curve(c, None, 1e-4)
    parts = [bump_curve(c, k, 1e-4) for k in DEFAULT_TENORS]
    for i in range(len(c._t)):
        total = sum(p._lndf[i] - c._lndf[i] for p in parts)
        assert total == pytest.approx(par._lndf[i] - c._lndf[i], abs=1e-12)


def test_parallel_bump_moves_zero_rate_by_exactly_the_shift():
    c = flat_curve(REF, 0.03)
    up = bump_curve(c, None, 1e-4)
    d = REF + timedelta(days=730)
    assert up.zero_rate(d) - c.zero_rate(d) == pytest.approx(1e-4, abs=1e-10)


def test_book_greeks_match_analytic_values_for_a_linear_trade():
    calib = _calib()
    g = book_greeks(calib, {"T": _Trade()})
    assert g["equity"]["EQ1"]["delta"]["T"] == pytest.approx(1000.0 * 100.0 * 0.01, rel=1e-9)  # per +1%
    assert g["equity"]["EQ1"]["gamma"]["T"] == pytest.approx(0.0, abs=1e-6)                  # linear
    assert g["fx"]["delta"]["T"] == pytest.approx(1e5 * 150.0 * 0.01, rel=1e-9)
    df1 = np.exp(-0.04 * 365 / 365.0)
    assert g["rate"]["parallel"]["T"] == pytest.approx(5_000_000.0 * df1 * 1e-4, rel=2e-3)     # DV01
    # bucketed DV01s add up to the parallel DV01
    assert sum(b["T"] for b in g["rate"]["buckets"].values()) == pytest.approx(g["rate"]["parallel"]["T"], rel=1e-3)


def test_netting_set_totals_add_up():
    out = netting_set_totals({"a": 1.0, "b": 2.0, "c": 4.0}, {"a": "X", "b": "X", "c": "Y"})
    assert out == {"X": 3.0, "Y": 4.0, "__portfolio__": 7.0}


def test_measures_ordering_and_diff():
    rng = np.random.default_rng(0)
    npv = rng.normal(2.0, 5.0, size=(2, 3, 4000))
    m = measures(["a", "b"], {"a": "X", "b": "X"}, npv, [0, 1, 2])
    x = m["X"]
    assert (x["MED"] <= x["PFE"]).all() and (x["EE"] <= x["PFE"]).all()
    d = diff_measures(m, m)
    assert all(abs(v).max() == 0 for v in d["X"].values())


def test_apply_rows_replaces_only_the_repriced_trades():
    base = np.zeros((3, 2, 4))
    out = apply_rows(base, [1], np.ones((1, 2, 4)))
    assert out[1].sum() == 8 and out[0].sum() == 0 and out[2].sum() == 0 and base.sum() == 0
