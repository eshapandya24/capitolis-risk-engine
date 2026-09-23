"""
Exposure on the close-out-window convention Capitolis specified (kickoff
deck slides 8-9), as opposed to the level exposure in aggregate.py.

Slide 9, verbatim: "Assume collected/posted variation margin on a given
date in the simulation is the NPV of the trade on the prior day on the
path. Because the counterparty defaults, variation margin discontinues
over the close out period and exposure is how much it MOVES from the NPV
on t-1."

So, per scenario and per reporting date t:

    VM(t)        = V(t - 1bd)                  -- last margin call before default,
                                                  SIGNED (a negative NPV means we
                                                  posted, not collected)
    exposure(t)  = max( V(t + 10bd) - VM(t), 0 )

and slide 8's metrics on top of that: EE = mean over scenarios, PFE = 99th
percentile, MPE = peak of the PFE curve. Slide 8 also requires these "per
trade and aggregated up to the counterparty level", so every function here
returns both.

Difference from collateral.py: that module floors collateral at zero
(max(V(t) - threshold, 0)), which models a one-way CSA where we only ever
RECEIVE margin. Slide 9 describes two-way variation margin at the full
prior-day NPV, so VM here is signed and there is no threshold.

INTERIM MODE (prev_node is None): the t-1bd leg needs grid nodes one
business day BEFORE each reporting date, which a grid built by
build_time_grid(mpor_days=...) does not contain -- it has the reporting
node and the +10bd look-ahead, nothing before. Passing prev_node=None
substitutes V(t) for V(t-1bd), which is the same quantity one business day
later. That is NOT the specified number: it omits one day of market move,
so it understates exposure slightly and is biased low. It exists so the
profile's SHAPE can be read off an already-cached run without a reprice.
Anything reported to Capitolis must come from a run with real t-1bd nodes.
"""
import numpy as np

CLOSE_OUT_BUSINESS_DAYS = 10  # slide 9: "Use a 10-day close out period"


def _net_npv(npv, trade_idx):
    """Net NPV across a set of trades: (n_nodes, n_scenarios)."""
    return npv[trade_idx, :, :].sum(axis=0)


def window_exposure(net_npv, node_map, prev_node=None, side="pos"):
    """exposure(t) = max( V(t+10bd) - V(t_prev), 0 ) for each reporting node.

    net_npv : (n_nodes, n_scenarios) netted NPV on the full simulation grid
    node_map: {reporting_i: {"reporting": j, "lookahead": k or None}}
    prev_node: {reporting_i: node index of t-1bd}, or None for INTERIM mode
               (see module docstring -- substitutes the reporting node,
               which biases exposure low by one business day of move).

    side: "pos" (default) is the exposure to the counterparty,
    max(V(t+10bd) - VM, 0); "neg" is the mirror image, the counterparty's
    exposure to us, max(VM - V(t+10bd), 0), used for DVA and funding benefit.

    Returns (n_reporting, n_scenarios).
    """
    n_reporting = len(node_map)
    out = np.zeros((n_reporting, net_npv.shape[1]))
    for i in range(n_reporting):
        mapping = node_map[i] if i in node_map else node_map[str(i)]
        reporting_node = mapping["reporting"]
        lookahead_node = mapping["lookahead"]

        # last margin call before default: SIGNED prior-day NPV
        prev_idx = reporting_node if prev_node is None else prev_node[i]
        vm = net_npv[prev_idx, :]

        if lookahead_node is None:
            # no room for a +10bd node before the book's horizon (the final
            # reporting dates) -- the close-out window would run past the
            # last trade's maturity, so there is no further move to capture
            v_close_out = net_npv[reporting_node, :]
        else:
            v_close_out = net_npv[lookahead_node, :]

        move = v_close_out - vm
        out[i, :] = np.maximum(move if side == "pos" else -move, 0.0)
    return out


