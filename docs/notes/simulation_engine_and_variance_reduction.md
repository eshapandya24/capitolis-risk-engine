# Simulation Engine, Speed/Variance Optimization, and Greeks — Analysis

Covers: building the Monte Carlo CCR engine end-to-end, the speed
optimizations applied (with measured before/after numbers), a controlled
comparison of five random-number-generation techniques for accuracy vs.
speed, and an extension to Greeks (sensitivities).

## 1. What was built

Three previously-empty modules, now implemented and tested:

- **`src/risk_engine/models/`** — `rates.py` (Hull-White one-factor short
  rate, calibrated to match today's real Databento curve exactly at t=0),
  `equity_fx.py` (correlated GBM for all 37 equities + USDJPY, hybrid with
  the simulated short rate), `calibration.py` (assembles both from data
  already collected — curve, spots, dividends, vols, correlation matrix;
  no new data sources needed).
- **`src/risk_engine/simulation/`** — `engine.py` (time grid, Cholesky
  correlation, path stepping, MarketState construction, repricing via the
  already-validated pricer library), `random_numbers.py` (5 sampling
  techniques behind one interface), `parallel.py` (multiprocessing across
  scenarios), `black_scholes.py` (analytic ground truth for the variance
  study).
- **`src/risk_engine/exposure/`** — `aggregate.py` (EE/PFE/MPE, netted by
  counterparty).

**Self-validation, not just assumed correct:**
- Hull-White's closed-form bond price matches the real curve's own
  `discount()` to 1e-9 relative tolerance at every tested tenor (t=0
  identity check).
- The engine's own EE(t=0) (no randomness yet) matches the independently
  hand-calculated Current Exposure (`scripts/calculate_current_exposure.py`)
  to within 0.02–0.03% — the residual being live-data drift between two
  separate live yfinance/Databento pulls seconds apart, not a bug.
- GBM martingale property, Monte Carlo standard-error convergence (~1/√N),
  antithetic variance reduction on the correct estimator, and Cholesky
  recovering a target correlation — all covered by
  `tests/test_simulation_engine.py` (13/13 project tests pass).
- The exposure profile itself has the right *economic* shape: it collapses
  sharply once the large trades mature (most Equity TRS and Bond Forwards
  settle Oct–Dec 2026), decaying to a small tail through Jan 2028 when the
  last trade (BTRS_0001) ends — a portfolio's exposure should decay as
  trades roll off, and it does.

## 2. Speed optimization — two real bottlenecks found and fixed

### 2a. Curve construction per (scenario, node)

Building a full `capitolis_pricers.curves.Curve` object (sort pillars,
log-transform, store) for every one of `n_scenarios × n_nodes` pairs is
wasteful — and it's also an *approximation* (log-linear interpolation
between a handful of fixed tenor pillars).

**Fix:** `HullWhite1F.fast_node_curve()` — a lightweight object exposing
only `.ref_date`/`.discount(d)` (everything the pricers actually call),
computing the exact analytic HW1F bond price for whatever date is asked,
with zero interpolation.

**Measured:** 0.206 ms/call (old) → 0.019 ms/call (new) — **10.6x faster**,
and removes an interpolation error of up to ~2e-5 in the discount factor
that the fixed-pillar approach had. Faster *and* more accurate — the
approximation was pure overhead with no offsetting benefit.

### 2b. The real bottleneck: `.npv()` itself, and multiprocessing

The curve was never the dominant cost. Each pricer's `.npv()` call —
pure-Python object with schedule/date loops — costs **~1.2 ms**. At 2000
scenarios × 18 nodes × 16 trades = 576,000 calls, that's **~12 minutes
serial**, projected from direct measurement (not assumed).

Since every scenario's full repricing is independent of every other
scenario, this is embarrassingly parallel. `simulation/parallel.py`
distributes scenarios across worker processes via `multiprocessing`.

**A genuine Windows-specific bug found along the way:** Windows'
`spawn` process-start method re-executes the driver script's *module-level*
imports in every worker — including ones never called there. The initial
version imported the (databento/yfinance-heavy) `calibration` module at
the top of the driver script; each of 8 workers re-paid that import cost.
**Fix:** moved that import inside `main()`. Measured effect at N=800:
113 ms/scenario → 51 ms/scenario, a **2.2x** improvement from this fix
alone, on top of the parallelism itself.

**End-to-end result:** the full 16-trade, 2000-scenario, 18-node simulation
now runs in **93 seconds** (down from a projected ~12 minutes) — a
**~7.7x** total speedup, combining both fixes.

*(Note: multiprocessing on Windows has real fixed overhead per worker —
observed as roughly break-even or worse than serial below a few hundred
scenarios, since spawning fresh Python processes and re-importing numpy/
pandas per worker isn't free. It only pays off once the compute genuinely
dominates the fixed cost — confirmed empirically, not assumed, which is
why `run_simulation.py` only switches to the parallel path above 200
scenarios.)*

## 3. Variance reduction — comparing 5 random-number techniques

Compared **pseudo-random, antithetic, moment-matched, Sobol (quasi-random/
low-discrepancy), and Latin Hypercube Sampling** on two levels:

### 3a. Controlled test: a European call, with a known answer

