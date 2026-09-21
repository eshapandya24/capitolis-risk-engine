"""Bump helpers shared by the exposure Greeks and the SA-CVA sensitivities."""
import copy

import numpy as np

DEFAULT_TENORS = (0.25, 0.5, 1, 2, 3, 5, 10, 30)


def bump_curve(curve, tenor_years, shift, tenors=DEFAULT_TENORS):
    """Zero-rate bump of `shift` (absolute, e.g. 1e-4) at one key tenor,
    triangular in maturity between neighbouring key tenors (flat beyond the
    end tenors). tenor_years=None bumps the whole curve in parallel."""
    from capitolis_pricers.curves import Curve
    ts = list(tenors)

    if tenor_years is None:
        def w(t):
            return 1.0
    else:
        k = ts.index(tenor_years)

        def w(t):
            if k > 0 and t < ts[k - 1]:
                return 0.0
            if t <= ts[k]:
                return 1.0 if k == 0 else (t - ts[k - 1]) / (ts[k] - ts[k - 1])
            if k == len(ts) - 1:
                return 1.0
            return max(0.0, (ts[k + 1] - t) / (ts[k + 1] - ts[k]))

    lndf = [y - w(t) * shift * t for t, y in zip(curve._t, curve._lndf)]
    return Curve(curve.ref_date, list(curve._t), [float(np.exp(y)) for y in lndf], basis=curve.basis)


def make_calib(calib, bump):
    """Copy of the calibration dict with ONE risk-factor bump applied.
    bump = ("base",) | ("ir_delta", tenor_or_None, shift) | ("ir_vega",) |
           ("fx_delta",) | ("fx_vega",) | ("eq_delta", isins) | ("eq_vega", isins)"""
    from ..models.rates import HullWhite1F
    c = dict(calib)
    kind = bump[0]
    if kind == "base":
        return c
    c["gbm"] = copy.deepcopy(calib["gbm"])
    hw = calib["hw"]
    if kind == "ir_delta":
        c["hw"] = HullWhite1F(bump_curve(calib["usd_curve"], bump[1], bump[2]), hw.sigma, hw.a)
    elif kind == "ir_vega":
        c["hw"] = HullWhite1F(calib["usd_curve"], hw.sigma * 1.01, hw.a)
    elif kind == "fx_delta":
        c["gbm"].spots0["FX_USDJPY"] = calib["gbm"].spots0["FX_USDJPY"] * 1.01
    elif kind == "fx_vega":
        c["gbm"].vols["FX_USDJPY"] = calib["gbm"].vols["FX_USDJPY"] * 1.01
    elif kind in ("eq_delta", "eq_vega"):
        for isin in bump[1]:
            if kind == "eq_delta":
                c["gbm"].spots0[isin] = calib["gbm"].spots0[isin] * 1.01
            else:
                c["gbm"].vols[isin] = calib["gbm"].vols[isin] * 1.01
    return c
