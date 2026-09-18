"""
PCA-based factor model for the 37-equity (+FX +RATE) correlation structure --
an alternative to the engine's default full-rank Cholesky correlation.

Why: the full-rank approach (simulation/engine.py's `self.L`, a 39x39
Cholesky factor) is exact but treats the correlation matrix as one opaque
39x39 object -- every one of the ~741 off-diagonal pairs is an independent
number estimated from only 613 historically-aligned daily returns (see
correlations.py), which is a lot of parameters to estimate reliably from
that much data. A standard alternative used in real risk systems: assume
most of that co-movement is explained by a SMALL number of common factors
(broad market/sector moves) plus each name's own idiosyncratic noise --

    corr ~= B @ B.T + diag(idiosyncratic_variance)

where B is an (n_names x k_factors) loading matrix, k << n. This is
principal-component factor analysis: take the top-k eigenvectors of the
correlation matrix (scaled by sqrt of their eigenvalues) as the loadings.
It's a real, standard dimensionality-reduction technique (not invented for
this project), and it has two genuine practical benefits for an MCCR engine:
  1. Fewer effective stochastic drivers (k systematic + n idiosyncratic,
     vs. an implicit n arbitrary correlated ones) -- more robust to
     estimation noise in the original 39x39 matrix, and more interpretable
     (each factor can be inspected: which names load heavily on it).
  2. Cheaper variance-reduction: quasi-random sequences (Sobol/LHS, see
     simulation/random_gen.py) lose their low-discrepancy advantage in very
     high dimensions -- collapsing 39 correlated dims down to k systematic
     dims (plus per-name idiosyncratic noise, which doesn't need
     low-discrepancy treatment since each name's own noise averages out
     independently) puts the "hard" dimensions where QMC is most useful.

Trade-off disclosed, not hidden: a k-factor model can only ever
APPROXIMATE the full empirical correlation matrix (exact only if k equals
the matrix's rank) -- see reconstruction_error() below, used in tests to
confirm accuracy improves monotonically with k and is small already at a
modest k for this book's actual matrix (its top few eigenvalues capture
most of the total variance, typical of real equity correlation matrices,
which tend to have one dominant "market" factor).
"""
import numpy as np


def build_pca_factor_loadings(corr_matrix, n_factors):
    """corr_matrix: (n, n) numpy array (already PSD-cleaned, see
    simulation/engine.py's _nearest_psd). Returns (B, idio_var):
      B: (n, n_factors) loading matrix, columns = top-n_factors
         eigenvectors scaled by sqrt(eigenvalue) -- B @ B.T is the
         "systematic" part of the correlation matrix.
      idio_var: (n,) the leftover diagonal variance per name
         (1 - sum of squared loadings across factors), clipped at 0 --
         this is what makes each simulated name's total variance come
         back to 1 despite only partially explaining its correlation
         with everything else.
    """
    n = corr_matrix.shape[0]
    if not (1 <= n_factors <= n):
        raise ValueError(f"n_factors must be in [1, {n}], got {n_factors}")

    vals, vecs = np.linalg.eigh(corr_matrix)  # ascending
    order = np.argsort(vals)[::-1]
    vals, vecs = vals[order], vecs[:, order]

    top_vals = np.clip(vals[:n_factors], 0.0, None)
    top_vecs = vecs[:, :n_factors]
    B = top_vecs * np.sqrt(top_vals)  # (n, n_factors)

    communality = np.sum(B ** 2, axis=1)
    idio_var = np.clip(1.0 - communality, 0.0, None)
    return B, idio_var


def reconstruct_correlation(B, idio_var):
    """corr_hat = B @ B.T + diag(idio_var) -- the factor model's own
    approximation of the correlation matrix it was fit from."""
    return B @ B.T + np.diag(idio_var)


def reconstruction_error(corr_matrix, B, idio_var):
    """Max absolute entrywise error between the real correlation matrix and
    the k-factor reconstruction -- the honest accuracy metric for "how much
    is lost" by using k factors instead of the full matrix."""
    corr_hat = reconstruct_correlation(B, idio_var)
    return float(np.max(np.abs(corr_matrix - corr_hat)))


def explained_variance_ratio(corr_matrix, n_factors):
    """Fraction of the correlation matrix's total eigenvalue mass captured
    by the top n_factors -- the standard PCA "how much is this k good for"
    diagnostic, independent of which names load on which factor."""
    vals = np.linalg.eigvalsh(corr_matrix)
    vals = np.clip(vals[::-1], 0.0, None)  # descending
    total = vals.sum()
    return float(vals[:n_factors].sum() / total) if total > 0 else 0.0
