"""
Sensitivities of the EXPOSURE measures (EE, median PFE, PFE99) to risk
factors, by netting set and for the portfolio, at every reporting date --
"Greeks across scenarios" (Capitolis project objective 3).

Method: bump-and-reprice with COMMON RANDOM NUMBERS (same seed, same
Latin Hypercube draws in base and bumped runs), so the difference is
sensitivity, not Monte Carlo noise. Two mechanisms, chosen for efficiency:

  * Equity and FX spots: a bump of S0 rescales every simulated path exactly
    (GBM drift does not depend on the spot level), so NO re-simulation is
    needed: the existing paths are re-used with spots multiplied, and ONLY
    the trades that hold the bumped factor are repriced (the other trades'
    NPVs are unchanged). Cost per name is a fraction of one full reprice.
  * Interest-rate curve and all volatility bumps change the paths
    themselves (short-rate alpha(t), drift, dispersion), so they need a
    re-simulation with the bumped calibration and the same random numbers.

delta = [M(+h) - M(-h)] / 2 (per +1% / +1bp); gamma = M(+h) - 2 M + M(-h);
vega = M(sigma*1.01) - M (per +1% relative vol), M in {EE, median PFE, PFE99}.
"""
import numpy as np

from ..exposure.aggregate import netted_exposure_by_counterparty

CONF = 0.99
ENTITIES = ("CPTY_A", "CPTY_B", "CPTY_C", "__portfolio__")


def measures(trade_ids, trade_counterparty, npv, node_idx, conf=CONF):
    """{entity: {"EE","MED","PFE"}: arrays over the reporting nodes}."""
    exp = netted_exposure_by_counterparty(trade_ids, trade_counterparty, np.nan_to_num(npv))
    exp = {c: a[node_idx, :] for c, a in exp.items()}
    exp["__portfolio__"] = sum(exp[c] for c in sorted(exp))
    return {c: {"EE": a.mean(1), "MED": np.quantile(a, 0.5, axis=1), "PFE": np.quantile(a, conf, axis=1)}
            for c, a in exp.items()}


class CloseOut:
    """Context for measuring exposure on the brief's definition,
    max(V(t+10bd) - V(t-1bd), 0), from an engine built with mpor_days and
    vm_lag_days (see exposure/spec_exposure.py). `keep` is the list of
    reporting dates (indices into the node map) within `horizon_days` of the
    reference date; all measures are returned on those dates only."""

    def __init__(self, engine, ref_date, horizon_days=365):
        from datetime import date as _d
        self.node_map = engine.node_map
        self.dates = engine.dates
        self.trade_expiry = dict(engine.trade_expiries)
        self.prev = {i: (m["prev"] if m["prev"] is not None else m["reporting"])
                     for i, m in engine.node_map.items()}
        self.reporting_idx = [engine.node_map[i]["reporting"] for i in range(len(engine.node_map))]
        self.keep = [i for i, r in enumerate(self.reporting_idx)
                     if (engine.dates[r] - ref_date).days <= horizon_days]

    def report_dates(self):
        return [self.dates[self.reporting_idx[i]] for i in self.keep]


def measures_closeout(trade_ids, trade_counterparty, npv, ctx, conf=CONF):
    """Like `measures`, on the close-out exposure of `ctx` (CloseOut)."""
    from ..exposure import spec_exposure as spec
    by = spec.exposure_by_counterparty(trade_ids, trade_counterparty, np.nan_to_num(npv), ctx.node_map,
                                       prev_node=ctx.prev, trade_expiry=ctx.trade_expiry,
                                       exclude_maturing=True, dates=ctx.dates)
    exp = {c: a[ctx.keep, :] for c, a in by.items()}
    exp["__portfolio__"] = sum(exp[c] for c in sorted(exp))
    return {c: {"EE": a.mean(1), "MED": np.quantile(a, 0.5, axis=1), "PFE": np.quantile(a, conf, axis=1)}
            for c, a in exp.items()}


def apply_rows(base_npv, rows, arr):
    """Copy of base_npv with the repriced trade rows replaced."""
    out = base_npv.copy()
    out[rows] = arr
    return out


def diff_measures(a, b, scale=1.0):
    """(a - b) * scale for every entity and measure."""
    return {c: {m: (a[c][m] - b[c][m]) * scale for m in a[c]} for c in a}
