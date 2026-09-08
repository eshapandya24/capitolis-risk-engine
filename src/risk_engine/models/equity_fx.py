"""
Equity spots (37 names) + USDJPY FX: correlated Geometric Brownian Motion
under the risk-neutral measure, driven by the same short rate path as
models/rates.py (a "hybrid" short-rate + lognormal-equity model -- standard
for CCR engines; simpler than a full stochastic-vol or local-vol model,
and consistent with the lognormal vol convention already computed).

    dS_i/S_i = (r(t) - q_i) dt + sigma_i dW_i        (USD-quoted names)
    dS_i/S_i = (r_JPY(t) - q_i) dt + sigma_i dW_i    (JPY-quoted names)
    dFX/FX   = (r(t) - r_JPY(t)) dt + sigma_FX dW_FX  (JPY per USD)

r_JPY(t) is not a separately-simulated factor (we have no JPY curve, and
building a full second Hull-White factor for 2 small compo trades is not
worth the complexity) -- instead it's approximated as r(t) minus a constant
calibrated differential, backed out from REAL market data: CME JPY futures
(6J, via Databento, same account/dataset as the SOFR futures) compared
against our own real USD curve via covered interest rate parity. See
models/calibration.py for exactly how that differential is derived. This
is a disclosed simplification, not a fabricated number.

Discretization: exact-in-distribution log-Euler step (GBM increments are
lognormal in closed form given a piecewise-constant drift over one step,
so this is exact given the short rate is held at r(t) constant across
the step, matching the same discretization granularity as the rate model).
"""
import math

import numpy as np


class CorrelatedGBM:
    def __init__(self, factor_names, spots, vols, currencies, dividends,
                 jpy_usd_rate_diff):
        """
        factor_names: ordered list of ISINs (matches the correlation matrix
            column order) -- FX_USDJPY and RATE_USD are NOT included here,
            they're handled by the rate model / the FX row below.
        spots: {isin: float}
        vols: {isin: float} annualized lognormal vol
        currencies: {isin: "USD"|"JPY"}
        dividends: {isin: float} continuous dividend yield (static, not simulated)
        jpy_usd_rate_diff: float, r_USD - r_JPY (constant, real-data-derived)
        """
        self.factor_names = list(factor_names)
        self.spots0 = spots
        self.vols = vols
        self.currencies = currencies
        self.dividends = dividends
        self.jpy_usd_rate_diff = jpy_usd_rate_diff
        self.fx_vol = vols["FX_USDJPY"]

    def r_jpy(self, r_usd_t):
        return r_usd_t - self.jpy_usd_rate_diff

    def step_log_spot(self, ln_s_prev, isin, r_usd_t, dt, z):
        """One log-Euler step for equity `isin`."""
        sigma = self.vols[isin]
        q = self.dividends.get(isin, 0.0)
        r = self.r_jpy(r_usd_t) if self.currencies.get(isin) == "JPY" else r_usd_t
        drift = (r - q - 0.5 * sigma ** 2) * dt
        return ln_s_prev + drift + sigma * math.sqrt(max(dt, 0.0)) * z

    def step_log_fx(self, ln_fx_prev, r_usd_t, dt, z):
        """One log-Euler step for USDJPY spot (JPY per USD). Drift under the
        USD risk-neutral measure is r_USD - r_JPY (covered interest parity),
        which collapses to the constant differential itself."""
        sigma = self.fx_vol
        drift = (self.jpy_usd_rate_diff - 0.5 * sigma ** 2) * dt
        return ln_fx_prev + drift + sigma * math.sqrt(max(dt, 0.0)) * z
