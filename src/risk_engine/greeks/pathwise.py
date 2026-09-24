"""
Pathwise (likelihood-free) equity and FX deltas of the close-out exposure
measures: the fast alternative to bump-and-reprice.

Why it is possible here. An equity TRS is LINEAR in the equity spots: its NPV
is  dir * sum_i shares_i * (S_i,ccy - basis_i DF) - funding, so
d NPV / d S_i,0 = dir * shares_i * (dS_i(t)/dS_i,0) (/X(t) for a JPY name),
and under GBM dS_i(t)/dS_i,0 = S_i(t)/S_i,0 on every path. The exposure is
max(V(t+10bd) - V(t-1bd), 0), so per scenario

    d exposure / d S_i,0 = 1{exposure > 0} * dir * shares_i
                           * [ S_i(t+10bd)/X(.) - S_i(t-1bd)/X(.) ] / S_i,0 .

Averaging over scenarios gives the delta of EE with NO repricing at all; the
delta of a quantile is the same gradient averaged over the scenarios that sit
at that quantile (a kernel window around the rank). For USDJPY the same holds
with d(S/X)/dX_0 = -(S/X)/X_0.

This is exact for EE and noisy for the median and PFE99 (a local average of a
few dozen scenarios), which is why the report uses bump-and-reprice with
common random numbers as the reference and pathwise as the fast cross-check
for equity and FX. It does not apply to rates (the trades are not linear in
the curve; that would need differentiating the pricers, i.e. adjoint
differentiation, which the black-box pricer library does not offer).

All deltas are per +1% of the factor, in USD, matching greeks/exposure.py.
"""
import numpy as np

from ..exposure import spec_exposure as spec


def _position_values(engine, paths, trade, isin_filter=None):
    """{isin: (n_scen, n_nodes) signed USD value of the trade's position in that
    name} (dir * shares * S / X for JPY names). Equity TRS only."""
    sign = 1.0 if trade.direction == "receive_equity" else -1.0
    x = np.exp(paths["ln_fx"])
    out = {}
    for p in trade.positions:
        if isin_filter is not None and p.isin not in isin_filter:
            continue
        s = np.exp(paths["ln_spot"][p.isin])
        out[p.isin] = sign * p.shares * s / (x if p.currency == "JPY" else 1.0)
    return out


def _windows(engine, keep_nodes):
    nm = engine.node_map
    for i in keep_nodes:
        m = nm[i]
        prev = m["prev"] if m["prev"] is not None else m["reporting"]
        la = m["lookahead"] if m["lookahead"] is not None else m["reporting"]
        yield i, prev, la, engine.dates[prev], engine.dates[la]


def pathwise_deltas(engine, paths, ids, npv, keep_nodes, window=0.02, isins=None):
    """Pathwise equity deltas (per +1% of each name) and FX delta (per +1% USDJPY)
    of the close-out EE, median and PFE99, by counterparty, at the reporting
    nodes `keep_nodes` (indices into engine.node_map).

    Returns {"equity": {cpty: {isin: {"EE","MED","PFE": arrays}}},
             "fx": {cpty: {"EE","MED","PFE"}}}.
    `window` is the half-width, in rank probability, of the kernel used for the
    median and PFE99 gradients."""
    npv = np.nan_to_num(npv)
    cpm = engine.trade_counterparty
    trades = engine.trades
    texp = dict(engine.trade_expiries)
    pos_vals = {tid: _position_values(engine, paths, trades[tid], isins) for tid in ids if hasattr(trades[tid], "positions")}
    jpy_names = {tid: {p.isin for p in trades[tid].positions if p.currency == "JPY"} for tid in pos_vals}
    x0 = float(np.exp(paths["ln_fx"][0, 0]))
    n_scen = npv.shape[2]
    out = {"equity": {}, "fx": {}}
    cptys = sorted(set(cpm[t] for t in ids))
    for c in cptys:
        idx = [i for i, t in enumerate(ids) if cpm[t] == c]
        names = sorted({n for i in idx if ids[i] in pos_vals for n in pos_vals[ids[i]]})
        if isins is not None:
            names = [n for n in names if n in isins]
        eq_res = {n: {k: np.zeros(len(keep_nodes)) for k in ("EE", "MED", "PFE")} for n in names}
        fx_res = {k: np.zeros(len(keep_nodes)) for k in ("EE", "MED", "PFE")}
        for j, (i, prev, la, w0, w1) in enumerate(_windows(engine, keep_nodes)):
            live = spec._live_trade_idx(ids, idx, texp, w0, w1, True)
            # a trade that matured before the window has NPV zero on both legs: no gradient
            live = [li for li in live if texp.get(ids[li]) is None or texp[ids[li]] >= w0]
            if not live:
                continue
            v = npv[live].sum(axis=0)
            move = v[la, :] - v[prev, :]
            expo = np.maximum(move, 0.0)
            ind = (move > 0).astype(float)
            order = np.argsort(expo)
            ranks = np.empty(n_scen)
            ranks[order] = (np.arange(n_scen) + 0.5) / n_scen
            masks = {"MED": np.abs(ranks - 0.5) <= window, "PFE": np.abs(ranks - 0.99) <= window}

            def reduce(grad):
                g = ind * grad
                return {"EE": float(g.mean()), "MED": float(g[masks["MED"]].mean()), "PFE": float(g[masks["PFE"]].mean())}

            fx_grad = np.zeros(n_scen)
            for n in names:
                grad = np.zeros(n_scen)
                for li in live:
                    tid = ids[li]
                    if tid in pos_vals and n in pos_vals[tid]:
                        pv = pos_vals[tid][n]
                        grad += pv[:, la] - pv[:, prev]
                for k, val in reduce(grad).items():
                    eq_res[n][k][j] = 0.01 * val
            for li in live:
                tid = ids[li]
                for n in jpy_names.get(tid, ()):
                    pv = pos_vals[tid][n]
                    fx_grad += -(pv[:, la] - pv[:, prev])          # d(S/X)/dX0 = -(S/X)/X0, times X0 * 1%
            for k, val in reduce(fx_grad).items():
                fx_res[k][j] = 0.01 * val
        out["equity"][c] = eq_res
        out["fx"][c] = fx_res
    return out
