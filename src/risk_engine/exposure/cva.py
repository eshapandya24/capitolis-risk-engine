"""
Regulatory CVA (Basel MAR50.32) for an uncollateralized netting set:

    CVA = LGD * sum_i  0.5 * [ DEE(t_{i-1}) + DEE(t_i) ] * PD(t_{i-1}, t_i)

where DEE(t) = E[ D(t) * max(V(t), 0) ] is the expected DISCOUNTED exposure
(D = pathwise risk-free discount factor from the simulated short rate) and
PD comes from the (proxy) credit-spread curve. Unilateral: the bank is
assumed default-free (no DVA); exposure and default are independent (no
wrong-way risk), both disclosed simplifications.
"""
import numpy as np

from ..models.credit import LGD, marginal_pd


def path_discount_factors(x_rate, times, hw):
    """D(t_k) along each path: exp(-trapezoid integral of r), r = x + alpha(t).
    x_rate: (n_scen, n_nodes). Returns (n_scen, n_nodes) with D(t_0)=1."""
    times = np.asarray(times, dtype=float)
    alpha = np.array([hw.alpha(t) for t in times])
    r = x_rate + alpha[None, :]
    dt = np.diff(times)
    incr = 0.5 * (r[:, :-1] + r[:, 1:]) * dt[None, :]
    return np.exp(-np.concatenate([np.zeros((r.shape[0], 1)), np.cumsum(incr, axis=1)], axis=1))


def discounted_ee(exposure, disc):
    """exposure, disc: (n_nodes, n_scen) and (n_scen, n_nodes) -> DEE (n_nodes,)."""
    return (exposure * disc.T).mean(axis=1)


def cva(dee, times, tenors, spreads, lgd=LGD):
    """Regulatory CVA from a discounted-EE profile on `times` (times[0] = 0)."""
    pd_ = marginal_pd(times, tenors, spreads, lgd)
    return float(lgd * np.sum(0.5 * (dee[:-1] + dee[1:]) * pd_))
