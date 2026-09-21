"""
Book Greeks at t=0 (deterministic, no simulation): for every trade and
netting set, delta and gamma to each equity (per 1% relative spot move),
FX delta/gamma (USDJPY, per 1%), and interest-rate DV01 (per +1bp) both
parallel and bucketed at key tenors, plus rate gamma (parallel). Central
finite differences on the SAME pricers the simulation uses.

    delta = [NPV(+h) - NPV(-h)] / 2        (change per +1% / +1bp)
    gamma =  NPV(+h) - 2 NPV(0) + NPV(-h)  (change in delta per 1% / 1bp)
"""
import numpy as np

from capitolis_pricers.curves import FxCurve
from capitolis_pricers.market import MarketState

from .bumps import DEFAULT_TENORS, bump_curve


def _market(calib, curve, eq_spots, fx_spot):
    return MarketState(ref_date=calib["ref_date"], reporting_ccy="USD", discount_curves={"USD": curve},
                       equity_spots=eq_spots, equity_dividend_rates=calib["dividends"],
                       fx_curves={("USD", "JPY"): FxCurve("USD", "JPY", fx_spot, curve)})


def _npvs(trades, market):
    return {tid: t.npv(market, reporting=True) for tid, t in trades.items()}


def book_greeks(calib, trades, eq_shift=0.01, fx_shift=0.01, rate_shift=1e-4, tenors=DEFAULT_TENORS):
    """Returns {"npv": {tid: v}, "equity": {isin: {"delta": {tid: v}, "gamma": {tid: v}}},
    "fx": {...}, "rate": {"parallel": {...}, "buckets": {tenor: {tid: dv01}}, "gamma": {tid: v}}}."""
    hw = calib["hw"]
    curve = hw.fast_node_curve(calib["ref_date"], 0.0, hw.short_rate0())
    spots, fx = dict(calib["equity_spots"]), calib["fx_spot"]
    base = _npvs(trades, _market(calib, curve, spots, fx))
    out = {"npv": base, "equity": {}, "fx": {}, "rate": {"buckets": {}}}

    for isin in spots:
        up = _npvs(trades, _market(calib, curve, {**spots, isin: spots[isin] * (1 + eq_shift)}, fx))
        dn = _npvs(trades, _market(calib, curve, {**spots, isin: spots[isin] * (1 - eq_shift)}, fx))
        out["equity"][isin] = {"delta": {t: (up[t] - dn[t]) / 2 for t in base},
                               "gamma": {t: up[t] - 2 * base[t] + dn[t] for t in base}}
    up = _npvs(trades, _market(calib, curve, spots, fx * (1 + fx_shift)))
    dn = _npvs(trades, _market(calib, curve, spots, fx * (1 - fx_shift)))
    out["fx"] = {"delta": {t: (up[t] - dn[t]) / 2 for t in base}, "gamma": {t: up[t] - 2 * base[t] + dn[t] for t in base}}

    # rate curves: bump the exact curve pillars of the t=0 curve object's base curve
    base_curve = hw.base_curve
    up = _npvs(trades, _market(calib, bump_curve(base_curve, None, rate_shift), spots, fx))
    dn = _npvs(trades, _market(calib, bump_curve(base_curve, None, -rate_shift), spots, fx))
    b0 = _npvs(trades, _market(calib, base_curve, spots, fx))
    out["rate"]["parallel"] = {t: (up[t] - dn[t]) / 2 for t in base}
    out["rate"]["gamma"] = {t: up[t] - 2 * b0[t] + dn[t] for t in base}
    for k in tenors:
        u = _npvs(trades, _market(calib, bump_curve(base_curve, k, rate_shift, tenors), spots, fx))
        d = _npvs(trades, _market(calib, bump_curve(base_curve, k, -rate_shift, tenors), spots, fx))
        out["rate"]["buckets"][k] = {t: (u[t] - d[t]) / 2 for t in base}
    return out


def netting_set_totals(values, trade_counterparty):
    """Sum a {trade_id: value} dict to {counterparty: value} plus '__portfolio__'."""
    out = {}
    for t, v in values.items():
        out[trade_counterparty[t]] = out.get(trade_counterparty[t], 0.0) + v
    out["__portfolio__"] = float(sum(values.values()))
    return out
