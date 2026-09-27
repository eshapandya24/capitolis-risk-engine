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
    KVA = CoC * sum 0.5 (K_{i-1} + K_i) dt_i,   K(t) = capital_ratio * RW * alpha * EPE(t)

Own credit (DVA) and the funding spread are ASSUMPTIONS: no Capitolis CDS or
bond spreads are available. Own credit is proxied by a rating bucket (BBB by
default) through the same bond-index spread curves used for counterparties, and
the funding spread is set equal to that curve (the standard symmetric
assumption). If the funding spread equals the own credit spread, FBA and DVA
capture the same economic benefit; report `total_no_overlap` (CVA - DVA + FCA)
for that reason. Independence of exposure and default is assumed throughout,
as for CVA.

KVA is explicitly ILLUSTRATIVE/parametric, not a production number: it needs
a real capital methodology and Capitolis' own cost of capital, neither of
which is supplied. K(t) = capital_ratio * risk_weight * alpha * EPE(t) is the
simplest capital-charge proxy in the literature (capital_ratio=8% Basel
minimum, alpha=1.4 the standard EAD multiplier default, risk_weight=100% as a
placeholder), integrated (discounted) over the exposure profile and scaled
by an assumed cost of capital (CoC), swept over a small grid since no single
CoC is given. Reported alongside CVA/DVA/FVA as a fourth, clearly-labelled
XVA term (Report Section 8).

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


def kva(dee, times, cost_of_capital, capital_ratio=0.08, risk_weight=1.0, alpha=1.4):
    """Illustrative, parametric KVA from a discounted expected positive exposure
    profile: capital_ratio * risk_weight * alpha * EPE(t) is the capital charge
    K(t), discounted and trapezoid-integrated over the profile like the other
    xVA terms, then scaled by an assumed cost of capital. Not a production
    number (see module docstring)."""
    t = np.asarray(times, dtype=float)
    dt = np.diff(t)
    k = capital_ratio * risk_weight * alpha * np.asarray(dee, dtype=float)
    pv_capital_years = float(np.sum(dt * _trap(k)))
    return float(cost_of_capital * pv_capital_years)


def xva_summary(dee, dene, times, cpty_curve, own_curve, fund_curve=None, lgd_cpty=LGD, lgd_own=LGD,
                 cost_of_capital=None, capital_ratio=0.08, risk_weight=1.0, alpha=1.4):
    """All xVA terms for one netting set. Curves are (tenors, spreads).
    fund_curve defaults to own_curve (funding spread = own credit spread).
    KVA is included only if `cost_of_capital` is given (it has no data-based
    default; see module docstring)."""
    from .cva import cva as _cva
    fund_curve = own_curve if fund_curve is None else fund_curve
    c = _cva(dee, times, cpty_curve[0], cpty_curve[1], lgd_cpty)
    d = dva(dene, times, own_curve[0], own_curve[1], lgd_own)
    fca = funding_cost(dee, times, fund_curve[0], fund_curve[1])
    fba = funding_cost(dene, times, fund_curve[0], fund_curve[1])
    out = {"CVA": c, "DVA": d, "FCA": fca, "FBA": fba, "FVA": fca - fba,
           "bilateral_CVA": c - d, "total": c - d + (fca - fba), "total_no_overlap": c - d + fca}
    if cost_of_capital is not None:
        k = kva(dee, times, cost_of_capital, capital_ratio, risk_weight, alpha)
        out["KVA"] = k
        out["total_with_kva"] = out["total"] + k
        out["total_no_overlap_with_kva"] = out["total_no_overlap"] + k
    return out
