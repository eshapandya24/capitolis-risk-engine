"""
Turns simulated NPVs (src/risk_engine/simulation/engine.py) into the actual
counterparty credit risk numbers: Expected Exposure (EE), Potential Future
Exposure (PFE) at a chosen confidence level, and Maximum PFE (MPE) --
netted by counterparty, using the same netting-set logic as
scripts/calculate_current_exposure.py (that script's Current Exposure is
exactly this module's EE(t=0), a cross-check both should agree on).
"""
import numpy as np


def netted_exposure_by_counterparty(trade_ids, trade_counterparty, npv):
    """npv: (n_trades, n_nodes, n_scenarios). Returns
    {counterparty: exposure_array (n_nodes, n_scenarios)} = max(net NPV, 0)."""
    cptys = sorted(set(trade_counterparty[tid] for tid in trade_ids))
    out = {}
    for cpty in cptys:
        idx = [i for i, tid in enumerate(trade_ids) if trade_counterparty[tid] == cpty]
        net_npv = npv[idx, :, :].sum(axis=0)  # (n_nodes, n_scenarios)
        out[cpty] = np.maximum(net_npv, 0.0)
    return out


def portfolio_exposure(exposure_by_cpty):
    """Total exposure across all counterparties (sum of each cpty's own
    netted exposure -- netting does NOT apply ACROSS counterparties, only
    within one, since that's the legal unit a netting agreement covers)."""
    cptys = list(exposure_by_cpty)
    stacked = np.stack([exposure_by_cpty[c] for c in cptys], axis=0)
    return stacked.sum(axis=0)


def expected_exposure(exposure_array):
    """EE(t) = mean exposure across scenarios, per time node."""
    return exposure_array.mean(axis=1)


def median_exposure(exposure_array):
    """Median (50th percentile) exposure per time node -- the typical
    scenario, vs. EE (the mean, pulled up by the right tail) and PFE (the
    tail)."""
    return np.quantile(exposure_array, 0.5, axis=1)


def potential_future_exposure(exposure_array, confidence=0.95):
    """PFE(t) at `confidence` = that percentile of the exposure distribution
    across scenarios, per time node."""
    return np.quantile(exposure_array, confidence, axis=1)


def maximum_pfe(pfe_curve):
    """MPE = peak of the PFE(t) curve across all time nodes."""
    return float(np.max(pfe_curve))


def build_profiles(trade_ids, trade_counterparty, npv, dates, confidence=0.95):
    """Full profile: EE(t)/PFE(t)/MPE per counterparty and for the book."""
    by_cpty = netted_exposure_by_counterparty(trade_ids, trade_counterparty, npv)
    portfolio = portfolio_exposure(by_cpty)

    profiles = {}
    for cpty, arr in by_cpty.items():
        ee = expected_exposure(arr)
        pfe = potential_future_exposure(arr, confidence)
        profiles[cpty] = {"dates": dates, "EE": ee, "MedianExposure": median_exposure(arr), "PFE": pfe, "MPE": maximum_pfe(pfe)}

    ee_p = expected_exposure(portfolio)
    pfe_p = potential_future_exposure(portfolio, confidence)
    profiles["__portfolio__"] = {"dates": dates, "EE": ee_p, "MedianExposure": median_exposure(portfolio), "PFE": pfe_p, "MPE": maximum_pfe(pfe_p)}
    return profiles