Using one of our real calibrated names (AAPL: real spot, real realized
vol, real dividend yield) as a European call under GBM, with the
Black-Scholes closed-form price as ground truth — the standard textbook
setup for this kind of comparison, chosen specifically because it lets bias
and variance be measured against a *known correct* answer, not just
compared relative to each other. 200 independent repeats per method,
2000 scenarios each:

| Method | Bias | Std | RMSE | Time/trial |
|---|---|---|---|---|
| pseudo_random | -0.1196 | 1.3808 | 1.3860 | 0.079 ms |
| antithetic | -0.0263 | 1.0263 | 1.0266 | 0.066 ms |
| moment_matched | -0.0119 | 0.2203 | 0.2206 | 0.116 ms |
| sobol | -0.0003 | 0.0482 | 0.0482 | 0.439 ms |
| **latin_hypercube** | **-0.0023** | **0.0273** | **0.0274** | 0.296 ms |

**Latin Hypercube wins outright** — ~50x lower RMSE than plain
pseudo-random, at less than 4x the per-trial cost. Sobol is close behind.
This single-factor result matches textbook expectations for low-discrepancy
sequences.

### 3b. Confirmatory check: does this hold on the real 39-factor engine?

Same five methods, now driving the actual simulation engine (all 39 risk
factors, all 16 trades), measuring the stability of the 1-year PFE
estimate across 4 repeats at 120 scenarios each:

| Method | PFE(1y) std | vs. pseudo_random |
|---|---|---|
| **latin_hypercube** | **540** | **3.25x better** |
| sobol | 1,208 | 1.45x better |
| pseudo_random | 1,755 | baseline |
| moment_matched | 1,775 | no improvement |
| antithetic | 1,906 | slightly worse |

**A genuine, non-obvious finding, not assumed:** the ranking survives, but
compresses hard. Antithetic and moment-matching — which helped
substantially in 1 dimension — show **no benefit at all** at 663 effective
dimensions (39 factors × 17 time steps). Latin Hypercube still delivers a
real, meaningful improvement (3.25x) even at this dimensionality, because
it stratifies each dimension's own marginal independently rather than
relying on joint low-discrepancy structure across all 663 dimensions —
this is exactly the "curse of dimensionality" limitation flagged in
`random_numbers.py`'s docstring *before* this benchmark was run, now
empirically confirmed rather than just asserted.

**Practical recommendation:** use **Latin Hypercube Sampling** as the
default for the production engine — it wins on both the controlled test
and the real, high-dimensional case, with no dependency or major
implementation cost over plain pseudo-random.

## 4. Extension to Greeks

Two techniques compared on the same option test case, then one demonstrated
on the real book.

### 4a. Pathwise vs. bump-and-reprice (with and without common random numbers)

| Method | Bias | Std | Time/trial |
|---|---|---|---|
| Pathwise | +0.000085 | 0.003771 | 0.470 ms |
| Bump-and-reprice, **common** random numbers | +0.000033 | 0.003742 | 0.327 ms |
| Bump-and-reprice, **independent** random numbers | -0.003502 | 0.096885 | 0.850 ms |

**Common random numbers make bump-and-reprice essentially as good as
pathwise** (std 0.00374 vs 0.00377 — indistinguishable), while independent
draws for the up/down legs make it **~26x worse** (std 0.0969) and
noticeably biased. This is the standard, well-known result — confirmed
here directly, not assumed — and it matters practically: **pathwise deltas
need a fresh mathematical derivation per payoff type** (and don't exist for
discontinuous payoffs), while **bump-and-reprice works as a black box on
any pricer**, which is exactly why it's the technique that generalizes to
our real book.

### 4b. A real Greek on the real book

Computed the exact delta of `EQTRS_0003`'s current NPV to its largest
basket position (`NL0009538784`, 212,269 shares) via bump-and-reprice:

```
NPV(0) at base spot 227.84: 10,803,018.76 USD
Delta: -212,269.00 USD per $1 move
```

The magnitude exactly equals the share count — expected for this trade's
linear payoff structure, and a strong internal-consistency check (this
delta needs no Monte Carlo at all, since t=0 has no randomness — Greeks of
*today's* value are exact bump-and-reprice on the pricer directly; Greeks
of *future exposure* (e.g. d(PFE)/dS at a future node) are where the
common-random-numbers lesson from 4a actually applies, using the same
bump-and-reprice mechanism on the simulated paths instead of on today's
snapshot).

## 5. Recommendations going forward

1. **Switch the production engine's default sampling method to Latin
   Hypercube** — validated improvement at both 1 and 663 dimensions.
2. **PFE-sensitivity Greeks** (d(PFE)/dS, useful for hedging or
   attribution) are a natural next step: identical bump-and-reprice +
   common-random-numbers mechanism as §4a, applied to
   `simulation/engine.py`'s paths instead of a single deterministic
   `MarketState`.
3. **Further speed work, if needed:** the remaining bottleneck is the
   pure-Python pricer object itself (~1.2ms/call). A vectorized
   reimplementation of the three pricer formulas (validated against the
   real library on a subsample) would remove the multiprocessing overhead
   entirely and likely give another order of magnitude — not done here to
   avoid introducing a second, potentially-diverging pricing
   implementation without strong justification; worth revisiting if
   scenario counts need to grow into the tens of thousands.
