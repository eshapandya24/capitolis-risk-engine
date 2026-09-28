"""
Exact rate-bump repricing WITHOUT resimulation: uses the same Latin Hypercube
draws (common random numbers) already in the base run's simulated paths to
compute rate Greeks, the same idea already used for equity/FX bumps (spot
bumps rescale every GBM path exactly, Report 9.1), extended here to the rate
curve itself.

Why this is possible. In the one-factor Hull-White model, the short rate is

    r(t) = x(t) + alpha(t)

where x(t) is the zero-mean Ornstein-Uhlenbeck factor actually simulated
(models/rates.py) and alpha(t) is a DETERMINISTIC function of the curve, `a`
and `sigma` only (not of the random draws). A curve bump that leaves `a` and
`sigma` unchanged (as every DV01/key-rate bump in this project does) changes
alpha(t) only -- so x(t) is IDENTICAL, path by path, between the base and
the bumped curve: the stochastic part of every simulated path is literally
unaffected by a rate-curve bump.

The equity/FX log-Euler step (models/equity_fx.py) uses r(t) piecewise-
constant over each step, entering the DRIFT only (never the diffusion):

    USD equity name    d ln S = (r_USD(t) - q - s^2/2) dt + s dW
    JPY-listed name     no r_USD(t) dependence at all (uses r_JPY only)
    USDJPY (ln X)      d ln X = (r_JPY(t) - r_USD(t) + s_X^2/2) dt + s_X dW_X

So bumping the USD curve changes each step's drift by a purely deterministic
amount [alpha_bumped(t_k) - alpha_base(t_k)] * dt_k -- the SAME number on
EVERY simulated scenario, for every USD name, with the opposite sign for
USDJPY, and no effect at all on JPY-listed names. Accumulating this over the
grid gives an exact, closed-form SHIFT to apply to the base run's own
ln_spot / ln_fx paths; x_rate, x_jpy and y_rate (if a G2++/second rate factor
is in use -- not supported by this module, see below) are reused unchanged.
Repricing the shifted paths reproduces, to floating-point precision, what a
full resimulation with the identical random draws would give -- because it
IS that resimulation, computed without drawing anything or stepping the SDE
again.

Limits: HW1F only (the report's default rates model; G2++ has a second,
correlated OU factor whose own contribution to alpha is not implemented
here -- fall back to resimulation for that model). The USD curve only (JPY
curve bumps are not covered by this module).
"""
import numpy as np


def _cum_alpha_offset(hw_base, hw_bumped, times):
    """Cumulative sum_{k<K} [alpha_bumped(t_k) - alpha_base(t_k)] * dt_k at
    every grid node K (length len(times), first entry 0). This is exactly
    the deterministic drift offset the equity/FX step accumulates, since
    both models step piecewise-constant drift over dt = times[k+1]-times[k]
    using the short rate at times[k]."""
    times = np.asarray(times, dtype=float)
    offset_k = np.array([hw_bumped.alpha(t) - hw_base.alpha(t) for t in times[:-1]])
    dt = np.diff(times)
    cum = np.concatenate([[0.0], np.cumsum(offset_k * dt)])
    return cum


def fast_rate_bump_paths(base_paths, hw_base, hw_bumped, currencies):
    """A new paths dict, identical to `base_paths` except ln_spot (USD names)
    and ln_fx are shifted by the exact deterministic curve-bump offset;
    ln_spot for JPY-listed names, x_rate, x_jpy and y_rate are copied
    unchanged (see module docstring for why). `currencies`: {isin: "USD"|
    "JPY"}, matching CorrelatedGBM.currencies."""
    times = base_paths["_times"] if "_times" in base_paths else None
    if times is None:
        raise ValueError("base_paths must include '_times' (the engine's own time grid); "
                         "pass paths=dict(engine.simulate_paths(), _times=engine.times)")
    cum = _cum_alpha_offset(hw_base, hw_bumped, times)  # (n_nodes,)

    out = dict(base_paths)
    out["ln_spot"] = {}
    for isin, arr in base_paths["ln_spot"].items():
        if currencies.get(isin) == "JPY":
            out["ln_spot"][isin] = arr             # unaffected, no resimulation needed
        else:
            out["ln_spot"][isin] = arr + cum[np.newaxis, :]
    out["ln_fx"] = base_paths["ln_fx"] - cum[np.newaxis, :]
    return out
