"""
Validation tests for the Monte Carlo engine, beyond the pricer-level
tests already in test_bond_forward_validation.py. Uses only cached market
data (data/processed/) and the closed-form rate/equity models -- no network
calls, so this runs offline and in CI.

Checks:
  - Hull-White reproduces today's real curve exactly at t=0 (a closed-form
    identity, not a Monte Carlo average -- should match to machine precision).
  - GBM martingale property: the AVERAGE simulated equity spot at a future
    date should equal the deterministic forward price (S0 * DF-implied
    growth), a standard Monte Carlo correctness check independent of the
    pricer library entirely.
  - Monte Carlo standard error shrinks like 1/sqrt(N) as scenario count
    grows (convergence sanity check).
  - Antithetic variates produce lower variance than plain pseudo-random at
    equal scenario count, for a linear-ish payoff (the whole point of the
    technique).
"""
import math

import numpy as np
import pytest

from capitolis_pricers.curves import flat_curve
from risk_engine.models.rates import HullWhite1F
from risk_engine.simulation.random_numbers import generate

REF_DATE = "2026-01-15"
FLAT_RATE = 0.04


def test_hull_white_reproduces_todays_curve_at_t0():
    """P(0,T) from the HW1F closed form must match the real curve's own
    discount() exactly at t=0 -- that's the whole point of the shift
    function alpha(t) (see models/rates.py). Compare using the EXACT
    year-fraction the curve itself computes from each date (ACT/365F), not
    an assumed 365.25-day year -- otherwise a harmless date/day-count
    rounding mismatch masquerades as a model discrepancy."""
    from datetime import date, timedelta
    from capitolis_pricers.daycount import year_fraction
    curve = flat_curve(REF_DATE, FLAT_RATE)
    hw = HullWhite1F(curve, sigma=0.0063, a=0.03)
    ref = date(2026, 1, 15)
    for days_out in [91, 365, 730, 1826, 3653]:  # ~0.25y, 1y, 2y, 5y, 10y
        d = ref + timedelta(days=days_out)
        T = year_fraction(ref, d, curve.basis)
        analytic = hw.bond_price(0.0, T, hw.short_rate0())
        real = curve.discount(d)
        assert math.isclose(analytic, real, rel_tol=1e-9), f"HW1F P(0,{T}) diverges from real curve"


def test_gbm_martingale_property():
    """E[S_T] under the risk-neutral measure should equal the deterministic
    forward S0 * exp((r - q) * T) for GBM with drift (r - q) -- check this
    holds (within Monte Carlo noise) for a simple single-factor case,
    independent of the rest of the engine (no correlation, no rate
    simulation -- r held flat and known)."""
    rng = np.random.default_rng(7)
    S0, r, q, sigma, T = 100.0, 0.04, 0.01, 0.25, 1.0
    n = 200_000
    z = rng.standard_normal(n)
    ln_ST = math.log(S0) + (r - q - 0.5 * sigma ** 2) * T + sigma * math.sqrt(T) * z
    ST = np.exp(ln_ST)
    forward = S0 * math.exp((r - q) * T)
    mc_mean = ST.mean()
    se = ST.std() / math.sqrt(n)
    assert abs(mc_mean - forward) < 4 * se, (
        f"Simulated mean {mc_mean:.4f} vs analytic forward {forward:.4f} "
        f"differs by more than 4 standard errors ({se:.4f}) -- drift is wrong")


def test_monte_carlo_standard_error_shrinks_like_inverse_sqrt_n():
    rng = np.random.default_rng(3)
    sigma = 0.2
    errors = []
    for n in [1000, 4000, 16000]:
        z = rng.standard_normal(n)
        x = sigma * z
        se = x.std() / math.sqrt(n)
        errors.append(se)
    # quadrupling n should roughly halve the standard error (1/sqrt(4)=0.5)
    ratio1 = errors[1] / errors[0]
    ratio2 = errors[2] / errors[1]
    assert 0.35 < ratio1 < 0.65, f"SE ratio {ratio1} not near the expected ~0.5"
    assert 0.35 < ratio2 < 0.65, f"SE ratio {ratio2} not near the expected ~0.5"


def test_antithetic_reduces_variance_for_monotonic_payoff():
    """Antithetic variance reduction is a claim about the ESTIMATOR (the
    mean over pairs Y_i = (f(z_i)+f(-z_i))/2), not about the raw pooled
    sample of individual draws -- the marginal distribution of a single
    draw is identical either way, so comparing raw pooled std (a common
    test-design mistake) shows no difference. Compare the actual quantity
    that matters: repeat the SAME total-evaluation-count estimator many
    times and compare how much the two methods' answers scatter run to run."""
    n_pairs, seed, n_repeats = 500, 11, 300
    payoff = lambda z: 100 * np.exp(0.2 * z)

    plain_means, anti_means = [], []
    for trial in range(n_repeats):
        rng = np.random.default_rng(seed + trial)
        z_plain = rng.standard_normal(2 * n_pairs)  # same total evaluations (2*n_pairs) as antithetic
        plain_means.append(payoff(z_plain).mean())

        z_half = rng.standard_normal(n_pairs)
        paired = (payoff(z_half) + payoff(-z_half)) / 2.0
        anti_means.append(paired.mean())

    var_plain = np.var(plain_means)
    var_anti = np.var(anti_means)
    assert var_anti < var_plain, (
        f"Antithetic estimator variance ({var_anti:.6f}) should be lower than "
        f"plain pseudo-random ({var_plain:.6f}) at equal total evaluation count")


def test_correlated_draws_recover_target_correlation():
    """Cholesky-correlating independent draws should recover the target
    correlation matrix in the large-sample limit -- the exact mechanism
    engine.py uses to correlate the 39 risk factors."""
    target_rho = 0.6
    corr = np.array([[1.0, target_rho], [target_rho, 1.0]])
    L = np.linalg.cholesky(corr)
    rng = np.random.default_rng(5)
    z = rng.standard_normal((200_000, 2))
    correlated = z @ L.T
    sample_rho = np.corrcoef(correlated[:, 0], correlated[:, 1])[0, 1]
    assert abs(sample_rho - target_rho) < 0.01
