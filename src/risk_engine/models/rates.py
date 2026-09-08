"""
USD short-rate model: Hull-White one-factor (extended Vasicek), the standard
textbook choice for CCR simulation engines -- Gaussian, mean-reverting,
closed-form bond prices at every future node (so building a discount curve
at a simulated future date is cheap and exact, not another Monte Carlo
step).

    dr(t) = [theta(t) - a*r(t)] dt + sigma dW(t)

Implemented via the standard "shifted OU process" decomposition (Brigo &
Mercurio, "Interest Rate Models", ch. 3): r(t) = x(t) + alpha(t), where
x(t) is a zero-mean Ornstein-Uhlenbeck process (x(0)=0) and alpha(t) is a
deterministic shift fitting the model to today's real curve exactly:

    alpha(t) = f(0,t) + (sigma^2 / (2*a^2)) * (1 - exp(-a*t))^2

f(0,t) is today's instantaneous forward rate, read off the REAL Databento-
built curve (src/risk_engine/market/sofr.py) -- so the simulated curve
reproduces today's actual market curve exactly at t=0, not a toy curve.

Calibration inputs, both already collected (no new data needed):
  - `a` (mean reversion speed): NOT derivable from data we have access to
    (would normally come from swaption/cap vols). Using a=0.03, a standard
    textbook value for USD rates -- an explicit, disclosed assumption.
  - `sigma`: the realized normal vol already computed in vols.py
    (RATE_USD, ~63bp) -- real data, not assumed.
"""
import math

DEFAULT_MEAN_REVERSION = 0.03  # 'a' -- disclosed assumption, see module docstring


class HullWhite1F:
    def __init__(self, base_curve, sigma, a=DEFAULT_MEAN_REVERSION, fwd_eps=1.0 / 365.0):
        """
        base_curve: today's real capitolis_pricers.curves.Curve (t=0 anchor).
        sigma: annualized normal rate vol (decimal, e.g. 0.0063).
        a: mean reversion speed (1/years).
        """
        self.base_curve = base_curve
        self.sigma = sigma
        self.a = a
        self._eps = fwd_eps

    # ---- today's curve, read directly (no re-fitting) ----
    def _ln_df(self, t):
        return self.base_curve._ln_df_at_t(max(t, 0.0))

    def discount0(self, t):
        """P(0,t) off today's real curve."""
        return math.exp(self._ln_df(t))

    def forward0(self, t):
        """Instantaneous forward rate f(0,t), central finite difference on
        today's real curve's log-discount-factor function."""
        eps = self._eps
        return -(self._ln_df(t + eps) - self._ln_df(max(t - eps, 0.0))) / (
            eps if t - eps < 0 else 2 * eps)

    def short_rate0(self):
        """r(0) = f(0,0), today's instantaneous short rate."""
        return self.forward0(0.0)

    # ---- shift function ----
    def alpha(self, t):
        a, sigma = self.a, self.sigma
        return self.forward0(t) + (sigma ** 2 / (2 * a ** 2)) * (1 - math.exp(-a * t)) ** 2

    # ---- path simulation of the zero-mean OU factor x(t) ----
    def step_x(self, x_prev, dt, z):
        """Exact one-step transition of the OU factor x (Gaussian, so the
        Euler-vs-exact distinction doesn't matter -- this IS the exact
        transition density, not an approximation)."""
        a, sigma = self.a, self.sigma
        mean = x_prev * math.exp(-a * dt)
        var = (sigma ** 2 / (2 * a)) * (1 - math.exp(-2 * a * dt))
        return mean + math.sqrt(max(var, 0.0)) * z

    def short_rate(self, x_t, t):
        return x_t + self.alpha(t)

    # ---- analytic bond price at a future node, given the simulated r(t) ----
    def _B(self, tau):
        a = self.a
        return (1 - math.exp(-a * tau)) / a if a > 1e-10 else tau

    def bond_price(self, t, T, r_t):
        """P(t,T): the price at simulated future time t of a zero-coupon
        bond maturing at T, given the simulated short rate r(t). Brigo &
        Mercurio eq. 3.39, using today's REAL curve for P(0,t), P(0,T), f(0,t)."""
        if T <= t:
            return 1.0
        a, sigma = self.a, self.sigma
        tau = T - t
        B = self._B(tau)
        P0T = self.discount0(T)
        P0t = self.discount0(t)
        f0t = self.forward0(t)
        A = (P0T / P0t) * math.exp(
            B * f0t - (sigma ** 2 / (4 * a)) * (1 - math.exp(-2 * a * t)) * B ** 2
        )
        return A * math.exp(-B * r_t)

    def build_curve_at_node(self, node_date, t, r_t, tenors=(0.25, 0.5, 1, 2, 3, 5, 7, 10)):
        """Build a real capitolis_pricers.curves.Curve object anchored at the
        simulated future date `node_date` (t years from t=0), using the
        analytic HW1F bond price formula for each tenor pillar. Kept for
        cases that want an actual Curve object (e.g. printing a curve
        shape); the simulation engine's hot path uses FastNodeCurve below
        instead, which is both cheaper AND exact (no pillar interpolation)."""
        from capitolis_pricers.curves import Curve
        pillar_times, dfs = [], []
        for tau in tenors:
            pillar_times.append(tau)
            dfs.append(self.bond_price(t, t + tau, r_t))
        return Curve(node_date, pillar_times, dfs, basis=self.base_curve.basis)

    def fast_node_curve(self, node_date, t, r_t):
        """A lightweight object exposing just what the pricers actually use
        (`.ref_date`, `.discount(date)`) -- no Curve object construction
        (sorting, log-DF preprocessing over fixed pillars), and no pillar
        interpolation error: every requested date's discount factor is the
        exact analytic HW1F bond price, computed on demand. This is the
        simulation engine's per-(scenario,node) discount curve; it is both
        faster AND more accurate than build_curve_at_node's fixed-pillar
        approximation, since the analytic formula needs no interpolation
        at all."""
        return FastNodeCurve(self, node_date, t, r_t)


class FastNodeCurve:
    """Duck-types capitolis_pricers.curves.Curve's public interface
    (`.ref_date`, `.discount(d)`) using HullWhite1F.bond_price() directly --
    see HullWhite1F.fast_node_curve()."""
    __slots__ = ("hw", "ref_date", "t", "r_t")

    def __init__(self, hw, ref_date, t, r_t):
        self.hw = hw
        self.ref_date = ref_date
        self.t = t
        self.r_t = r_t

    def discount(self, d):
        from capitolis_pricers.daycount import to_date, year_fraction
        tau = year_fraction(self.ref_date, to_date(d), self.hw.base_curve.basis)
        return self.hw.bond_price(self.t, self.t + tau, self.r_t)
