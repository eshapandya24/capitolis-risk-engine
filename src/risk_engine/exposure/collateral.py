"""
MPOR (Margin Period of Risk)-shifted exposure -- for a MARGINED
(collateralized) counterparty, if they default, close-out isn't
instantaneous: there's a real delay (industry standard ~10 business days
under Basel/ISDA SIMM) between the last collateral exchange and when the
position can actually be replaced. During that window the market can move
further against you, beyond what's already collateralized.

The current book (data/MARKET_DATA.md; trade_data/ carries no CSA/margin
terms) is treated as UNCOLLATERALIZED -- for an uncollateralized
counterparty there's no periodic margining process for MPOR to model a
delay around, so the plain (non-MPOR-shifted) exposure in
exposure/aggregate.py is the correct calculation, not this module. This
exists so the calculation is real, tested, and ready the moment actual CSA
terms are known for any counterparty -- not a stub.

Standard collateralized exposure at a reporting date t, using a look-ahead
date t+MPOR on the SAME simulated path (both computed by
simulation/engine.py's build_time_grid(mpor_days=...)):

    C(t)              = max(V(t) - threshold, 0)      -- collateral held,
                          based on the portfolio's value at t, net of an
                          uncollateralized threshold H
    Exposure_MPOR(t)   = max(V(t + MPOR) - C(t), 0)    -- what's owed at the
                          (delayed) close-out date, less what's already
                          collateralized

threshold=0 means full variation margin (every dollar of MTM is
collateralized) -- the exposure is then purely the potential MOVE over the
MPOR window, the cleanest way to see the MPOR effect in isolation.
threshold=inf recovers the uncollateralized case exactly (C(t) is always
0, so this reduces to max(V(t+MPOR), 0) -- still not identical to the plain
Exposure(t) in aggregate.py, since it's evaluated MPOR days later; use
aggregate.py directly for genuinely uncollateralized counterparties, not
this module with an infinite threshold).

Simplification disclosed, not hidden: no Minimum Transfer Amount (MTA) --
collateral is assumed to move in exact dollar amounts, not in the
real-world MTA-rounded increments (a small effect, second-order next to
the MPOR window itself).
"""
import numpy as np

DEFAULT_MPOR_DAYS = 10  # BUSINESS days: ISDA SIMM / Basel standard for margined bilateral OTC derivatives


def mpor_shifted_exposure_by_counterparty(trade_ids, trade_counterparty, npv, node_map, threshold=0.0):
    """npv: (n_trades, n_nodes, n_scenarios) -- from a SimulationEngine built
    WITH mpor_days set (so node_map has real lookahead indices, not None).
    Returns {counterparty: exposure array (n_reporting_nodes, n_scenarios)}."""
    cptys = sorted(set(trade_counterparty[tid] for tid in trade_ids))
    out = {}
    n_reporting = len(node_map)
    for cpty in cptys:
        idx = [i for i, tid in enumerate(trade_ids) if trade_counterparty[tid] == cpty]
        net_npv = npv[idx, :, :].sum(axis=0)  # (n_nodes, n_scenarios)

        exposure = np.zeros((n_reporting, net_npv.shape[1]))
        for report_i, mapping in node_map.items():
            reporting_node = mapping["reporting"]
            lookahead_node = mapping["lookahead"]
            v_t = net_npv[reporting_node, :]
            collateral = np.maximum(v_t - threshold, 0.0)
            if lookahead_node is None:
                # no room left for a look-ahead node before the horizon (last
                # reporting date) -- fall back to the un-shifted exposure
                v_future = v_t
            else:
                v_future = net_npv[lookahead_node, :]
            exposure[report_i, :] = np.maximum(v_future - collateral, 0.0)
        out[cpty] = exposure
    return out


def mpor_vs_uncollateralized_comparison(trade_ids, trade_counterparty, npv, node_map,
                                          reporting_dates, threshold=0.0, confidence=0.99):
    """Side-by-side EE/PFE: plain (uncollateralized-style, exposure AT each
    reporting node) vs MPOR-shifted (collateralized-style, exposure at
    reporting node + MPOR, net of collateral). Both computed from the SAME
    npv array/paths for a clean apples-to-apples comparison."""
    from .aggregate import expected_exposure, median_exposure, potential_future_exposure, maximum_pfe

    reporting_node_idx = {i: m["reporting"] for i, m in node_map.items()}
    cptys = sorted(set(trade_counterparty[tid] for tid in trade_ids))

    plain, mpor = {}, {}
    mpor_exposure = mpor_shifted_exposure_by_counterparty(trade_ids, trade_counterparty, npv, node_map, threshold)
    for cpty in cptys:
        idx = [i for i, tid in enumerate(trade_ids) if trade_counterparty[tid] == cpty]
        net_npv = npv[idx, :, :].sum(axis=0)
        plain_exposure_at_reporting = np.stack(
            [np.maximum(net_npv[reporting_node_idx[i], :], 0.0) for i in range(len(node_map))], axis=0)

        plain[cpty] = {"EE": expected_exposure(plain_exposure_at_reporting),
                        "MedianExposure": median_exposure(plain_exposure_at_reporting),
                        "PFE": potential_future_exposure(plain_exposure_at_reporting, confidence)}
        plain[cpty]["MPE"] = maximum_pfe(plain[cpty]["PFE"])

        mpor[cpty] = {"EE": expected_exposure(mpor_exposure[cpty]),
                      "MedianExposure": median_exposure(mpor_exposure[cpty]),
                      "PFE": potential_future_exposure(mpor_exposure[cpty], confidence)}
        mpor[cpty]["MPE"] = maximum_pfe(mpor[cpty]["PFE"])

    return {"dates": reporting_dates, "uncollateralized": plain, "mpor_shifted": mpor}
