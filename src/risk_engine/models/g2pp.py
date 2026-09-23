"""
Two-factor Gaussian short-rate model (G2++, Brigo and Mercurio, "Interest
Rate Models", ch. 4; equivalent to a two-factor LGM), the richer alternative
to the one-factor Hull-White model in rates.py:

    r(t)  = x(t) + y(t) + phi(t)
    dx    = -a x dt + sigma dW1
    dy    = -b y dt + eta   dW2          corr(dW1, dW2) = rho

phi(t) fits today's curve exactly:

    phi(t) = f(0,t) + sigma^2/(2a^2)(1-e^{-at})^2 + eta^2/(2b^2)(1-e^{-bt})^2
             + rho sigma eta/(ab) (1-e^{-at})(1-e^{-bt})

Zero-coupon bond at a future node (tau = T - t):

    P(t,T) = P(0,T)/P(0,t) exp( 0.5 [V(t,T) - V(0,T) + V(0,t)]
                                - B(a,tau) x(t) - B(b,tau) y(t) )
    V(t,T) = sigma^2/a^2 [tau + 2/a e^{-a tau} - 1/(2a) e^{-2a tau} - 3/(2a)]
           + eta^2/b^2   [tau + 2/b e^{-b tau} - 1/(2b) e^{-2b tau} - 3/(2b)]
           + 2 rho sigma eta/(ab) [tau + (e^{-a tau}-1)/a + (e^{-b tau}-1)/b
                                   - (e^{-(a+b) tau}-1)/(a+b)]

The second factor lets the curve twist independently of its level (a slope
factor), which the one-factor model cannot produce: in one-factor Hull-White
every zero rate moves in lock-step with the short rate. Calibration is to the
REALISED covariance of Treasury yield changes across tenors (real-world
measure, appropriate for exposure; see calibrate_to_yield_covariance).

The engine only needs r(t) for drifts and discounting (r = x + y + phi), so
the combined x + y is stored as the path's rate state and the second factor y
separately, for building the node curve.
"""
import math

import numpy as np


def _B(k, tau):
    return (1.0 - math.exp(-k * tau)) / k if k > 1e-10 else tau


class G2PP:
    def __init__(self, base_curve, sigma, a, eta, b, rho, fwd_eps=1.0 / 365.0):
        if a <= 0 or b <= 0:
            raise ValueError("G2++ needs positive mean-reversion speeds a, b")
        if not -1.0 < rho < 1.0:
            raise ValueError("rho must be in (-1, 1)")
        self.base_curve, self._eps = base_curve, fwd_eps
        self.sigma, self.a, self.eta, self.b, self.rho = sigma, a, eta, b, rho

    # ---- today's curve
    def _ln_df(self, t):
        return self.base_curve._ln_df_at_t(max(t, 0.0))

    def discount0(self, t):
        return math.exp(self._ln_df(t))

    def forward0(self, t):
        eps = self._eps
        return -(self._ln_df(t + eps) - self._ln_df(max(t - eps, 0.0))) / (eps if t - eps < 0 else 2 * eps)

    def short_rate0(self):
        return self.forward0(0.0)

    # ---- deterministic shift
    def alpha(self, t):
        """phi(t); named alpha so code written for the one-factor model
        (discounting along a path) works unchanged."""
        s, a, e, b, r = self.sigma, self.a, self.eta, self.b, self.rho
        ea, eb = 1.0 - math.exp(-a * t), 1.0 - math.exp(-b * t)
        return (self.forward0(t) + s * s / (2 * a * a) * ea * ea + e * e / (2 * b * b) * eb * eb
                + r * s * e / (a * b) * ea * eb)

    def short_rate(self, x_plus_y, t):
        return x_plus_y + self.alpha(t)

    # ---- exact joint transition of (x, y)
    def step(self, x, y, dt, z1, z2):
        """Exact one-step transition. z1, z2 independent N(0,1). Returns (x', y')."""
        s, a, e, b, r = self.sigma, self.a, self.eta, self.b, self.rho
        sd_x = s * math.sqrt((1 - math.exp(-2 * a * dt)) / (2 * a))
        sd_y = e * math.sqrt((1 - math.exp(-2 * b * dt)) / (2 * b))
        cov = r * s * e * (1 - math.exp(-(a + b) * dt)) / (a + b)
        c = max(min(cov / (sd_x * sd_y), 0.999999), -0.999999) if sd_x * sd_y > 0 else 0.0
        xn = x * math.exp(-a * dt) + sd_x * z1
        yn = y * math.exp(-b * dt) + sd_y * (c * z1 + math.sqrt(1 - c * c) * z2)
        return xn, yn

    def step_vec(self, x, y, dt, z1, z2):
        """Vectorised exact transition over arrays of scenarios."""
        s, a, e, b, r = self.sigma, self.a, self.eta, self.b, self.rho
        sd_x = s * math.sqrt((1 - math.exp(-2 * a * dt)) / (2 * a))
        sd_y = e * math.sqrt((1 - math.exp(-2 * b * dt)) / (2 * b))
        cov = r * s * e * (1 - math.exp(-(a + b) * dt)) / (a + b)
        c = max(min(cov / (sd_x * sd_y), 0.999999), -0.999999) if sd_x * sd_y > 0 else 0.0
        return (x * math.exp(-a * dt) + sd_x * z1,
                y * math.exp(-b * dt) + sd_y * (c * z1 + math.sqrt(1 - c * c) * z2))

    # ---- bond prices
    def _V(self, tau):
        s, a, e, b, r = self.sigma, self.a, self.eta, self.b, self.rho
        return (s * s / (a * a) * (tau + 2 / a * math.exp(-a * tau) - math.exp(-2 * a * tau) / (2 * a) - 3 / (2 * a))
                + e * e / (b * b) * (tau + 2 / b * math.exp(-b * tau) - math.exp(-2 * b * tau) / (2 * b) - 3 / (2 * b))
                + 2 * r * s * e / (a * b) * (tau + (math.exp(-a * tau) - 1) / a + (math.exp(-b * tau) - 1) / b
                                             - (math.exp(-(a + b) * tau) - 1) / (a + b)))

    def bond_price(self, t, T, x, y):
        if T <= t:
            return 1.0
        tau, T0 = T - t, T
        expo = 0.5 * (self._V(tau) - self._V(T0) + self._V(t)) - _B(self.a, tau) * x - _B(self.b, tau) * y
        return self.discount0(T) / self.discount0(t) * math.exp(expo)

    def fast_node_curve(self, node_date, t, r_t, y=0.0):
        """Curve at a simulated node given the short rate r_t = x + y + phi(t)
        and the second factor y."""
        x = r_t - self.alpha(t) - y
        return G2NodeCurve(self, node_date, t, x, y)