def _live_trade_idx(trade_ids, trade_idx, trade_expiry, window_start, window_end,
                     exclude_maturing):
    """Trades to include for one window. exclude_maturing drops any trade
    settling inside [window_start, window_end] from BOTH legs, so a
    scheduled settlement (NPV -> 0) doesn't read as a market move against
    us. The alternative (exclude_maturing=False) lets that drop count as
    exposure, which overstates it: the cash actually settles."""
    if not exclude_maturing:
        return trade_idx
    keep = []
    for i in trade_idx:
        exp = trade_expiry.get(trade_ids[i])
        if exp is not None and window_start <= exp <= window_end:
            continue
        keep.append(i)
    return keep


def exposure_by_trade(trade_ids, npv, node_map, prev_node=None, trade_expiry=None,
                      exclude_maturing=False, dates=None):
    """Slide 8's per-trade leg: {trade_id: (n_reporting, n_scenarios)}.

    With exclude_maturing the same rule as the counterparty level applies: a
    window in which the trade settles contributes zero (its scheduled NPV
    drop to zero is a cash settlement, not a market move) -- so per-trade and
    per-counterparty profiles are on the same footing."""
    out = {}
    for i, tid in enumerate(trade_ids):
        arr = window_exposure(npv[[i], :, :].sum(axis=0), node_map, prev_node)
        if exclude_maturing:
            exp = trade_expiry.get(tid)
            for r in range(len(node_map)):
                mapping = node_map[r] if r in node_map else node_map[str(r)]
                la = mapping["lookahead"]
                w_start = dates[prev_node[r] if prev_node is not None else mapping["reporting"]]
                w_end = dates[la if la is not None else mapping["reporting"]]
                if exp is not None and w_start <= exp <= w_end:
                    arr[r, :] = 0.0
        out[tid] = arr
    return out


def exposure_by_counterparty(trade_ids, trade_counterparty, npv, node_map,
                              prev_node=None, trade_expiry=None,
                              exclude_maturing=False, dates=None, side="pos"):
    """Slide 8's netting-set leg: {counterparty: (n_reporting, n_scenarios)}.

    Netting is applied BEFORE the max(.,0), which is the whole point of a
    netting set -- a negative NPV on one trade genuinely offsets a positive
    one to the same counterparty.
    """
    cptys = sorted(set(trade_counterparty[tid] for tid in trade_ids))
    out = {}
    for cpty in cptys:
        idx = [i for i, tid in enumerate(trade_ids) if trade_counterparty[tid] == cpty]
        if not exclude_maturing:
            out[cpty] = window_exposure(_net_npv(npv, idx), node_map, prev_node, side)
            continue

        # maturity exclusion is per-window, so the trade set changes by node
        n_reporting = len(node_map)
        exposure = np.zeros((n_reporting, npv.shape[2]))
        for i in range(n_reporting):
            mapping = node_map[i] if i in node_map else node_map[str(i)]
            la = mapping["lookahead"]
            w_start = dates[prev_node[i] if prev_node is not None else mapping["reporting"]]
            w_end = dates[la if la is not None else mapping["reporting"]]
            live = _live_trade_idx(trade_ids, idx, trade_expiry, w_start, w_end, True)
            if not live:
                continue
            single = {0: mapping}
            exposure[i, :] = window_exposure(_net_npv(npv, live), single, None
                                              if prev_node is None else {0: prev_node[i]}, side)[0, :]
        out[cpty] = exposure
    return out


def summarize(exposure_array, confidence=0.99, horizon_mask=None):
    """Slide 8's metrics: EE(t), PFE(t) at `confidence`, MPE = peak PFE.
    horizon_mask (bool per reporting node) restricts MPE / peak EE to the
    one-year horizon slide 8 asks for; the full profiles are returned too."""
    ee = exposure_array.mean(axis=1)
    pfe = np.quantile(exposure_array, confidence, axis=1)
    m = np.ones(len(pfe), dtype=bool) if horizon_mask is None else np.asarray(horizon_mask, dtype=bool)
    return {"EE": ee,
            "MedianExposure": np.quantile(exposure_array, 0.5, axis=1),
            "PFE": pfe,
            "MPE": float(np.max(pfe[m])),
            "EE_max": float(np.max(ee[m]))}
