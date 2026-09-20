"""
Basel SA-CVA capital aggregation (BCBS d507 / MAR50.42-MAR50.77) from
already-computed CVA sensitivities. Parameters below are transcribed from
the BIS text "Targeted revisions to the credit valuation adjustment risk
framework" (July 2020), the version in force from 2023: m_CVA = 1,
hedging-disallowance R applies only with hedges (none here).

Per risk class and per delta/vega:
    WS_k   = RW_k * s_k                                 (MAR50.51)
    K_b    = sqrt( sum_k WS_k^2 + sum_{k!=l} rho_kl WS_k WS_l )   (no hedges)
    S_b    = clip( sum_k WS_k, -K_b, +K_b )
    K      = m_CVA * sqrt( sum_b K_b^2 + sum_{b!=c} gamma_bc S_b S_c )   (MAR50.53)
Capital = sum over delta classes + vega classes; RWA = 12.5 * capital.

Risk classes present in this book: interest rate (USD), FX (USDJPY),
counterparty credit spread, equity. Reference credit spread and commodity
classes are absent (no such exposure drivers) and contribute zero.
Counterparty credit spread has no vega requirement (MAR50.63).
"""
import numpy as np

M_CVA = 1.0

# Interest rate delta (specified currencies incl. USD, JPY), tenors 1,2,5,10,30y (MAR50.56)
IR_TENORS = [1, 2, 5, 10, 30]
IR_RW = np.array([0.0111, 0.0093, 0.0074, 0.0074, 0.0074])
IR_RHO = np.array([[1.00, 0.91, 0.72, 0.55, 0.31],
                   [0.91, 1.00, 0.87, 0.72, 0.45],
                   [0.72, 0.87, 1.00, 0.91, 0.68],
                   [0.55, 0.72, 0.91, 1.00, 0.83],
                   [0.31, 0.45, 0.68, 0.83, 1.00]])
IR_VEGA_RW = 1.00       # MAR50.58
FX_DELTA_RW = 0.11      # MAR50.61
FX_VEGA_RW = 1.00       # MAR50.62
CCS_TENORS = [0.5, 1, 3, 5, 10]
CCS_RW = {  # (bucket, quality) -> RW, MAR50.65 Table 7 (bucket 1 uses the 1a value)
    (1, "IG"): 0.005, (2, "IG"): 0.05, (3, "IG"): 0.03, (4, "IG"): 0.03, (5, "IG"): 0.02, (6, "IG"): 0.015, (7, "IG"): 0.05,
    (1, "HY"): 0.23, (2, "HY"): 0.12, (3, "HY"): 0.07, (4, "HY"): 0.085, (5, "HY"): 0.055, (6, "HY"): 0.05, (7, "HY"): 0.12}
CCS_GAMMA = np.array([[1, .10, .20, .25, .20, .15, 0],
                      [.10, 1, .05, .15, .20, .05, 0],
                      [.20, .05, 1, .20, .25, .05, 0],
                      [.25, .15, .20, 1, .25, .05, 0],
                      [.20, .20, .25, .25, 1, .05, 0],
                      [.15, .05, .05, .05, .05, 1, 0],
                      [0, 0, 0, 0, 0, 0, 1.0]])
EQ_GAMMA = 0.15         # MAR50.71, buckets 1-10


def bucket_K(ws, rho):
    ws = np.asarray(ws, dtype=float)
    return float(np.sqrt(max(ws @ rho @ ws, 0.0)))  # rho has a unit diagonal


def aggregate(ws_by_bucket, rho_by_bucket, gamma, m=M_CVA):
    """ws_by_bucket: {b: weighted sensitivities}, rho_by_bucket: {b: matrix},
    gamma: {(b, c): correlation} or scalar for all pairs. Returns (K, {b: K_b})."""
    Kb = {b: bucket_K(ws, rho_by_bucket[b]) for b, ws in ws_by_bucket.items()}
    Sb = {b: float(np.clip(np.sum(ws), -Kb[b], Kb[b])) for b, ws in ws_by_bucket.items()}
    bs = list(Kb)
    total = sum(Kb[b] ** 2 for b in bs)
    for i, b in enumerate(bs):
        for c in bs:
            if b == c:
                continue
            g = gamma if np.isscalar(gamma) else gamma[(b, c)]
            total += g * Sb[b] * Sb[c]
    return m * float(np.sqrt(max(total, 0.0))), Kb


def ccs_rho(names, tenors):
    """Correlation of counterparty credit-spread factors (MAR50.65): tenor
    (1 same / 0.9 else) x name (1 same / 0.5 unrelated) x quality (1 if same
    IG/HY class). All counterparties are assumed unrelated and same quality."""
    keys = [(n, t) for n in names for t in tenors]
    R = np.zeros((len(keys), len(keys)))
    for i, (n1, t1) in enumerate(keys):
        for j, (n2, t2) in enumerate(keys):
            R[i, j] = (1.0 if t1 == t2 else 0.9) * (1.0 if n1 == n2 else 0.5)
    return keys, R


def eq_gamma(buckets):
    return {(b, c): EQ_GAMMA for b in buckets for c in buckets if b != c}
