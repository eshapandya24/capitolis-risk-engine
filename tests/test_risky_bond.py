"""Risky-bond sample trade and issuer credit in the simulation (synthetic, no network)."""
from datetime import date

import numpy as np

from capitolis_pricers.credit import CreditCurve
from capitolis_pricers.curves import flat_curve
from capitolis_pricers.market import MarketState
from capitolis_pricers.pricers import BondForwardTrade
from risk_engine.simulation.engine import SimulationEngine
from tests.test_jpy_factor import _calib

REF = date(2026, 8, 28)
TN, SP = [0.5, 1, 3, 5, 10], [0.008, 0.009, 0.011, 0.013, 0.015]


def _trade():
    t = BondForwardTrade.from_terms(dict(issue_date="3/1/2026", maturity_date="3/1/2031", coupon=0.05, frequency_months=6,
                                         day_count="30/360", face=100.0, issuer="SAMPLE_BBB_CORP"),
                                    forward_date="2/26/2027", strike_clean=100.0, position="long", notional=25e6)
    t.counterparty = "CPTY_S"
    return t


def _mkt(credit):
    return MarketState(ref_date=REF, reporting_ccy="USD", discount_curves={"USD": flat_curve(REF, 0.042)}, credit_curves=credit)


def test_issuer_credit_lowers_a_long_forward_and_scales_with_spread():
    t = _trade()
    rf = t.npv(_mkt({}))
    risky = t.npv(_mkt({"SAMPLE_BBB_CORP": CreditCurve(REF, TN, SP, 0.4)}))
    wide = t.npv(_mkt({"SAMPLE_BBB_CORP": CreditCurve(REF, TN, [2 * s for s in SP], 0.4)}))
    assert risky < rf and wide < risky
    assert rf - wide > 1.6 * (rf - risky)


def test_engine_passes_issuer_credit_to_the_pricer_at_every_node():
    calib = _calib(with_jpy=False)
    calib["issuer_spreads"] = {"SAMPLE_BBB_CORP": (TN, SP, 0.4)}
    t = _trade()
    kw = dict(method="pseudo_random", n_scenarios=40, seed=1)
    e_r = SimulationEngine(calib, {"T": t}, **kw)
    e_f = SimulationEngine(dict(calib, issuer_spreads=None), {"T": t}, **kw)
    npv_r = e_r.price_one_scenario(e_r.simulate_paths(), 0)
    npv_f = e_f.price_one_scenario(e_f.simulate_paths(), 0)
    active = np.isfinite(npv_r[0]) & (np.abs(npv_f[0]) > 0)
    assert active.any()
    assert (npv_r[0][active] < npv_f[0][active]).all()
