# Bloomberg data upgrade: swaption-based calibration, real FX forwards, real JPY curve

The user provided a one-time Bloomberg data export
(`data/raw/bloomberg/data_bloomberg/`, gitignored — licensed data, not
redistributed via the repo) dated **2026-08-31** (3 days after our
Databento/yfinance snapshot of 2026-08-28 — close enough for curve-shape
and vol calibration, disclosed rather than treated as identical). It
directly fills three gaps the project had explicitly flagged as
unresolved: a genuine swaption-based Hull-White calibration, real USDJPY
forward points, and a real JPY OIS curve.

## What's in the export

Per its own `metadata/manifest.csv` and `data_gaps_and_exclusions.csv`:

| Series | Coverage | Used here? |
|---|---|---|
| USD SOFR: history, market-quote curve, Bloomberg zero curve, **ATM normal swaption vol cube** | Full history (2017–2026) for the curve/history pieces; single 2026-08-31 snapshot for the swaption cube | **Yes** — swaption cube (calibration), zero curve (JPY differential cross-check) |
| JPY OIS: curve + swaption vols | **Single 2026-08-31 snapshot only** — no full history | **Yes** — zero curve (JPY differential) |
| USDJPY: spot, forward points, implied vol surface | Full history (2017–2026) | **Yes** — spot + forward points (real FX forward curve) |
| SPX / TOPIX implied vol | **Single 2026-08-31 snapshot, INDEX level only** | **No** — our engine needs per-single-name vol for 37 individual equities, not one index-level number; not directly usable without a separate basis assumption, so left for a future pass rather than force-fit |

`src/risk_engine/market/bloomberg.py` is the only place that parses these
files; everything else consumes its outputs.

## 1. Swaption-based Hull-White calibration (the real, standard method)

`models/hw_calibration.py`'s own docstring, written before this data
existed, said: *"the standard way to calibrate `a` is against swaption/cap
implied volatilities, which we don't have access to."* We now do.

**Method** (`calibrate_mean_reversion_from_swaptions`): same exponential-
decay-of-vol-with-tenor regression already used for the futures-based
calibration, applied to the real ATM normal swaption vol cube's 1-month
expiry row (closest to "an option starting almost immediately") across
swap tenors up to 15 years (the book's relevant horizon; far-end tenors
20–30Y reflect different, pension-driven market dynamics not informative
here).

**Result: a = 0.0167, R² = 0.84** — a strong fit, but **meaningfully
different** from the earlier futures-vol-decay proxy's **a = 0.0458**.
Both are real, legitimate calibrations from real data; they differ because
they use different instruments and methods (futures-implied forward-rate
vol vs. swaption-implied swap-rate vol). Since swaption vols are the
genuine industry-standard input, **the swaption-based value is now
preferred** — `models/calibration.py`'s `load_or_calibrate_mean_reversion`
tries it first, falling back to the futures-based route only if the
Bloomberg data isn't present.

**Honest note on the simplification still being made:** using one
short-expiry row of the vol cube (rather than fitting the whole 2D
expiry×tenor grid jointly, which would need to actually price swaptions
under HW1F, e.g. via the Jamshidian decomposition) is standard practice
for a quick alpha estimate, not the most rigorous possible calibration —
disclosed in the code, not hidden.

## 2. Real JPY-USD rate differential (replacing a single futures point)

The constant JPY-USD differential used for JPY-compo equity/FX drift
(`models/equity_fx.py`) previously came from a single CME JPY futures
(6J) contract via covered interest parity — one noisy point.

**New preferred method** (`implied_jpy_usd_rate_diff_from_bloomberg`):
read the differential directly off two **real, directly-quoted** Bloomberg
zero curves (USD SOFR and JPY OIS) at a matching tenor (12M).

**Result: 2.64%** — dramatically larger than the old 6J-futures estimate
(~0.7–1.1% across various runs). **Cross-validated against a second,
completely independent real Bloomberg series** (the separately-quoted
USDJPY forward points, via covered interest parity): **2.83%** — close
agreement (~19bp) between two independent real sources, strongly
suggesting the new number is correct and the old single-futures-point
estimate was a real underestimate, not that the new one is wrong.

This is a materially important correction: it directly affects the drift
used for both JPY-compo equity names and the USDJPY FX process in
simulation, and the U.S./Japan short-rate differential (currently ~4% vs.
~1.5% given real 2026-08-31 quotes) is large enough that getting this
number right matters for the 2 JPY-compo trades' simulated exposure.

`build_calibration()` now tries the Bloomberg-curve route first, falling
back to the original 6J-futures route only if the Bloomberg data isn't
present.

## 3. Real USDJPY forward curve (filling a stub)

`market/fx.py`'s `fetch_forward_points`/`build_fx_curve` were explicitly
stubbed (`NotImplementedError`) — no free live source existed. Now
implemented using the Bloomberg forward points.

**Method:** rather than only supporting covered-interest-parity forwards
derived from our own USD curve alone (the pre-existing `FxCurve` behavior,
which has no JPY-side information at all), `build_fx_curve` inverts CIP
using the **real quoted forward** at each tenor to back out an **implied
JPY discount curve**:

```
DF_jpy(T) = DF_usd(T) * spot / forward(T)
```

Handing that implied curve to `FxCurve` as its `quote_curve` means
`FxCurve.forward(T)` reproduces the real quoted market forward **exactly**
at every tenor used to build it — verified directly (`diff = 0.00e+00` at
every tested tenor: 1W, 2W, 3W, 1M, 2M, 3M), not approximately.

**Honest limitation:** this upgrades the deterministic/pricing-time FX
curve only — it does not change `models/equity_fx.py`'s constant-
differential simplification for the *simulated* JPY process (a full
stochastic JPY curve factor remains future work, same conclusion as
before, just now backed by better point-in-time data).

## Validation

- All 3 new pieces have dedicated tests (`tests/test_bloomberg_
  calibration.py`, 5 tests) — skipped automatically if the Bloomberg data
  export isn't present, so they don't break a fresh clone or CI.
- Full project test suite: 28/28 passing (23 previous + 5 new).
- Re-ran `scripts/run_simulation.py` end-to-end after wiring all three
  changes in: still validates to exactly 0.0000% internal consistency at
  t=0. (A visible EE(0) difference vs. the previous run for CPTY_B is
  expected live-data drift between separate runs — equity/FX spots are
  fetched live and move over time — not caused by today's changes, since
  drift parameters only affect *future* simulated paths, not today's
  deterministic snapshot.)

## What wasn't done (explicitly out of scope for this pass)

- SPX/TOPIX implied vols: index-level only, not usable for our 37
  individual equity names without a separate, undocumented basis
  assumption — not force-fit in.
- A full second stochastic JPY short-rate factor (using the real JPY OIS
  curve/swaption vols to build a proper JPY Hull-White model, correlated
  with the USD one) — a meaningfully larger undertaking than the 3 pieces
  above; the real JPY curve is now used for a better point-in-time
  snapshot value, but the *simulated* JPY process is still the constant-
  differential approximation.
- A full 2D (expiry × tenor) swaption-cube fit for Hull-White — the
  single-row approximation is disclosed as a real simplification, not the
  most rigorous possible route.
