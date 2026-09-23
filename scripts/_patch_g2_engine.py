p = "src/risk_engine/models/g2pp.py"
s = open(p, encoding="utf-8").read()
a = "    # ---- bond prices\n"
b = '''    def step_vec(self, x, y, dt, z1, z2):
        """Vectorised exact transition over arrays of scenarios."""
        s, a, e, b, r = self.sigma, self.a, self.eta, self.b, self.rho
        sd_x = s * math.sqrt((1 - math.exp(-2 * a * dt)) / (2 * a))
        sd_y = e * math.sqrt((1 - math.exp(-2 * b * dt)) / (2 * b))
        cov = r * s * e * (1 - math.exp(-(a + b) * dt)) / (a + b)
        c = max(min(cov / (sd_x * sd_y), 0.999999), -0.999999) if sd_x * sd_y > 0 else 0.0
        return (x * math.exp(-a * dt) + sd_x * z1,
                y * math.exp(-b * dt) + sd_y * (c * z1 + math.sqrt(1 - c * c) * z2))

    # ---- bond prices
'''
assert a in s
s = s.replace(a, b, 1)
open(p, "w", encoding="utf-8").write(s)

p = "src/risk_engine/simulation/engine.py"
s = open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert a in s, a[:70]
    s = s.replace(a, b, 1)


rep('vm_lag_days=None, jpy_factor=True):', 'vm_lag_days=None, jpy_factor=True, rates_model="hw1f"):')
rep('''            constant r_USD - r_JPY differential.
        """''', '''            constant r_USD - r_JPY differential.
        rates_model: "hw1f" (default, one-factor Hull-White) or "g2pp" (two-factor
            Gaussian, needs calib["g2"]; see models/g2pp.py). The second factor
            is driven by rho * (first factor's shock) plus an extra independent
            shock, so it correlates with every other factor through the first.
        """''')
rep('''        self.factor_order = base_order + (["RATE_JPY"] if self.hw_jpy is not None else [])
        self.n_factors = len(self.factor_order)
''', '''        self.factor_order = base_order + (["RATE_JPY"] if self.hw_jpy is not None else [])
        self.g2 = calib["g2"] if rates_model == "g2pp" else None
        if rates_model not in ("hw1f", "g2pp"):
            raise ValueError(f"rates_model must be 'hw1f' or 'g2pp', got {rates_model!r}")
        if self.g2 is not None:
            self.factor_order = self.factor_order + ["RATE_USD_2"]
        self.rm = self.g2 if self.g2 is not None else self.hw      # model that owns short_rate/alpha/node curves
        self.n_factors = len(self.factor_order)
''')
rep('''        self.jpy_idx = self.factor_order.index("RATE_JPY") if self.hw_jpy is not None else None
        self.equity_idx = {f: i for i, f in enumerate(self.factor_order)
                            if f not in ("RATE_USD", "FX_USDJPY", "RATE_JPY")}
''', '''        self.jpy_idx = self.factor_order.index("RATE_JPY") if self.hw_jpy is not None else None
        self.y_idx = self.factor_order.index("RATE_USD_2") if self.g2 is not None else None
        self.equity_idx = {f: i for i, f in enumerate(self.factor_order)
                            if f not in ("RATE_USD", "FX_USDJPY", "RATE_JPY", "RATE_USD_2")}
''')
rep('''        corr = _nearest_psd(corr)
        self.corr = corr''', '''        if self.g2 is not None:
            corr = np.pad(corr, ((0, 1), (0, 1)))
            corr[-1, -1] = 1.0                       # independent extra shock for the second factor
        corr = _nearest_psd(corr)
        self.corr = corr''')
rep('''        x_jpy = np.zeros((n_scen, n_steps + 1)) if self.hw_jpy is not None else None
''', '''        x_jpy = np.zeros((n_scen, n_steps + 1)) if self.hw_jpy is not None else None
        y_rate = np.zeros((n_scen, n_steps + 1)) if self.g2 is not None else None
        x_only = np.zeros(n_scen)
        y_only = np.zeros(n_scen)
''')
rep('''            r_prev = self.hw.short_rate(x_rate[:, k], t_prev)  # vectorized short rate at step start
''', '''            r_prev = self.rm.short_rate(x_rate[:, k], t_prev)  # vectorized short rate at step start
''')
rep('''            z_rate = z[:, k, self.rate_idx]
            x_rate[:, k + 1] = _vec_step_x(self.hw, x_rate[:, k], dt, z_rate)
''', '''            z_rate = z[:, k, self.rate_idx]
            if self.g2 is not None:
                # second factor: shock rho * z_x + sqrt(1 - rho^2) * z_extra, then the exact joint OU step
                rho = self.g2.rho
                z_y = rho * z_rate + math.sqrt(1.0 - rho * rho) * z[:, k, self.y_idx]
                x_only, y_only = self.g2.step_vec(x_only, y_only, dt, z_rate, z_y)
                x_rate[:, k + 1] = x_only + y_only
                y_rate[:, k + 1] = y_only
            else:
                x_rate[:, k + 1] = _vec_step_x(self.hw, x_rate[:, k], dt, z_rate)
''')
rep('''        if x_jpy is not None:
            out["x_jpy"] = x_jpy
        return out''', '''        if x_jpy is not None:
            out["x_jpy"] = x_jpy
        if y_rate is not None:
            out["y_rate"] = y_rate
        return out''')
rep('''            r_t = self.hw.short_rate(paths["x_rate"][s, node_idx], t)
            usd_curve = self.hw.fast_node_curve(node_date, t, r_t)
''', '''            r_t = self.rm.short_rate(paths["x_rate"][s, node_idx], t)
            if self.g2 is not None:
                usd_curve = self.g2.fast_node_curve(node_date, t, r_t, paths["y_rate"][s, node_idx])
            else:
                usd_curve = self.hw.fast_node_curve(node_date, t, r_t)
''')
rep("from datetime import date, timedelta\n\nimport numpy as np", "import math\nfrom datetime import date, timedelta\n\nimport numpy as np")
open(p, "w", encoding="utf-8").write(s)
print("g2 engine patched")