class G2NodeCurve:
    __slots__ = ("m", "ref_date", "t", "x", "y")

    def __init__(self, model, ref_date, t, x, y):
        self.m, self.ref_date, self.t, self.x, self.y = model, ref_date, t, x, y

    def discount(self, d):
        from capitolis_pricers.daycount import to_date, year_fraction
        tau = year_fraction(self.ref_date, to_date(d), self.m.base_curve.basis)
        return self.m.bond_price(self.t, self.t + tau, self.x, self.y)


# ---------------------------------------------------------------- calibration
def model_zero_rate_cov(params, tenors):
    """Annual covariance of daily-scale zero-rate changes at `tenors` implied
    by the model at short horizons: dz(T) = f_a(T) dx + f_b(T) dy,
    f_k(T) = (1 - e^{-kT})/(kT)."""
    s, a, e, b, r = params
    fa = np.array([_B(a, T) / T for T in tenors])
    fb = np.array([_B(b, T) / T for T in tenors])
    return (s * s * np.outer(fa, fa) + e * e * np.outer(fb, fb) + r * s * e * (np.outer(fa, fb) + np.outer(fb, fa)))


def calibrate_to_yield_covariance(cov_annual, tenors, a_bounds=(0.001, 0.3), b_bounds=(0.05, 3.0), a0=0.02, b0=0.5):
    """Least-squares fit of (sigma, a, eta, b, rho) to an annualised covariance
    matrix of yield changes (normal, decimal). The objective is the relative
    Frobenius error of the whole matrix, so it matches level vols and the
    correlation structure across tenors at once. The first factor is the slow
    one (a < b). Returns dict(params, rel_error, model_cov)."""
    from scipy.optimize import least_squares

    cov = np.asarray(cov_annual, dtype=float)
    scale = np.linalg.norm(cov)

    def resid(p):
        s, a, e, b, r = p
        return ((model_zero_rate_cov(p, tenors) - cov) / scale).ravel()

    v0 = float(np.sqrt(np.mean(np.diag(cov))))
    best = None
    for a_init, b_init in ((a0, b0), (0.01, 0.2), (0.05, 1.0), (0.005, 0.1)):
        x0 = [v0, a_init, 0.5 * v0, b_init, -0.3]
        lo = [1e-5, a_bounds[0], 1e-5, b_bounds[0], -0.99]
        hi = [0.05, a_bounds[1], 0.05, b_bounds[1], 0.99]
        res = least_squares(resid, x0, bounds=(lo, hi))
        if best is None or res.cost < best.cost:
            best = res
    s, a, e, b, r = best.x
    if a > b:  # label the slower factor as x
        s, a, e, b = e, b, s, a
    p = (float(s), float(a), float(e), float(b), float(r))
    m = model_zero_rate_cov(p, tenors)
    return {"sigma": p[0], "a": p[1], "eta": p[2], "b": p[3], "rho": p[4],
            "rel_error": float(np.linalg.norm(m - cov) / scale), "model_cov": m}
