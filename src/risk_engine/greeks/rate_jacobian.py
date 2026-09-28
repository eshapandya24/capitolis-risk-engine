"""
Par-instrument (Jacobian) rate sensitivities: bump the curve's own NATIVE
construction pillars (the actual SOFR-futures-implied and Bloomberg-spliced
points in usd_curve._t / ._lndf -- see market/sofr.py) rather than a
synthetic zero-rate grid.

Why this is different from greeks/bumps.py's bump_curve(): that function
applies a triangular perturbation on 8 hand-chosen tenors (0.25y..30y) to
the FITTED zero curve. It's a reasonable key-rate grid, but it is not tied
to how the curve was actually built, and it is coarse in exactly the region
(20-30y) that matters most for this book's dominant position, the 2049
bond forward. Bumping the curve's own ~45 native pillars instead is the
textbook Jacobian sensitivity: the same kind of thing a rates desk gets by
bumping each of its curve-building instruments (futures, swaps) one at a
time and re-bootstrapping.

Two things this module gives:
  1. jacobian_zero_to_pillar(curve, report_tenors): the deterministic (no
     Monte Carlo) matrix d(zero rate at each report tenor) / d(each native
     pillar's own zero rate), by finite difference on the curve's own
     interpolation. No simulation needed; this alone shows how local (or
     not) each report-bucket tenor actually is in instrument space.
  2. bump_curve_native_pillars(curve, pillar_indices, shift): bump ONLY the
     chosen native pillars (by `shift`, an absolute zero-rate shift) and let
     the curve's own interpolation fill in between -- no invented weighting
     function. bucket_native_pillars(curve, report_tenors) partitions every
     native pillar (except t=0) to its nearest report tenor, so bumping one
     bucket at a time reprices with an EXACT partition of the curve (bucket
     deltas sum exactly to the parallel delta), and reusing the exposure
     Greeks' own resimulation gives a genuine par-bucket DV01.
"""
import math

import numpy as np


def bucket_native_pillars(curve, report_tenors):
    """{report_tenor: [pillar_index, ...]} assigning every native pillar with
    t > 0 to its nearest report tenor (ties to the lower tenor)."""
    tenors = np.asarray(report_tenors, dtype=float)
    out = {t: [] for t in report_tenors}
    for i, t in enumerate(curve._t):
        if t <= 0:
            continue
        j = int(np.argmin(np.abs(tenors - t)))
        out[report_tenors[j]].append(i)
    return out


def bump_curve_native_pillars(curve, pillar_indices, shift):
    """Copy of `curve` with an absolute zero-rate shift `shift` applied at
    exactly the given native pillar indices (ln DF(t_i) -= shift * t_i),
    left untouched everywhere else; the curve's own (linear-in-ln-DF)
    interpolation determines the shape in between and beyond, exactly as a
    real curve rebuild would after moving one quoted instrument."""
    from capitolis_pricers.curves import Curve
    idx = set(pillar_indices)
    lndf = [y - (shift * t if i in idx else 0.0) for i, (t, y) in enumerate(zip(curve._t, curve._lndf))]
    return Curve(curve.ref_date, list(curve._t), [math.exp(v) for v in lndf], basis=curve.basis)


def jacobian_zero_to_pillar(curve, report_tenors, eps=1e-4):
    """Deterministic (t, pillar) matrix: d(zero rate at report tenor t) /
    d(zero rate bump at native pillar), by central finite difference,
    reading zero rates off the bumped curve's own interpolation. No
    simulation -- this is a curve-construction property, not a model one."""
    from datetime import timedelta
    n_pillars = len(curve._t)
    rows = []
    for i in range(n_pillars):
        if curve._t[i] <= 0:
            rows.append([0.0] * len(report_tenors))
            continue
        up = bump_curve_native_pillars(curve, [i], eps)
        dn = bump_curve_native_pillars(curve, [i], -eps)
        row = []
        for t in report_tenors:
            d = curve.ref_date + timedelta(days=round(365.25 * t))
            row.append((up.zero_rate(d) - dn.zero_rate(d)) / (2 * eps))
        rows.append(row)
    return np.array(rows)  # (n_pillars, n_report_tenors)
