"""Properties the Greeks rely on: Latin Hypercube draws are reproducible per seed (common random
numbers) and stratified in every dimension, and a bump on shared draws has far less noise than a
bump on independent draws."""
import numpy as np
from scipy.stats import norm

from risk_engine.simulation.random_numbers import generate


def test_same_seed_gives_identical_draws_for_every_method():
    for m in ("pseudo_random", "antithetic", "moment_matched", "sobol", "latin_hypercube"):
        a = generate(m, 64, 5, 3, seed=11)
        b = generate(m, 64, 5, 3, seed=11)
        assert np.array_equal(a, b), m
        assert not np.array_equal(a, generate(m, 64, 5, 3, seed=12)), m


def test_latin_hypercube_has_one_draw_per_bin_in_every_dimension():
    n = 200
    z = generate("latin_hypercube", n, 6, 4, seed=5)
    u = norm.cdf(z).reshape(n, -1)
    bins = np.floor(u * n).astype(int)
    for j in range(u.shape[1]):
        assert sorted(bins[:, j]) == list(range(n)), j


def test_common_random_numbers_shrink_the_noise_of_a_bumped_difference():
    """Delta of E[max(S*(1+h) - K, 0)] by central bump: shared draws vs independent draws."""
    n, h, reps = 300, 0.01, 40
    f = lambda z, s: np.maximum(100 * np.exp(0.2 * z) * s - 100, 0).mean()
    crn, ind = [], []
    for r in range(reps):
        z = generate("latin_hypercube", n, 1, 1, seed=r)[:, 0, 0]
        crn.append(0.5 * (f(z, 1 + h) - f(z, 1 - h)))
        z1 = generate("latin_hypercube", n, 1, 1, seed=1000 + r)[:, 0, 0]
        z2 = generate("latin_hypercube", n, 1, 1, seed=2000 + r)[:, 0, 0]
        ind.append(0.5 * (f(z1, 1 + h) - f(z2, 1 - h)))
    assert np.std(crn) < 0.1 * np.std(ind)


def test_latin_hypercube_reduces_error_of_a_smooth_mean():
    n, reps = 200, 60
    e = {}
    for m in ("pseudo_random", "latin_hypercube"):
        est = [np.exp(0.3 * generate(m, n, 1, 1, seed=r)[:, 0, 0]).mean() for r in range(reps)]
        e[m] = np.sqrt(np.mean((np.array(est) - np.exp(0.045)) ** 2))
    assert e["latin_hypercube"] < 0.5 * e["pseudo_random"]
