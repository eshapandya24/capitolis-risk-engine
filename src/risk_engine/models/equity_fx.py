"""
Equity spots (37 names) + USDJPY FX: correlated Geometric Brownian Motion
under the USD risk-neutral measure (USD money-market numeraire), driven by
the simulated USD short rate (models/rates.py) and, for JPY-quoted names and
USDJPY, the simulated JPY short rate (a second Hull-White factor).

Notation: X = USDJPY, quoted as JPY per 1 USD; Y = 1/X = USD per JPY.
All drifts below follow from requiring that every USD-denominated tradable
asset, discounted by the USD money market, is a martingale:

    USD names      d ln S = (r_USD - q - s^2/2) dt + s dW
    JPY names      d ln S = (r_JPY - q + rho_SX s s_X - s^2/2) dt + s dW    (S in JPY)
    USDJPY         d ln X = (r_JPY - r_USD + s_X^2/2) dt + s_X dW_X

* The JPY bank account, valued in USD (B_JPY * Y), must earn r_USD, which
  gives Y drift r_USD - r_JPY and hence the X drift above. (An earlier
  version of this module used +(r_USD - r_JPY) for X, the drift of USD per
  JPY: the wrong direction for a JPY-per-USD quote.)
* A JPY-listed name held by a USD investor has USD value S*Y; requiring it to
  earn r_USD - q gives the JPY-currency drift r_JPY - q + rho_SX s s_X (the
  familiar quanto correction; rho_SX is the correlation between the stock and
  USDJPY shocks). Check: d ln(S*Y) = (r_USD - q - (s^2 + s_X^2 - 2 rho s s_X)/2) dt + ...
* Equity trades are USD trades; a JPY name enters through its USD value
  S*Y = S / X, whose drift is r_USD - q whatever the JPY rate does. The JPY
  rate therefore changes the drift of S and X separately, not (in
  expectation) their ratio; it does change the dispersion of exposure through
  the S and X paths individually.

r_JPY(t) is the simulated JPY Hull-White short rate when the engine has a JPY
factor. Without one (older calibrations), it falls back to r_USD(t) minus a
constant differential backed out from real market data (calibration.py).

Discretization: exact-in-distribution log-Euler step for each name given a
piecewise-constant drift over the step (short rates held at their step-start
values, the same granularity as the rate models).
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
        """JPY short rate implied by the constant differential (fallback when
        no JPY factor is simulated)."""
        return r_usd_t - self.jpy_usd_rate_diff

    def log_spot_drift(self, isin, r_usd_t, r_jpy_t=None, rho_fx=0.0):
        """Per-year drift of ln S under the USD risk-neutral measure."""
        sigma = self.vols[isin]
        q = self.dividends.get(isin, 0.0)
        if self.currencies.get(isin) == "JPY":
            r_j = self.r_jpy(r_usd_t) if r_jpy_t is None else r_jpy_t
            return r_j - q + rho_fx * sigma * self.fx_vol - 0.5 * sigma ** 2
        return r_usd_t - q - 0.5 * sigma ** 2

    def log_fx_drift(self, r_usd_t, r_jpy_t=None):
        """Per-year drift of ln USDJPY (JPY per USD)."""
        r_j = self.r_jpy(r_usd_t) if r_jpy_t is None else r_jpy_t
        return r_j - r_usd_t + 0.5 * self.fx_vol ** 2

    def step_log_spot(self, ln_s_prev, isin, r_usd_t, dt, z, r_jpy_t=None, rho_fx=0.0):
        """One log-Euler step for equity `isin`."""
        sigma = self.vols[isin]
        return (ln_s_prev + self.log_spot_drift(isin, r_usd_t, r_jpy_t, rho_fx) * dt
                + sigma * math.sqrt(max(dt, 0.0)) * z)

    def step_log_fx(self, ln_fx_prev, r_usd_t, dt, z, r_jpy_t=None):
        """One log-Euler step for USDJPY spot (JPY per USD)."""
        return (ln_fx_prev + self.log_fx_drift(r_usd_t, r_jpy_t) * dt
                + self.fx_vol * math.sqrt(max(dt, 0.0)) * z)
