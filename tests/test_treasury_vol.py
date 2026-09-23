"""Hull-White sigma fit to realised long-end yield vols (synthetic, no network)."""
import numpy as np
import pandas as pd
import pytest

from risk_engine.market import treasury as T


def test_fit_recovers_sigma_from_model_consistent_vols():
    a, sigma = 0.0167, 0.009
    vols = {t: T.hw_yield_vol(sigma, a, t) for t in T.FIT_TENORS}
    assert T.fit_hw_sigma(a, vols) == pytest.approx(sigma, rel=1e-12)


def test_zero_mean_reversion_gives_a_flat_vol_term_structure():
    assert T.hw_yield_vol(0.01, 0.0, 10) == 0.01
    assert T.hw_yield_vol(0.01, 0.05, 30) < T.hw_yield_vol(0.01, 0.05, 2)


def test_realized_vols_annualise_daily_changes_over_the_window():
    rng = np.random.default_rng(1)
    idx = pd.bdate_range("2022-01-03", "2026-08-28")
    hist = pd.DataFrame({s: 0.04 + np.cumsum(rng.normal(0, 0.0006, len(idx))) for s in T.SERIES.values()}, index=idx)
    v = T.realized_vols("2026-08-28", 3, hist)
    assert all(abs(x - 0.0006 * np.sqrt(252)) < 0.0015 for x in v.values())
