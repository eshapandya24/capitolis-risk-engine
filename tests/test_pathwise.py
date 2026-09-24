"""Pathwise equity/FX deltas of close-out exposure against bump-and-reprice on a
synthetic linear book (no network)."""
from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from risk_engine.exposure import spec_exposure as spec
from risk_engine.greeks.pathwise import pathwise_deltas

REF = date(2026, 8, 28)


class _Pos:
    def __init__(self, isin, shares, currency):
        self.isin, self.shares, self.currency = isin, shares, currency


def _setup(n=6000, seed=1):
    """Two trades, one counterparty: a USD name (receive equity) and a JPY name (pay equity)."""
    rng = np.random.default_rng(seed)
    n_nodes = 9                                    # reporting nodes at 1, 4, 7 with prev = node-1, lookahead = node+1
    dts = 10 / 252
    s_us = 100 * np.exp(np.cumsum(rng.normal(0, 0.25 * np.sqrt(dts), (n, n_nodes)), axis=1) - 0.5 * 0.25 ** 2 * dts)
    s_jp = 3000 * np.exp(np.cumsum(rng.normal(0, 0.30 * np.sqrt(dts), (n, n_nodes)), axis=1))
    x = 150 * np.exp(np.cumsum(rng.normal(0, 0.10 * np.sqrt(dts), (n, n_nodes)), axis=1))
    paths = {"ln_spot": {"US": np.log(s_us), "JP": np.log(s_jp)}, "ln_fx": np.log(x)}
    t1 = SimpleNamespace(direction="receive_equity", positions=[_Pos("US", 1000.0, "USD")])
    t2 = SimpleNamespace(direction="pay_equity", positions=[_Pos("JP", 40000.0, "JPY")])
    trades = {"T1": t1, "T2": t2}
    dates = [REF + timedelta(days=i) for i in range(n_nodes)]
    eng = SimpleNamespace(node_map={k: {"reporting": r, "lookahead": r + 1, "prev": r - 1} for k, r in enumerate((1, 4, 7))},
                          dates=dates, trades=trades, trade_counterparty={"T1": "C", "T2": "C"},
                          trade_expiries={"T1": REF + timedelta(days=1000), "T2": REF + timedelta(days=1000)})
    ids = ["T1", "T2"]

    def npv_of(sp, xx):
        v1 = 1000.0 * sp["US"]
        v2 = -40000.0 * sp["JP"] / xx
        return np.stack([v1.T, v2.T])              # (trades, nodes, N)

    return eng, paths, ids, npv_of, np.exp


def _ee(eng, ids, npv):
    prev = {i: m["prev"] for i, m in eng.node_map.items()}
    by = spec.exposure_by_counterparty(ids, eng.trade_counterparty, npv, eng.node_map, prev_node=prev,
                                       trade_expiry=eng.trade_expiries, exclude_maturing=True, dates=eng.dates)["C"]
    return by.mean(axis=1)


def test_pathwise_ee_deltas_match_central_bumps_of_the_same_paths():
    eng, paths, ids, npv_of, _ = _setup()
    sp = {k: np.exp(v) for k, v in paths["ln_spot"].items()}
    xx = np.exp(paths["ln_fx"])
    npv = npv_of(sp, xx)
    res = pathwise_deltas(eng, paths, ids, npv, keep_nodes=[0, 1, 2])
    h = 0.01
    for name in ("US", "JP"):
        up = dict(sp); up[name] = sp[name] * (1 + h)
        dn = dict(sp); dn[name] = sp[name] * (1 - h)
        bump = 0.5 * (_ee(eng, ids, npv_of(up, xx)) - _ee(eng, ids, npv_of(dn, xx)))
        assert np.allclose(res["equity"]["C"][name]["EE"], bump, rtol=0.03, atol=2.0), (name, res["equity"]["C"][name]["EE"], bump)
    bump_fx = 0.5 * (_ee(eng, ids, npv_of(sp, xx * (1 + h))) - _ee(eng, ids, npv_of(sp, xx * (1 - h))))
    assert np.allclose(res["fx"]["C"]["EE"], bump_fx, rtol=0.03, atol=2.0)


def test_pathwise_quantile_deltas_are_finite_and_have_the_right_sign_for_a_long_position():
    eng, paths, ids, npv_of, _ = _setup()
    sp = {k: np.exp(v) for k, v in paths["ln_spot"].items()}
    npv = npv_of(sp, np.exp(paths["ln_fx"]))
    res = pathwise_deltas(eng, paths, ids, npv, keep_nodes=[0, 1, 2], window=0.03)
    us = res["equity"]["C"]["US"]
    assert np.isfinite(us["PFE"]).all() and (us["EE"] > 0).all()
    assert (us["PFE"] > 0).all()                 # tail scenarios are those where the long US position gained


def test_expired_trades_contribute_no_gradient_after_maturity():
    """T1 matures after node 2; at the later windows its NPV is zero, so pathwise must give
    zero for its name, in agreement with a bump of the same paths."""
    eng, paths, ids, npv_of, _ = _setup()
    eng.trade_expiries["T1"] = REF + timedelta(days=2)
    sp = {k: np.exp(v) for k, v in paths["ln_spot"].items()}
    xx = np.exp(paths["ln_fx"])

    def npv_alive(spots, fxx):
        n = npv_of(spots, fxx)
        n[0, 3:, :] = 0.0                                   # T1 is worth nothing once expired
        return n

    npv = npv_alive(sp, xx)
    res = pathwise_deltas(eng, paths, ids, npv, keep_nodes=[0, 1, 2])
    up, dn = dict(sp), dict(sp)
    up["US"], dn["US"] = sp["US"] * 1.01, sp["US"] * 0.99
    bump = 0.5 * (_ee(eng, ids, npv_alive(up, xx)) - _ee(eng, ids, npv_alive(dn, xx)))
    assert np.allclose(res["equity"]["C"]["US"]["EE"], bump, rtol=0.03, atol=2.0)
    assert res["equity"]["C"]["US"]["EE"][2] == 0.0          # reporting node 2 window starts after expiry
