"""
Backtesting of the simulated exposure quantiles against realised outcomes
(Basel-style Kupiec proportion-of-failures test, plus Christoffersen's
independence test).

What is tested. For a FIXED (static) set of positions, at each historical
as-of date t0 the model is calibrated ONLY on data up to t0 (rolling window,
no look-ahead) and asked for the 99th/95th percentile of the 10-business-day
change in the position's value. The realised change is then read off history.
An "exception" is a realised move above the predicted quantile. If the model
is right, exceptions occur with probability 1 - confidence, independently.
Windows do not overlap (step = horizon), so the independence assumption of
the Kupiec test is not violated by construction; shifting the starting phase
gives several series to check robustness.

Two legs are backtested:
  * equity/FX leg: each netting set's equity TRS positions (USD value of
    shares, JPY names through USDJPY), lognormal model with the historical
    covariance of the window (the engine's own equity/FX model);
  * rates leg: 10-day change of a Treasury yield at 5y/10y/20y against the
    one-factor Hull-White model's normal distribution, for two choices of
    sigma (overnight-SOFR realised vol, and the long-end fit now used).
The statistic is the standard one: with x exceptions in n trials and
p = 1 - confidence,
    LR_pof = -2 ln[(1-p)^(n-x) p^x] + 2 ln[(1-x/n)^(n-x) (x/n)^x] ~ chi2(1).
Low power is inherent (n non-overlapping 10-day windows per series), which
is why results are reported with the exception count and the expected count.
"""
import numpy as np
from scipy import stats


def kupiec_pof(x, n, p):
    """Kupiec proportion-of-failures likelihood-ratio test. p is the model's
    exception probability (0.01 for a 99% quantile). Returns dict with the
    exception count, rate, expected count, LR statistic and p-value."""
    x, n = int(x), int(n)
    if n <= 0:
        return {"x": x, "n": n, "rate": float("nan"), "expected": float("nan"),
                "lr": float("nan"), "p_value": float("nan")}
    phat = x / n

    def ll(q):
        # x ln q + (n-x) ln(1-q), with 0 ln 0 = 0
        out = 0.0
        if x > 0:
            out += x * np.log(q)
        if n - x > 0:
            out += (n - x) * np.log(1.0 - q)
        return out

    lr = max(-2.0 * (ll(p) - ll(phat)), 0.0)
    return {"x": x, "n": n, "rate": phat, "expected": p * n, "lr": float(lr),
            "p_value": float(1.0 - stats.chi2.cdf(lr, df=1))}


def christoffersen_independence(hits):
    """LR test that exceptions do not cluster (first-order Markov). Returns
    (lr, p_value); (nan, nan) when the series has no exceptions or too few
    transitions to estimate."""
    h = np.asarray(hits, dtype=int)
    if len(h) < 3 or h.sum() == 0:
        return float("nan"), float("nan")
    a, b = h[:-1], h[1:]
    n00 = int(np.sum((a == 0) & (b == 0)))
    n01 = int(np.sum((a == 0) & (b == 1)))
    n10 = int(np.sum((a == 1) & (b == 0)))
    n11 = int(np.sum((a == 1) & (b == 1)))
    if (n00 + n01) == 0 or (n10 + n11) == 0:
        return float("nan"), float("nan")
    pi01 = n01 / (n00 + n01)
    pi11 = n11 / (n10 + n11)
    pi = (n01 + n11) / (n00 + n01 + n10 + n11)

    def ll(pr, k1, k0):
        out = 0.0
        if k1:
            out += k1 * np.log(pr)
        if k0:
            out += k0 * np.log(1.0 - pr)
        return out

    lr = -2.0 * (ll(pi, n01 + n11, n00 + n10) - ll(pi01, n01, n00) - ll(pi11, n11, n10))
    lr = max(float(lr), 0.0)
    return lr, float(1.0 - stats.chi2.cdf(lr, df=1))


def summarize_hits(hits, confidence):
    """Kupiec (and independence) results for a 0/1 exception series."""
    hits = np.asarray(hits, dtype=int)
    k = kupiec_pof(hits.sum(), len(hits), 1.0 - confidence)
    lr_i, p_i = christoffersen_independence(hits)
    k.update({"confidence": confidence, "independence_lr": lr_i, "independence_p": p_i,
              "pass_5pct": bool(k["p_value"] >= 0.05)})
    return k


# ---------------------------------------------------------------- equity / FX leg
def lognormal_move_quantiles(w_usd, cov, currencies_jpy, horizon_days, quantiles, n_draws=20000, seed=7):
    """Quantiles of the change in USD value of positions under the lognormal
    model over `horizon_days`.

    w_usd: USD value of each position at t0 (signed; length m).
    cov  : (m+1, m+1) DAILY-return covariance of [names..., USDJPY] log
           returns; scaled here by `horizon_days`. Column m is USDJPY (JPY
           per USD).
    currencies_jpy: bool array (m) marking JPY-quoted names: their USD value
           moves with exp(l_S - l_FX) - 1.
    """
    m = len(w_usd)
    rng = np.random.default_rng(seed)
    C = cov * horizon_days
    vals, vecs = np.linalg.eigh(C)
    L = vecs * np.sqrt(np.clip(vals, 0.0, None))
    z = rng.standard_normal((n_draws, m + 1))
    ell = z @ L.T - 0.5 * np.diag(C)[None, :]
    lr = ell[:, :m] - np.where(currencies_jpy, 1.0, 0.0)[None, :] * ell[:, [m]]
    dv = ((np.exp(lr) - 1.0) * w_usd[None, :]).sum(axis=1)
    return np.quantile(dv, quantiles)


