"""Regression tests for the parametric checks written into
docs/Capitolis_CCR_Parametric_Benchmarks.xlsx (scripts/build_validation_excel.py):
the same intuitive formulas (STDEV of returns, Hull-White closed form) that the
Excel sheet computes, run here directly against the calibration and a small
simulation, so a break in the pipeline is caught without opening the workbook."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from risk_engine.market import treasury

REF = date(2026, 8, 28)


@pytest.fixture(scope="module")
def calib():
    from risk_engine.models.calibration import build_calibration
    return build_calibration(REF)


def _window(df):
    end = pd.Timestamp(REF)
    return df[(df.index > end - pd.DateOffset(years=3)) & (df.index <= end)]


def test_excel_style_realized_vol_matches_the_calibrated_equity_vol():
    from risk_engine.models.calibration import load_vol_table
    px = pd.read_csv("data/raw/backtest_prices.csv", index_col=0, parse_dates=True)
    vols = load_vol_table()
    checked = 0
    for factor in px.columns[:5]:
        s = _window(px[factor].dropna())
        if len(s) < 100 or factor not in vols:
            continue
        excel_vol = float(np.log(s / s.shift(1)).dropna().std() * np.sqrt(252))
        assert excel_vol == pytest.approx(vols[factor], rel=0.01)
        checked += 1
    assert checked >= 3


def test_excel_style_realized_rate_vol_matches_treasury_realized_vols():
    hist = _window(treasury.load_cmt_history())
    computed = treasury.realized_vols(REF, hist=treasury.load_cmt_history())
    for t, s in treasury.SERIES.items():
        excel_vol = float(hist[s].dropna().diff().dropna().std() * np.sqrt(252))
        assert excel_vol == pytest.approx(computed[t], rel=1e-6)


def test_hull_white_formula_vol_is_within_a_wide_band_of_realized_at_fit_tenors():
    """The fit trades off tenors, so it need not match any single one exactly,
    but it should stay in the same ballpark (within 30%) at every fit tenor."""
    a = 0.0167
    vols = treasury.realized_vols(REF)
    sigma = treasury.fit_hw_sigma(a, vols)
    for t in treasury.FIT_TENORS:
        model = treasury.hw_yield_vol(sigma, a, t)
        assert model == pytest.approx(vols[t], rel=0.30)


def test_simulated_equity_and_rate_vol_matches_the_analytic_gbm_hw_formula(calib):
    from run_simulation import load_trades
    from risk_engine.models.calibration import load_vol_table
    from risk_engine.simulation.engine import SimulationEngine

    trades = load_trades()
    vols = load_vol_table()
    eng = SimulationEngine(calib, trades, method="latin_hypercube", n_scenarios=3000, seed=42)
    paths = eng.simulate_paths()
    times = np.array(eng.times)
    node = int(np.argmin(np.abs(times - 1.0)))
    T = float(times[node])

    factor = next(iter(paths["ln_spot"]))
    ln = paths["ln_spot"][factor][:, node] - paths["ln_spot"][factor][:, 0]
    assert float(ln.std()) == pytest.approx(vols[factor] * np.sqrt(T), rel=0.10)

    ln_fx = paths["ln_fx"][:, node] - paths["ln_fx"][:, 0]
    assert float(ln_fx.std()) == pytest.approx(vols["FX_USDJPY"] * np.sqrt(T), rel=0.10)

    a, sigma = calib["hw_mean_reversion_a"], calib["hw"].sigma
    analytic_rate_vol = sigma * np.sqrt((1 - np.exp(-2 * a * T)) / (2 * a))
    assert float(paths["x_rate"][:, node].std()) == pytest.approx(analytic_rate_vol, rel=0.10)
