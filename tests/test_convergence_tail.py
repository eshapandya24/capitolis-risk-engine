"""
Regression tests for the 99.9th-percentile convergence study
(docs/notes/convergence_study.md's "Extension" section,
scripts/convergence_study_tail.py).

Two kinds of test here:
  1. Self-contained, synthetic, no network/simulation needed (runs in CI) --
     demonstrates the same statistical mechanism the real study relies on:
     a tail quantile's standard error shrinks as N grows, same as the mean's
     does (already covered for the mean in test_simulation_engine.py), just
     slower since fewer samples land in the tail.
  2. A real-data regression check against the actual
     data/processed/convergence_study_tail_pfe999.json artifact this
     project generated -- skipped automatically if that file isn't present
     (it's gitignored/regenerable, not something a fresh clone has), so
     this only runs where the real results exist, and catches this
     specific empirical finding (marginal SE gain rises then declines;
     bias shrinks toward the reference as N grows) silently regressing.
"""
import json
import math
import os

import numpy as np
import pytest

DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "processed", "convergence_study_tail_pfe999.json",
)


def _bootstrap_quantile_se(population, N, confidence, n_bootstrap=200, seed=0):
    rng = np.random.default_rng(seed)
    pop_size = len(population)
    estimates = []
    for _ in range(n_bootstrap):
        idx = rng.choice(pop_size, size=N, replace=(N > pop_size))
        estimates.append(np.quantile(population[idx], confidence))
    arr = np.array(estimates)
    return arr.mean(), arr.std()


def test_tail_quantile_se_shrinks_with_n():
    """The 99.9th-percentile estimator's standard error should shrink as N
    grows, same direction as the mean's 1/sqrt(N) law -- verified on a
    synthetic population, no real simulation needed."""
    rng = np.random.default_rng(7)
    population = rng.lognormal(mean=10, sigma=1.2, size=200_000)  # a fat-tailed distribution, like exposure

    _, se_small = _bootstrap_quantile_se(population, N=200, confidence=0.999, seed=1)
    _, se_large = _bootstrap_quantile_se(population, N=5000, confidence=0.999, seed=1)

    assert se_large < se_small, (
        f"Tail quantile SE should shrink with more scenarios: N=200 SE={se_small:.2f}, "
        f"N=5000 SE={se_large:.2f}")


def test_tail_quantile_needs_more_n_than_the_median_for_equal_relative_precision():
    """The whole reason this extension study existed: a 99.9th-percentile
    estimate is noisier than a 50th-percentile (median) estimate at the
    SAME N, because far fewer samples inform the tail. Verify that
    directly, rather than just asserting it in prose."""
    rng = np.random.default_rng(11)
    population = rng.lognormal(mean=10, sigma=1.2, size=200_000)
    N = 1000

    mean_median, se_median = _bootstrap_quantile_se(population, N, confidence=0.50, seed=2)
    mean_tail, se_tail = _bootstrap_quantile_se(population, N, confidence=0.999, seed=2)

    rel_se_median = se_median / mean_median
    rel_se_tail = se_tail / mean_tail
    assert rel_se_tail > rel_se_median, (
        f"99.9th percentile relative SE ({rel_se_tail:.4f}) should be larger than the "
        f"median's ({rel_se_median:.4f}) at equal N -- the tail is harder to estimate")


def test_marginal_se_gain_eventually_declines_with_n():
    """Mirrors the real study's core finding on a synthetic case: as N
    grows past the point where the tail estimate is well-populated, each
    additional batch of paths buys progressively less SE reduction than
    the batch before it -- the empirical 'convergence' signature, not just
    the SE monotonically shrinking (which it does throughout, but that
    alone doesn't show WHERE it stops being worth the compute)."""
    rng = np.random.default_rng(13)
    population = rng.lognormal(mean=10, sigma=1.2, size=300_000)

    Ns = [500, 2000, 8000, 20000]
    ses = [_bootstrap_quantile_se(population, N, confidence=0.999, seed=3)[1] for N in Ns]
    gains = [(ses[i - 1] - ses[i]) / ses[i - 1] for i in range(1, len(ses))]

    # the LAST marginal gain (largest N step) should be smaller than the
    # FIRST -- diminishing returns as N grows, not constant or increasing
    assert gains[-1] < gains[0], (
        f"Expected diminishing marginal SE gains as N grows; got gains={gains}")


@pytest.mark.skipif(not os.path.exists(DATA_PATH),
                     reason="convergence_study_tail_pfe999.json not present -- run "
                            "scripts/convergence_study_tail.py to regenerate it")
def test_real_convergence_study_bias_shrinks_toward_reference():
    with open(DATA_PATH) as f:
        data = json.load(f)
    results = data["results"]
    biases = [abs(r["bias_vs_pool_pct"]) for r in results]
    # not strictly monotonic (bootstrap noise), but the LAST point (largest
    # N before the reference itself) must be closer to zero than the FIRST
    assert biases[-1] < biases[0], (
        f"Expected bias vs. the N=30,000 reference to shrink as N grows: "
        f"first={biases[0]:.3f}%, last={biases[-1]:.3f}%")


@pytest.mark.skipif(not os.path.exists(DATA_PATH),
                     reason="convergence_study_tail_pfe999.json not present -- run "
                            "scripts/convergence_study_tail.py to regenerate it")
def test_real_convergence_study_marginal_gain_peaks_then_declines():
    with open(DATA_PATH) as f:
        data = json.load(f)
    results = data["results"]
    # Exclude N == N_pool: that point's SE is trivially 0 (the reference
    # pool measured against itself), producing a degenerate 100% "gain"
    # that isn't a genuine measurement -- see convergence_study.md's note.
    n_pool = data["N_pool"]
    gains = [r["marginal_se_improvement_pct"] for r in results
             if r["marginal_se_improvement_pct"] is not None and r["N"] != n_pool]
    peak_idx = gains.index(max(gains))
    # the peak should not be the very last point -- there must be a
    # declining tail after it, which is the "convergence" signature
    assert peak_idx < len(gains) - 1, (
        f"Expected the marginal SE gain to peak and then decline, not keep rising "
        f"through the largest N tested; gains={gains}")
    assert gains[-1] < gains[peak_idx], "Marginal gain should be lower at the largest N than at its peak"
