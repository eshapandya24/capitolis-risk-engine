"""
Regression tests for the PCA/factor-model alternative to the engine's
default full-rank Cholesky correlation (models/equity_factor_model.py,
wired into simulation/engine.py via corr_mode="factor").

Self-contained with a small synthetic correlation matrix (block structure:
two clusters of highly-correlated names, weakly correlated across
clusters) so the "a 2-factor model should explain this well" claim is
checkable exactly, without needing the real 39x39 matrix or network data.
"""
import numpy as np
import pytest

from risk_engine.models.equity_factor_model import (
    build_pca_factor_loadings, reconstruct_correlation,
    reconstruction_error, explained_variance_ratio,
)


def _two_cluster_corr(n_per_cluster=4, within=0.8, across=0.05):
    """A correlation matrix that is EXACTLY rank-2 by construction: each
    name i is assigned a unit 2D vector u_i, and corr_ij = u_i . u_j. Any
    such matrix is automatically PSD with a unit diagonal (no forcing
    needed, unlike a block-constant or loading-plus-diagonal construction,
    where fixing the diagonal back to 1 perturbs the matrix away from
    exact low rank) -- so a 2-factor PCA fit should reconstruct it exactly."""
    import math
    n = 2 * n_per_cluster
    # cluster 1 near angle 0, cluster 2 near angle theta (small within-
    # cluster angular spread so names in the same cluster are highly, but
    # not perfectly, correlated -- `within`/`across` set that spread).
    theta_across = math.acos(across)
    spread = math.acos(within) / 2
    angles = ([0.0 + a for a in np.linspace(-spread, spread, n_per_cluster)] +
              [theta_across + a for a in np.linspace(-spread, spread, n_per_cluster)])
    vecs = np.array([[math.cos(a), math.sin(a)] for a in angles])
    return vecs @ vecs.T


def _frobenius_reconstruction_error(corr, B, idio_var):
    """Frobenius-norm reconstruction error -- unlike max-abs-entrywise
    error, THIS is the metric Eckart-Young/PCA theory guarantees is
    monotonically non-increasing as k grows (a low-rank PCA truncation is
    the best possible approximation in Frobenius/spectral norm, not
    necessarily in max-entrywise norm)."""
    corr_hat = reconstruct_correlation(B, idio_var)
    return float(np.linalg.norm(corr - corr_hat, ord="fro"))


def test_full_rank_reconstruction_is_exact():
    """n_factors == matrix rank should reconstruct the correlation matrix
    (near) exactly -- the factor model is strictly more general than any
    fixed k, full rank is the degenerate/lossless case."""
    corr = _two_cluster_corr()
    n = corr.shape[0]
    B, idio_var = build_pca_factor_loadings(corr, n_factors=n)
    err = reconstruction_error(corr, B, idio_var)
    assert err < 1e-8, f"full-rank PCA reconstruction should be exact, got max error {err}"


def test_two_factor_model_captures_block_structure_well():
    """The synthetic matrix has an EXACT 2-factor structure, so k=2 should
    already reconstruct it almost exactly, much better than k=1."""
    corr = _two_cluster_corr()
    B1, idio1 = build_pca_factor_loadings(corr, n_factors=1)
    B2, idio2 = build_pca_factor_loadings(corr, n_factors=2)
    err1 = reconstruction_error(corr, B1, idio1)
    err2 = reconstruction_error(corr, B2, idio2)
    assert err2 < err1, "k=2 should reconstruct the true 2-factor structure better than k=1"
    assert err2 < 0.05, f"k=2 should nearly exactly capture an exact 2-factor matrix, got {err2}"


def test_reconstruction_error_shrinks_monotonically_with_k():
    rng = np.random.default_rng(3)
    n = 10
    A = rng.normal(size=(n, n))
    cov = A @ A.T
    d = np.sqrt(np.diag(cov))
    corr = cov / np.outer(d, d)
    np.fill_diagonal(corr, 1.0)

    errors = [_frobenius_reconstruction_error(corr, *build_pca_factor_loadings(corr, k)) for k in range(1, n + 1)]
    for i in range(1, len(errors)):
        assert errors[i] <= errors[i - 1] + 1e-9, (
            f"Frobenius reconstruction error should not increase as k grows: {errors}")
    assert errors[-1] < 1e-8, "full rank (k=n) should be an exact reconstruction"


def test_explained_variance_ratio_increases_with_k_and_caps_at_one():
    corr = _two_cluster_corr()
    n = corr.shape[0]
    ratios = [explained_variance_ratio(corr, k) for k in range(1, n + 1)]
    assert ratios[-1] == pytest.approx(1.0, abs=1e-6)
    for i in range(1, len(ratios)):
        assert ratios[i] >= ratios[i - 1] - 1e-9


def test_invalid_n_factors_raises():
    corr = _two_cluster_corr()
    n = corr.shape[0]
    with pytest.raises(ValueError):
        build_pca_factor_loadings(corr, n_factors=0)
    with pytest.raises(ValueError):
        build_pca_factor_loadings(corr, n_factors=n + 1)


def test_total_variance_is_preserved_regardless_of_k():
    """B@B.T's diagonal (communality) + idio_var must sum to 1 for every
    name, for ANY k -- this is what makes each simulated factor's own
    variance come back to 1 even though the systematic part alone
    under-explains it at low k."""
    corr = _two_cluster_corr()
    n = corr.shape[0]
    for k in (1, 2, 4, n):
        B, idio_var = build_pca_factor_loadings(corr, k)
        communality = np.sum(B ** 2, axis=1)
        total_var = communality + idio_var
        assert np.allclose(total_var, 1.0, atol=1e-8), f"k={k}: total variance not preserved: {total_var}"