def equity_book_backtest(log_prices, log_fx, positions, is_jpy, window=756, horizon=10, phase=0,
                         confidences=(0.95, 0.99), min_names=1, n_draws=20000):
    """Rolling out-of-sample backtest of one netting set of equity positions.

    log_prices: DataFrame (dates x names) of log LOCAL-currency closes.
    log_fx    : Series of log USDJPY on the same dates (JPY per USD).
    positions : {name: signed shares} (receive equity +, pay equity -).
    is_jpy    : {name: bool}.
    Returns {confidence: {"hits", "pred", "real", "dates"}}.
    """
    names = [n for n in positions if n in log_prices.columns]
    df = log_prices[names].join(log_fx.rename("_fx"), how="inner")
    ret = df.diff()
    idx = df.index
    jpy = np.array([bool(is_jpy[n]) for n in names])
    shares = np.array([positions[n] for n in names], dtype=float)
    out = {c: {"hits": [], "pred": [], "real": [], "dates": []} for c in confidences}
    t0 = window + phase
    while t0 + horizon < len(df):
        hist = ret.iloc[t0 - window + 1:t0 + 1]
        ok = [i for i, n in enumerate(names)
              if hist[n].notna().all() and np.isfinite(df[n].iloc[t0]) and np.isfinite(df[n].iloc[t0 + horizon])]
        if len(ok) >= min_names:
            nm = [names[i] for i in ok]
            cov = hist[nm + ["_fx"]].cov().values
            fxs, fxh = np.exp(df["_fx"].iloc[t0]), np.exp(df["_fx"].iloc[t0 + horizon])
            sh, jp = shares[ok], jpy[ok]
            s0 = np.exp(df[nm].iloc[t0].values)
            s1 = np.exp(df[nm].iloc[t0 + horizon].values)
            v0 = s0 / np.where(jp, fxs, 1.0)
            v1 = s1 / np.where(jp, fxh, 1.0)
            real = float((sh * (v1 - v0)).sum())
            qs = lognormal_move_quantiles(sh * v0, cov, jp, horizon, list(confidences), n_draws)
            for c, q in zip(confidences, qs):
                out[c]["hits"].append(int(real > q))
                out[c]["pred"].append(float(q))
                out[c]["real"].append(real)
                out[c]["dates"].append(str(idx[t0].date()))
        t0 += horizon
    for c in confidences:
        out[c]["hits"] = np.array(out[c]["hits"], dtype=int)
    return out


# ---------------------------------------------------------------- rates leg
def hw_yield_move_sd(sigma, a, tenor, horizon_days=10):
    """Standard deviation of the 10-business-day change of the zero rate at
    `tenor` in one-factor Hull-White (Gaussian, so no level dependence)."""
    f = 1.0 if a < 1e-10 else (1.0 - np.exp(-a * tenor)) / (a * tenor)
    h = horizon_days / 252.0
    var_r = sigma ** 2 * h if a < 1e-10 else sigma ** 2 * (1.0 - np.exp(-2.0 * a * h)) / (2.0 * a)
    return f * np.sqrt(var_r)


def rates_backtest(yields, tenor, sigma_at, a, window=756, horizon=10, phase=0, confidences=(0.95, 0.99)):
    """Out-of-sample backtest of the model's distribution of the 10-day change
    in a yield. `sigma_at(t0_index)` returns the model sigma calibrated only
    on data up to t0. Exceptions are counted on each tail separately (up: the
    yield rises by more than the model's `confidence` quantile; down likewise);
    the exposure-relevant side depends on the position.
    Returns {confidence: {"up", "down", "dates"}}."""
    y = yields.dropna()
    out = {c: {"up": [], "down": [], "dates": []} for c in confidences}
    t0 = window + phase
    while t0 + horizon < len(y):
        sd = hw_yield_move_sd(sigma_at(t0), a, tenor, horizon)
        d = float(y.iloc[t0 + horizon] - y.iloc[t0])
        for c in confidences:
            z = stats.norm.ppf(c)
            out[c]["up"].append(int(d > z * sd))
            out[c]["down"].append(int(d < -z * sd))
            out[c]["dates"].append(str(y.index[t0].date()))
        t0 += horizon
    for c in confidences:
        out[c]["up"] = np.array(out[c]["up"], dtype=int)
        out[c]["down"] = np.array(out[c]["down"], dtype=int)
    return out
