# Calibrating Hull-White's mean reversion

The convergence study (`docs/notes/convergence_study.md`) flagged the
disclosed `a=0.03` textbook assumption as the largest unquantified source
of model uncertainty in the engine — larger than the Monte Carlo sampling
error itself. This replaces it with a real calibration.

## Method

The standard way to calibrate Hull-White's mean reversion `a` is against
swaption/cap implied volatilities, which we don't have access to. Instead,
this uses a real, standard alternative: HW1F predicts that the volatility
of the instantaneous forward rate decays exponentially with time-to-maturity,

```
sigma_f(t, T) = sigma * exp(-a * (T - t))
```

Measuring the REALIZED volatility of several SOFR futures contracts at
different tenors (each contract's implied rate is a proxy for a forward
rate at that tenor, using ~2 years of daily history per contract via
Databento) lets `a` be fit from how fast that volatility decays across
tenors — linear regression of ln(vol) against average tenor, slope = -a.

## Result

| Contract | Avg. tenor | Realized vol |
|---|---|---|
| SR3U6 | 1.05y | 0.84% |
| SR3Z6 | 1.30y | 0.87% |
| SR3H7 | 1.55y | 0.88% |
| SR3U7 | 2.05y | 0.83% |
| SR3H8 | 2.55y | 0.79% |
| SR3U8 | 3.06y | 0.77% |
| SR3H9 | 3.56y | 0.75% |
| SR3H0 | 4.52y | 0.76% |

**Fitted: a = 0.0458** (vs. the disclosed 0.03 assumption), **R² = 0.82** —
a reasonably strong fit, meaning the HW1F exponential-decay assumption is a
decent (not perfect) description of how this vol term structure actually
behaves. The fit's own implied short-end sigma (0.91%) differs somewhat
from the realized SOFR-spot vol used elsewhere in the model (0.63%,
`vols.py`) — expected, since the fit extrapolates back from 1–4.5y tenors
to a zero-tenor intercept, and real markets aren't perfectly HW1F; `sigma`
in the production model still comes from the more directly-interpretable
realized spot vol, only `a` is taken from this fit.

Cached in `data/processed/hull_white_calibration.json`; refresh with
`python scripts/calibrate_hull_white.py`. `models/calibration.py`'s
`build_calibration()` loads it automatically (falling back to a live
recalibration, then to the disclosed textbook value only if both fail).

## Two real bugs found and fixed while doing this

### 1. A second SOFR-curve decade-resolution bug

Testing the calibration against a far-dated contract (`SR3H0`) surfaced a
bug in `sofr.py`'s year-decoding that the earlier fix (see
`data/MARKET_DATA.md` §1) had introduced without noticing: removing the
decade-wrap logic fixed the original problem (recently-expired serial
contracts wrongly wrapped a decade forward) but broke the opposite case —
genuinely far-future contracts (like `SR3H0` = March 2030) whose naive
same-decade resolution lands implausibly far in the past (March 2020) were
now silently dropped as "expired" instead of correctly wrapped forward.

**Fixed** with a threshold: a same-decade resolution more than ~400 days in
the past is treated as implausible for a still-live quote and wrapped
forward a decade; less than that is treated as a genuinely recently-expired
contract and left alone (matching the original fix's intent). Both cases
now have regression tests (`tests/test_sofr_curve.py`).

**Effect**: the SOFR curve now correctly includes all 33 live contracts
(up from 21), extending real futures-implied coverage from ~3.6 years out
to ~6.3 years, with a correspondingly smaller flat-extrapolated tail.
Re-validated against Treasury.gov par yields: spread still widens smoothly
(13bp → 46.5bp, an improvement on the earlier 13bp → 55.6bp, closer now
that less of the long end is extrapolated).

### 2. A stale-comparison false alarm in the simulation's self-validation

After wiring in the new calibration, `run_simulation.py`'s own EE(t=0)
cross-check (against a separately-cached Current Exposure file) suddenly
showed 7–15% "discrepancies" — alarmingly large. Investigation found the
cause: the cached comparison file was ~12.5 hours old, and real market
prices (one name carries 76% annualized volatility) had genuinely moved
overnight — not a bug in the new calibration or the curve fix. Confirmed
by regenerating the comparison fresh and re-running within the same
minute: differences dropped back to the usual ~0.02–0.8% range.

**Fixed properly, not just re-run once:** `run_simulation.py` no longer
compares against a separately-cached file at all. It now computes Current
Exposure directly from the exact same in-memory calibrated snapshot the
simulation itself just used, so live-data staleness can never cause a false
alarm again. This also tightened the check from "within 5%, live-data
drift expected" to "must match to 0.5%, real bug if not" — and after also
fixing a subtle curve-object mismatch (the check was using the original
interpolated curve while the engine internally uses the exact analytic
`FastNodeCurve`), the two now match to **exactly 0.0000%**, a much
stronger internal-consistency guarantee than before.

## Current model status

- Rate model: Hull-White 1F, `sigma` from realized SOFR spot vol (real
  data), `a` from this calibration (real data) — no remaining
  disclosed-guess parameters in the rate model.
- Remaining known simplification: the constant JPY-USD rate differential
  for compo trades (still real-data-derived, from CME JPY futures, but a
  constant rather than a full second stochastic JPY curve) — a reasonable
  scope boundary given only 2 of 16 trades are JPY compo.
