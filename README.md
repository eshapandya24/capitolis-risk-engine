# Capitolis Counterparty Credit Risk Engine

Monte Carlo counterparty credit risk (CCR) engine for Capitolis' ESF
derivatives book — Equity TRS (incl. JPY compo), Bond Forwards, and Bond
TRS.

## Structure

```
.
├── data/
│   ├── raw/                   # untracked raw pulls (gitignored)
│   ├── processed/             # untracked cleaned/cached data (gitignored)
│   ├── MARKET_DATA.md         # collection checklist: source, status, per series
│   └── MARKET_DATA_source.md  # original field spec (from capitolis_pricers)
├── trade_data/                 # the 16 trades + underlyings (Capitolis-supplied)
├── capitolis_pricers/           # pricing library (Capitolis-supplied, standard-library only)
├── src/risk_engine/
│   ├── market/                 # MarketState construction: fetch/clean/cache per source
│   ├── models/                 # Hull-White rate model + correlated GBM equity/FX, calibrated to real data
│   ├── simulation/             # Monte Carlo engine: paths, repricing, multiprocessing, RNG techniques
│   ├── exposure/                # EE/PFE/MPE aggregation, netted by counterparty
│   └── validation/              # analytical benchmarks (e.g. bond forward closed form)
├── scripts/                     # data pulls, full-book pricing, simulation driver, benchmarks
├── notebooks/                   # exploration notebooks
├── tests/                       # validation + unit tests
└── docs/
    ├── kickoff_deck.pdf
    ├── pricer_contract.md       # original capitolis_pricers/README.md
    └── notes/                    # dated check-in / review / analysis notes
```

## Install

```bash
pip install -r requirements.txt
```

or, with the package layout:

```bash
pip install -e .
```

Real data collection also needs a Databento API key set as the
`DATABENTO_API_KEY` environment variable (never committed, never passed
inline — see `src/risk_engine/market/sofr.py`).

## Run

Price the sample trades against the pricer library's illustrative sample
market (only the 4 Bond Forward / Bond TRS trades succeed against it — the
sample market only ships 3 placeholder equity spots, not the 37 real names):

```bash
python -m capitolis_pricers.examples.price_all
```

Price the full 16-trade book against real, live market data (SOFR curve via
Databento, equity spots + FX via yfinance):

```bash
python scripts/price_full_book_real_data.py
```

Calculate today's Current Exposure, gross and netted by counterparty:

```bash
python scripts/calculate_current_exposure.py
```

Run the full Monte Carlo simulation — calibrates models from real data,
simulates correlated paths, reprices the book at every scenario/node, and
produces EE/PFE/MPE profiles (self-validates against Current Exposure):

```bash
python scripts/run_simulation.py --scenarios 2000
```

Pull 3 years of historical data for volatility/correlation calibration:

```bash
python scripts/pull_historical_data.py
```

Compare random-number-generation techniques for speed/accuracy, and Greeks
techniques (pathwise vs. bump-and-reprice):

```bash
python scripts/benchmark_variance_reduction.py
python scripts/compute_greeks_demo.py
```

Run tests:

```bash
pip install pytest
pytest tests/
```

## Status

**Done:**
- Explored `capitolis_pricers/` and read the full pricer contract
  ([`docs/pricer_contract.md`](docs/pricer_contract.md)); summarized field
  contracts and conventions in
  [`docs/notes/pricer_review.md`](docs/notes/pricer_review.md).
- Repo reorganized; flattened the doubled `capitolis_pricers/capitolis_pricers/`
  nesting from the original zip.
- Inventoried all 16 trades by instrument type and counterparty, listed the
  41 underlying equity basket rows (37 unique names) and 5 bond types.
- All five market data series pulled, built, and independently validated
  (USD curve vs. Treasury.gov, historical vols/correlations sanity-checked)
  — see [`data/MARKET_DATA.md`](data/MARKET_DATA.md) for sources, methods,
  and bugs found and fixed along the way.
- All 16 trades price end-to-end against real market data; Current Exposure
  (gross and netted by counterparty) calculated from real MTMs.
- **The Monte Carlo simulation engine is built end-to-end**: a Hull-White
  one-factor rate model + correlated GBM for all 37 equities/USDJPY,
  calibrated entirely from data already collected, simulating the book
  forward and producing full EE/PFE/MPE exposure profiles. Self-validates
  (EE(t=0) matches hand-calculated Current Exposure to ~0.02%; the exposure
  profile correctly collapses once trades mature). See
  [`docs/notes/simulation_engine_and_variance_reduction.md`](docs/notes/simulation_engine_and_variance_reduction.md)
  for the full build writeup, two measured speed optimizations (10.6x from
  an exact analytic discount curve; a further 2.2x from fixing a Windows
  multiprocessing bug), a controlled comparison of 5 random-number
  techniques (Latin Hypercube wins on both a toy option case and the real
  39-factor engine), and an extension to Greeks (pathwise vs.
  bump-and-reprice, with and without common random numbers).
- 18 tests across pricer validation, market data (SOFR curve, correlations),
  and the simulation engine (Hull-White/curve identity, GBM martingale
  property, MC convergence, variance reduction, Cholesky correlation) — all
  passing.

**Open:**
- FX forward points beyond spot (no confirmed source yet) — a minor
  simplification in the current FX model, not a blocker.
- Databento's data-availability lag means the rate curve is pinned a few
  days behind the equity/FX spots' live timestamp — a small, disclosed
  inconsistency, not a correctness issue.
- Next: PFE-sensitivity Greeks (d(PFE)/dS at a future node, same
  bump-and-reprice + common-random-numbers mechanism already validated);
  a vectorized pricer reimplementation if scenario counts need to scale
  into the tens of thousands.

## Trades at a glance

| Instrument | Count | Counterparties |
|---|---|---|
| Equity TRS (incl. 2 JPY compo) | 8 | CPTY_A, CPTY_B, CPTY_C |
| Bond Forward | 4 | CPTY_A, CPTY_C |
| Bond TRS | 4 | CPTY_A, CPTY_B, CPTY_C |

41 equity basket rows / 37 unique names, 5 bond types (all US Treasuries).
Full detail in [`docs/notes/pricer_review.md`](docs/notes/pricer_review.md).
