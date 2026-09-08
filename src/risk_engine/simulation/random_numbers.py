"""
Random draw generation for the Monte Carlo engine -- several standard
variance-reduction / sampling techniques, so the engine can be run with any
of them and the results compared (see scripts/benchmark_variance_reduction.py
for the actual speed-vs-accuracy analysis).

All functions return an array of shape (n_scenarios, n_steps, n_factors) of
i.i.d. standard Normal(0,1) draws -- correlation across factors (via the
39x39 matrix) and across the rate/equity/FX models is applied afterwards by
the simulation engine (Cholesky), not here. Keeping these two concerns
separate lets any sampling technique below combine with any model.

Techniques implemented:
  - pseudo_random    : plain Mersenne Twister Gaussian draws (numpy default) --
                        the baseline every other technique is compared against.
  - antithetic        : each draw z is paired with -z, halving the true
                        number of independent draws but guaranteeing the
                        odd noise moments cancel exactly -- a classic,
                        near-free variance reduction for any roughly
                        linear-in-z payoff (which the underlying GBM/HW1F
                        log-increments are, to leading order).
  - moment_matched    : pseudo-random draws, then rescaled/recentered per
                        (step, factor) so the SAMPLE mean is exactly 0 and
                        sample std is exactly 1 -- removes sampling noise in
                        the first two moments at the cost of a small bias
                        (the draws are no longer strictly i.i.d. Normal).
  - sobol             : a low-discrepancy (quasi-random) Sobol sequence
                        mapped to Normal via the inverse CDF -- fills the
                        sample space more uniformly than pseudo-random,
                        typically converging faster in LOW-to-moderate
                        effective dimension. Our dimension here is
                        n_steps * n_factors (can be in the hundreds), where
                        QMC's advantage is known to degrade -- this is
                        exactly the tradeoff the benchmark script measures,
                        not assumed.
  - latin_hypercube   : stratifies each individual dimension's marginal
                        into n_scenarios equal-probability bins (one draw
                        per bin), a cheaper/simpler stratification than full
                        Sobol -- good 1-D coverage, weaker joint coverage.

"Mixed Gaussian" in the task sense here means comparing these different ways
of generating the Gaussian shocks the model consumes (not a Gaussian-mixture
/ fat-tailed distribution model -- the risk factor models above are
themselves Gaussian-driven, per data/MARKET_DATA.md's stated vol
conventions, and changing that would be a separate, larger modeling
decision).
"""
import numpy as np
from scipy.stats import norm, qmc


def pseudo_random(n_scenarios, n_steps, n_factors, seed=None):
    rng = np.random.default_rng(seed)
    return rng.standard_normal((n_scenarios, n_steps, n_factors))


def antithetic(n_scenarios, n_steps, n_factors, seed=None):
    """Generate n_scenarios/2 independent draws, then mirror each (z, -z).
    n_scenarios should be even; if odd, one extra independent draw is added."""
    rng = np.random.default_rng(seed)
    half = n_scenarios // 2
    base = rng.standard_normal((half, n_steps, n_factors))
    mirrored = np.concatenate([base, -base], axis=0)
    if n_scenarios % 2:
        extra = rng.standard_normal((1, n_steps, n_factors))
        mirrored = np.concatenate([mirrored, extra], axis=0)
    return mirrored


def moment_matched(n_scenarios, n_steps, n_factors, seed=None):
    rng = np.random.default_rng(seed)
    z = rng.standard_normal((n_scenarios, n_steps, n_factors))
    z = z - z.mean(axis=0, keepdims=True)
    std = z.std(axis=0, keepdims=True)
    std[std == 0] = 1.0
    return z / std


def sobol(n_scenarios, n_steps, n_factors, seed=None):
    """Sobol low-discrepancy sequence -> Normal via inverse CDF. scipy's
    Sobol sampler works best with n_scenarios a power of 2; we round UP to
    the next power of 2 internally and truncate, so results are always
    exactly n_scenarios draws regardless of the caller's choice."""
    dim = n_steps * n_factors
    sampler = qmc.Sobol(d=dim, scramble=True, seed=seed)
    m = int(np.ceil(np.log2(max(n_scenarios, 2))))
    u = sampler.random_base2(m=m)[:n_scenarios]  # (n_scenarios, dim) in (0,1)
    u = np.clip(u, 1e-10, 1 - 1e-10)  # avoid +/-inf at the inverse-CDF tails
    z = norm.ppf(u)
    return z.reshape(n_scenarios, n_steps, n_factors)


def latin_hypercube(n_scenarios, n_steps, n_factors, seed=None):
    dim = n_steps * n_factors
    sampler = qmc.LatinHypercube(d=dim, seed=seed)
    u = sampler.random(n=n_scenarios)
    u = np.clip(u, 1e-10, 1 - 1e-10)
    z = norm.ppf(u)
    return z.reshape(n_scenarios, n_steps, n_factors)


METHODS = {
    "pseudo_random": pseudo_random,
    "antithetic": antithetic,
    "moment_matched": moment_matched,
    "sobol": sobol,
    "latin_hypercube": latin_hypercube,
}


def generate(method, n_scenarios, n_steps, n_factors, seed=None):
    if method not in METHODS:
        raise ValueError(f"Unknown method {method!r}; choose from {list(METHODS)}")
    return METHODS[method](n_scenarios, n_steps, n_factors, seed=seed)
