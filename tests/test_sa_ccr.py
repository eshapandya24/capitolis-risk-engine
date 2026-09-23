"""SA-CCR against hand calculations (no network)."""
import math
from datetime import date, timedelta

import pytest

from risk_engine.exposure import sa_ccr as S


def test_supervisory_duration_and_maturity_factor_by_hand():
    assert S.supervisory_duration(0.0, 10.0) == pytest.approx((1 - math.exp(-0.5)) / 0.05)
    assert S.supervisory_duration(-1.0, 5.0) == S.supervisory_duration(0.0, 5.0)     # S floored at 0
    assert S.maturity_factor(0.25) == pytest.approx(0.5)
    assert S.maturity_factor(7.0) == 1.0
    assert S.maturity_factor(0.0) == pytest.approx(math.sqrt(10 / 250))               # 10-business-day floor


def _ir(delta, notional, start, end, maturity, ccy="USD"):
    return {"currency": ccy, "delta": delta, "notional": notional, "start": start, "end": end, "maturity": maturity}


def test_ir_addon_single_trade():
    d = 100.0 * S.supervisory_duration(1.0, 6.0) * 1.0                                # bucket 3, MF = 1
    add, en = S.ir_addon([_ir(+1, 100.0, 1.0, 6.0, 1.0)])
    assert add == pytest.approx(0.005 * d) and en["USD"] == pytest.approx(d)


def test_ir_offsetting_trades_in_the_same_bucket_cancel_and_across_buckets_only_partly():
    same = S.ir_addon([_ir(+1, 100, 0, 3, 1), _ir(-1, 100, 0, 3, 1)])[0]
    assert same == pytest.approx(0.0, abs=1e-12)
    d1 = 100 * S.supervisory_duration(0, 0.5)
    d2 = 100 * S.supervisory_duration(0, 3.0)
    cross = S.ir_addon([_ir(+1, 100, 0, 0.5, 1), _ir(-1, 100, 0, 3.0, 1)])[0]
    assert cross == pytest.approx(0.005 * math.sqrt(d1 ** 2 + d2 ** 2 - 1.4 * d1 * d2))


def test_ir_currencies_are_separate_hedging_sets_and_add():
    a = S.ir_addon([_ir(+1, 100, 0, 3, 1, "USD"), _ir(-1, 100, 0, 3, 1, "JPY")])[0]
    assert a == pytest.approx(2 * 0.005 * 100 * S.supervisory_duration(0, 3))


def test_equity_addon_aggregation_by_hand():
    one = S.equity_addon([{"entity": "A", "delta": 1, "notional": 100.0, "maturity": 1.0}])[0]
    assert one == pytest.approx(0.32 * 100.0)
    two = S.equity_addon([{"entity": "A", "delta": 1, "notional": 100.0, "maturity": 1.0},
                          {"entity": "B", "delta": 1, "notional": 100.0, "maturity": 1.0}])[0]
    a = 32.0
    assert two == pytest.approx(math.sqrt((0.5 * 2 * a) ** 2 + 0.75 * 2 * a ** 2))
    # the same name long in one trade and short in another nets to zero
    net = S.equity_addon([{"entity": "A", "delta": 1, "notional": 100.0, "maturity": 1.0},
                          {"entity": "A", "delta": -1, "notional": 100.0, "maturity": 1.0}])[0]
    assert net == 0.0


def test_multiplier_limits():
    assert S.multiplier(0.0, 10.0) == 1.0
    assert S.multiplier(50.0, 10.0) == 1.0
    assert S.multiplier(-1e9, 10.0) == pytest.approx(0.05, abs=1e-6)
    assert S.multiplier(-10.0, 10.0) == pytest.approx(0.05 + 0.95 * math.exp(-10 / (2 * 0.95 * 10)))
    assert S.multiplier(-5.0, 0.0) == 1.0


def test_ead_combines_replacement_cost_and_pfe():
    ir = [_ir(+1, 1000.0, 0.5, 10.0, 0.5)]
    eq = [{"entity": "A", "delta": -1, "notional": 500.0, "maturity": 0.25}]
    r = S.ead(40.0, ir, eq)
    assert r["RC"] == 40.0 and r["multiplier"] == 1.0
    assert r["EAD"] == pytest.approx(1.4 * (40.0 + r["addon_ir"] + r["addon_equity"]))
    neg = S.ead(-1e6, ir, eq)
    assert neg["RC"] == 0.0 and neg["multiplier"] < 0.06 and neg["EAD"] < r["EAD"]
