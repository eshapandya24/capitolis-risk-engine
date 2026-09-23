"""
DVA and FVA on top of the unilateral CVA in cva.py (extra-credit xVA).

With V the netting-set value to us, D the pathwise discount factor, and
EPE = E[D max(V,0)], ENE = E[D max(-V,0)] the discounted expected positive
and negative exposures:

    CVA = LGD_cpty * sum 0.5 (EPE_{i-1} + EPE_i) * PD_cpty(t_{i-1}, t_i)
    DVA = LGD_own  * sum 0.5 (ENE_{i-1} + ENE_i) * PD_own (t_{i-1}, t_i)
    FCA = sum s_f(t_i) dt_i * 0.5 (EPE_{i-1} + EPE_i)      funding cost of positive exposure
    FBA = sum s_f(t_i) dt_i * 0.5 (ENE_{i-1} + ENE_i)      funding benefit of negative exposure
    FVA = FCA - FBA

Own credit (DVA) and the funding spread are ASSUMPTIONS: no Capitolis CDS or
bond spreads are available. Own credit is proxied by a rating bucket (BBB by
default) through the same bond-index spread curves used for counterparties, and
the funding spread is set equal to that curve (the standard symmetric
assumption). If the funding spread equals the own credit spread, FBA and DVA
capture the same economic benefit; report `total_no_overlap` (CVA - DVA + FCA)
for that reason. Independence of exposure and default is assumed throughout,
as for CVA.

The exposure arrays can be on either exposure definition (level max(V,0), or
the brief's close-out max(V(t+10bd) - V(t-1bd), 0)); the caller decides.
"""
import numpy as np

from ..models.credit import LGD, marginal_pd, spread_at


def _trap(profile):
    """Interval averages 0.5 (x_{i-1} + x_i), length n-1."""
    p = np.asarray(profile, dtype=float)
    return 0.5 * (p[:-1] + p[1:])


def dva(dene, times, own_tenors, own_spreads, lgd=LGD):
    """DVA from a discounted expected negative exposure profile."""
    pd_ = marginal_pd(times, own_tenors, own_spreads, lgd)
    return float(lgd * np.sum(_trap(dene) * pd_))


def funding_cost(dee, times, fund_tenors, fund_spreads):
    """FCA: funding spread times discounted EPE, integrated over time."""
    t = np.asarray(times, dtype=float)
    dt = np.diff(t)
    s = spread_at(fund_tenors, fund_spreads, 0.5 * (t[:-1] + t[1:]))
    return float(np.sum(s * dt * _trap(dee)))


def xva_summary(dee, dene, times, cpty_curve, own_curve, fund_curve=None, lgd_cpty=LGD, lgd_own=LGD):
    """All xVA terms for one netting set. Curves are (tenors, spreads).
    fund_curve defaults to own_curve (funding spread = own credit spread)."""
    from .cva import cva as _cva
    fund_curve = own_curve if fund_curve is None else fund_curve
    c = _cva(dee, times, cpty_curve[0], cpty_curve[1], lgd_cpty)
    d = dva(dene, times, own_curve[0], own_curve[1], lgd_own)
    fca = funding_cost(dee, times, fund_curve[0], fund_curve[1])
    fba = funding_cost(dene, times, fund_curve[0], fund_curve[1])
    return {"CVA": c, "DVA": d, "FCA": fca, "FBA": fba, "FVA": fca - fba,
            "bilateral_CVA": c - d, "total": c - d + (fca - fba), "total_no_overlap": c - d + fca}
