"""
Analytic Black-Scholes European call -- the standard ground truth used to
validate Monte Carlo variance-reduction techniques (see
scripts/benchmark_variance_reduction.py). Not used anywhere in the actual
pricing/exposure pipeline -- our real trades are linear TRS/forwards, not
options; this exists purely so the RNG comparison has a KNOWN correct
answer to measure bias and error against, using one of our real calibrated
equity names' real spot/vol so the comparison is grounded in real numbers.
"""
import math
from scipy.stats import norm


def bs_call_price(S0, K, r, q, sigma, T):
    d1 = (math.log(S0 / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S0 * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)


def bs_call_delta(S0, K, r, q, sigma, T):
    d1 = (math.log(S0 / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    return math.exp(-q * T) * norm.cdf(d1)
