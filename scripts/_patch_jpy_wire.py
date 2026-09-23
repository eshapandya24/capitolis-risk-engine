p = "src/risk_engine/models/equity_fx.py"
s = open(p, encoding="utf-8").read()
j = s.index("import math")
doc = '''"""
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
'''
s = doc + s[j:]
k = s.index("    def r_jpy(self, r_usd_t):")
s = s[:k] + '''    def r_jpy(self, r_usd_t):
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
'''
open(p, "w", encoding="utf-8").write(s)

p = "src/risk_engine/simulation/engine.py"
s = open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert a in s, a[:60]
    s = s.replace(a, b, 1)


rep('corr_mode="full", n_pca_factors=5, vm_lag_days=None):', 'corr_mode="full", n_pca_factors=5, vm_lag_days=None, jpy_factor=True):')
rep('''        n_pca_factors: only used when corr_mode="factor".
        """''', '''        n_pca_factors: only used when corr_mode="factor".
        jpy_factor: True (default) simulates the JPY Hull-White short rate as
            an extra correlated factor (needs calib["hw_jpy"]) and uses it for
            the drift of JPY-listed names and USDJPY. False keeps the
            constant r_USD - r_JPY differential.
        """''')
rep('''        self.hw = calib["hw"]
        self.gbm = calib["gbm"]
        self.factor_order = calib["factor_order"]  # [equities..., FX_USDJPY, RATE_USD]
        self.n_factors = len(self.factor_order)
''', '''        self.hw = calib["hw"]
        self.gbm = calib["gbm"]
        base_order = list(calib["factor_order"])  # [equities..., FX_USDJPY, RATE_USD]
        self.hw_jpy = calib.get("hw_jpy") if jpy_factor else None
        self.factor_order = base_order + (["RATE_JPY"] if self.hw_jpy is not None else [])
        self.n_factors = len(self.factor_order)
''')
rep('''        self.equity_idx = {f: i for i, f in enumerate(self.factor_order)
                            if f not in ("RATE_USD", "FX_USDJPY")}

        corr = calib["corr_matrix"].loc[self.factor_order, self.factor_order].values
        corr = _nearest_psd(corr)
''', '''        self.jpy_idx = self.factor_order.index("RATE_JPY") if self.hw_jpy is not None else None
        self.equity_idx = {f: i for i, f in enumerate(self.factor_order)
                            if f not in ("RATE_USD", "FX_USDJPY", "RATE_JPY")}

        corr = calib["corr_matrix"].loc[base_order, base_order].values
        if self.hw_jpy is not None:
            corr = extend_correlation(corr, base_order, calib.get("jpy_rate_corr") or {},
                                       calib.get("usd_jpy_rate_factor_corr", 0.0))
        corr = _nearest_psd(corr)
        self.corr = corr
        # stock-USDJPY shock correlation, for the quanto term in JPY names' drift
        self.rho_fx = {f: float(corr[i, self.fx_idx]) for f, i in self.equity_idx.items()}
''')
rep('''        ln_fx = np.zeros((n_scen, n_steps + 1))

        for f, idx in self.equity_idx.items():
            ln_spot[f][:, 0] = np.log(self.gbm.spots0[f])''', '''        ln_fx = np.zeros((n_scen, n_steps + 1))
        x_jpy = np.zeros((n_scen, n_steps + 1)) if self.hw_jpy is not None else None

        for f, idx in self.equity_idx.items():
            ln_spot[f][:, 0] = np.log(self.gbm.spots0[f])''')
