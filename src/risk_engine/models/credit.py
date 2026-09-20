"""
Counterparty credit inputs for CVA: market-implied default probabilities
from a credit-spread curve, exactly as Basel MAR50.32 requires
(risk-neutral PD from spreads and a market-consensus expected LGD):

    PD(t_{i-1}, t_i) = exp(-s_{i-1} t_{i-1} / LGD) - exp(-s_i t_i / LGD)

Counterparty ratings are ASSUMPTIONS (the book's counterparties are
anonymised as CPTY_A/B/C): see COUNTERPARTY_ASSUMPTIONS.
"""
import numpy as np

LGD = 0.60  # market-consensus ELGD for senior unsecured (recovery 40%)

# Disclosed assumption: no counterparty identities or ratings were provided.
# All three are treated as investment-grade financials (broker/bank-type
# equity-swap counterparties), proxied at BBB, the conventional level for
# unrated counterparties. cva_vs_rating() shows the result for the whole
# rating range so the reader can see how much this assumption matters.
COUNTERPARTY_ASSUMPTIONS = {
    "CPTY_A": {"rating": "BBB", "sector_bucket": 2},
    "CPTY_B": {"rating": "BBB", "sector_bucket": 2},
    "CPTY_C": {"rating": "BBB", "sector_bucket": 2},
}


def spread_at(tenors, spreads, t):
    """Piecewise-linear spread, flat outside the tenor range."""
    return np.interp(t, tenors, spreads)


def survival_prob(t, tenors, spreads, lgd=LGD):
    """Q(t) = exp(-s(t) t / LGD)  (MAR50.32 credit-triangle form)."""
    t = np.asarray(t, dtype=float)
    return np.exp(-spread_at(tenors, spreads, t) * t / lgd)


def marginal_pd(times, tenors, spreads, lgd=LGD):
    """PD_i over (t_{i-1}, t_i] for consecutive grid times (times[0] = 0)."""
    q = survival_prob(times, tenors, spreads, lgd)
    return q[:-1] - q[1:]