rep('''            z_rate = z[:, k, self.rate_idx]
            x_rate[:, k + 1] = _vec_step_x(self.hw, x_rate[:, k], dt, z_rate)

            for f, idx in self.equity_idx.items():
                z_f = z[:, k, idx]
                ln_spot[f][:, k + 1] = _vec_step_log_spot(self.gbm, ln_spot[f][:, k], f, r_prev, dt, z_f)

            z_fx = z[:, k, self.fx_idx]
            ln_fx[:, k + 1] = _vec_step_log_fx(self.gbm, ln_fx[:, k], r_prev, dt, z_fx)

        return {"x_rate": x_rate, "ln_spot": ln_spot, "ln_fx": ln_fx}''', '''            if x_jpy is not None:
                r_jpy_prev = self.hw_jpy.short_rate(x_jpy[:, k], t_prev)
                x_jpy[:, k + 1] = _vec_step_x(self.hw_jpy, x_jpy[:, k], dt, z[:, k, self.jpy_idx])
            else:
                r_jpy_prev = r_prev - self.gbm.jpy_usd_rate_diff

            z_rate = z[:, k, self.rate_idx]
            x_rate[:, k + 1] = _vec_step_x(self.hw, x_rate[:, k], dt, z_rate)

            for f, idx in self.equity_idx.items():
                z_f = z[:, k, idx]
                ln_spot[f][:, k + 1] = _vec_step_log_spot(self.gbm, ln_spot[f][:, k], f, r_prev, r_jpy_prev,
                                                           dt, z_f, self.rho_fx[f])

            z_fx = z[:, k, self.fx_idx]
            ln_fx[:, k + 1] = _vec_step_log_fx(self.gbm, ln_fx[:, k], r_prev, r_jpy_prev, dt, z_fx)

        out = {"x_rate": x_rate, "ln_spot": ln_spot, "ln_fx": ln_fx}
        if x_jpy is not None:
            out["x_jpy"] = x_jpy
        return out''')
rep('''            fx_curve = FxCurve("USD", "JPY", fx_spot, usd_curve)
            market = MarketState(
                ref_date=node_date, reporting_ccy="USD",
                discount_curves={"USD": usd_curve},''', '''            fx_curve = FxCurve("USD", "JPY", fx_spot, usd_curve)
            curves = {"USD": usd_curve}
            if self.hw_jpy is not None:
                r_jpy_t = self.hw_jpy.short_rate(paths["x_jpy"][s, node_idx], t)
                curves["JPY"] = self.hw_jpy.fast_node_curve(node_date, t, r_jpy_t)
            market = MarketState(
                ref_date=node_date, reporting_ccy="USD",
                discount_curves=curves,''')
k = s.index("def _vec_step_log_spot")
s = s[:k] + '''def _vec_step_log_spot(gbm, ln_s_prev, isin, r_usd_t, r_jpy_t, dt, z, rho_fx=0.0):
    import math
    sigma = gbm.vols[isin]
    drift = gbm.log_spot_drift(isin, r_usd_t, r_jpy_t, rho_fx)
    return ln_s_prev + drift * dt + sigma * math.sqrt(max(dt, 0.0)) * z


def _vec_step_log_fx(gbm, ln_fx_prev, r_usd_t, r_jpy_t, dt, z):
    import math
    return ln_fx_prev + gbm.log_fx_drift(r_usd_t, r_jpy_t) * dt + gbm.fx_vol * math.sqrt(max(dt, 0.0)) * z


def extend_correlation(corr, factor_order, jpy_corr, usd_jpy_rate_corr):
    """Append a RATE_JPY row/column to the base correlation matrix.
    jpy_corr: {factor: correlation of the JPY rate factor with that factor}
    (equities and FX_USDJPY; missing entries are 0); RATE_USD takes
    `usd_jpy_rate_corr`. The result is what the engine Cholesky-factors, so it
    must stay positive semi-definite (the engine repairs tiny violations)."""
    n = len(factor_order)
    v = np.zeros(n)
    for i, f in enumerate(factor_order):
        v[i] = usd_jpy_rate_corr if f == "RATE_USD" else jpy_corr.get(f, 0.0)
    out = np.eye(n + 1)
    out[:n, :n] = corr
    out[n, :n] = v
    out[:n, n] = v
    return out
'''
open(p, "w", encoding="utf-8").write(s)
print("patched")
