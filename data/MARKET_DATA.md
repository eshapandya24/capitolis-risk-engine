# Market Data Checklist

Tracks collection status for every market-data series required to price and
simulate the book. Field/format specs live in the original source spec,
preserved at [`data/MARKET_DATA_source.md`](MARKET_DATA_source.md) (copied
verbatim from the pricer package's `MARKET_DATA.md`). This file is the
collection checklist reconciled against that spec — see also
[`docs/notes/pricer_review.md`](../docs/notes/pricer_review.md).

No series ship with `capitolis_pricers/` beyond three illustrative sample
spots in `capitolis_pricers/data/sample_market.py` — all five series below
have since been collected from real sources; see each section for details.

## Legend
`not started` · `pulled` (raw data landed in `data/raw/`) · `validated` (checked, cleaned, in `data/processed/`)

## 1. USD OIS (SOFR) discount curve

| Field | Value |
|---|---|
| Source | **Databento** (paid access confirmed) — CME Globex SOFR futures: `SR3` (3-month, primary curve-building instrument) and `SR1` (1-month, short end). No ready-made OIS swap curve is published anywhere; we bootstrap our own curve from futures settlement prices (`futures price -> implied forward rate -> discount factor`) |
| Identifier | Databento dataset `GLBX.MDP3`, parent symbols `SR3.FUT` / `SR1.FUT` |
| Tenors needed | O/N, T/N, 1W, 2W, 1M, 2M, 3M, 6M, 9M, 1Y, 18M, 2Y, 3Y, 4Y, 5Y, 7Y, 10Y |
| Date range | Single as-of snapshot for the valuation date; if a historical-proxy curve build is needed, pull daily back to the depth of the vol/correl lookback (see §5) |
| Frequency | Daily (snapshot as of valuation date) |
| Day count | ACT/360 |
| Status | **pulled + bootstrapped + validated**. `build_curve()` maps each SR3 contract to its 3-month IMM reference period and chains discount factors sequentially (ACT/360, simply-compounded). Cross-checked against Treasury.gov's daily par yield curve (same date, 2026-08-28, independent source, no API key needed): spread widens from ~13bp (1Mo) to ~46.5bp (10Yr) — consistent with the normal SOFR-vs-Treasury term premium, no anomalies. **A second decade-resolution bug was found and fixed** while calibrating Hull-White (§ simulation engine notes): the first bug-fix (recently-expired serial contracts, e.g. `SR3Q6`) had swung too far the other way and was silently dropping genuinely far-dated live contracts (e.g. `SR3H0` = March 2030, was wrongly resolving to March 2020 and getting filtered as "expired"). Fixed with a threshold-based decade check (`_MAX_PLAUSIBLE_EXPIRY_LAG_DAYS`); now correctly includes all 33 live contracts (up from 21), extending real futures-implied coverage to ~6.3yrs out (to ~2032-12) before flat extrapolation takes over — a meaningfully smaller extrapolated region than before. All 8 bond trades still price correctly off this curve. |
| Bug found + fixed | An earlier version of the year-decoding logic wrapped recently-expired serial contracts (e.g. `SR3Q6`, expiring Aug 2026) a full decade forward instead of dropping them, silently producing a spurious 3.5-year gap in the curve and a bad 10Y point (73bp vs. Treasury instead of the smooth ~56bp after the fix). Caught by this Treasury cross-check — a good example of why validating against an independent source matters. |
| Note | API key is never committed to the repo — set via environment variable only |

## 2. Equity spot prices + dividend yields (41 names)

| Field | Value |
|---|---|
| Source | yfinance (spot, historical prices); dividend yield via yfinance trailing yield or put-call parity if options data available |
| Identifier | ISIN (keys `MarketState.equity_spots`) — mapped from `trade_data/underlyings/equities.csv`; yfinance needs ticker, so ISIN→ticker mapping must be preserved (the `ticker` column already provides this) |
| Names | 41 basket rows / 37 unique ISINs across the 8 Equity TRS baskets (some names, e.g. AAPL, repeat across baskets) — see inventory in `docs/notes/pricer_review.md`; includes 6 JPY-quoted names (`6902.T`, `7751.T`, `4901.T`, `5108.T`, `4503.T`, `8035.T` across EQTRS_0005/0006) |
| Date range | Snapshot as of valuation date for pricing; 1-3yrs daily history for vol/correlation calibration (see §5) |
| Frequency | Daily |
| Status | **pulled** — live snapshot fetched via `src/risk_engine/market/equities.fetch_raw()` for all 37 ISINs, cached at `data/raw/equity_spots_2026-08-24.json`. Not yet **validated** (no cross-check against a second source; `div_yield` blanks defaulted to 0.0, needs review before use) |

## 3. USDJPY FX spot and forward curve

| Field | Value |
|---|---|
| Source | yfinance (`JPY=X`) for spot/history; forward points from a bank/Bloomberg FX swap points source — **needed for full forward curve, not just spot** |
| Identifier | `JPY=X` (yfinance), pair USDJPY (quoted JPY per USD, convention confirmed in pricer README §4/§6) |
| Tenors needed | SPOT (T+2), O/N, T/N, 1W, 1M, 2M, 3M, 6M, 9M, 1Y, 2Y |
| Date range | Snapshot as of valuation date; only needed for the JPY compo trades (EQTRS_0005, EQTRS_0006) |
| Frequency | Daily |
| Status | **spot pulled** (159.80 as of 2026-08-30, cached at `data/raw/usdjpy_spot_2026-08-30.json`) — sufficient to *price* the JPY compo trades. Forward points still **not started**, needed only once FX is simulated as a risk factor |
| Note | Only spot is needed to *price*; the full forward curve (swap points) is needed once FX is simulated as a risk factor |

## 4. Volatilities (simulation calibration — not used by the linear pricers)

| Field | Value |
|---|---|
| Source | **Historical realized vol** (the documented fallback), computed from the 3yr daily history already pulled for §5 — `src/risk_engine/market/vols.py`. Implied vols (options data, e.g. CBOE/OptionMetrics) would be more standard but no source is confirmed yet; realized vol unblocks pricing/simulation now and can be swapped later |
| Method | Equity/FX: annualized lognormal vol on daily log returns (`std(log(S_t/S_t-1)) * sqrt(252)`). Rate: annualized normal vol on daily rate **changes**, not log returns (rate levels can be near zero, so log returns aren't meaningful) |
| Factors | `RATE_USD`, one per equity ISIN (37 unique), `FX_USDJPY` — 39 factors total (37 not 41: some names repeat across baskets, see §2) |
| Date range | 3yr, matching §5's history (2023-08-31 to 2026-08-30) |
| Frequency | Daily inputs -> one annualized vol number per factor |
| Status | **pulled + computed**. Results sane: equity vols mostly 16%-58% (one outlier, SMTC/`US8168501018` at 76% — checked against its price history, a genuinely volatile name with several 20-30% single-day moves, not a data bug); `FX_USDJPY` at 9.3%; `RATE_USD` (normal vol) at ~63bp. Cached at `data/processed/volatilities.csv` (gitignored) |

## 5. Pairwise correlation matrix

| Field | Value |
|---|---|
| Source | Historical correlation proxy — daily log returns of the USD short rate, each of the 41 equity spots, and USDJPY |
| History | **1-3 years of daily returns** for all 39 factors |
| Date range | 2023-08-31 to 2026-08-30 (3yr) as the outer bound; can trim to 1yr if data quality/availability is an issue for some names |
| Frequency | Daily |
| Status | **built** — `src/risk_engine/market/correlations.py` computes the full 39x39 pairwise matrix (log returns for equity/FX, rate changes for RATE_USD, inner-joined on common dates -- 613 fully-aligned days -- so the matrix is PSD by construction, not just hoped to be). **PSD confirmed**: min eigenvalue 0.16 (safely positive). Sanity checks pass: RATE_USD correlates weakly with everything (-4% to +9%, expected for daily rate changes); FX_USDJPY correlates positively with the JPY-quoted equity names (~0.25 avg, economically sensible); equity-equity pairwise correlation averages ~0.15 (reasonable for a mixed-sector, mixed-market basket), max 0.82. Cached at `data/processed/correlation_matrix.csv` (gitignored). History itself: `scripts/pull_historical_data.py` fetches all 39 factors (SOFR/FRED 781 obs, USDJPY/yfinance 777 obs, 37 equities/yfinance 778 rows) — fixed two tz-alignment bugs (US/Tokyo market-hour timestamps for equities, then the same class of bug for FX) that were silently breaking the join |

## 6. Risk-free government/agency bond reference data (validation)

| Field | Value |
|---|---|
| Source | Trade data already supplies full bond terms (`trade_data/underlyings/bonds.csv`: 5 US Treasury bonds, Bond_A through Bond_E) — no external bond reference data needed to price, since bonds are risk-free and discount on the USD curve |
| Use | Cross-check the USD curve build against on-the-run Treasury yields as an independent sanity check (e.g. Treasury.gov par yield curve) |
| Status | **not started** (nice-to-have cross-check, not a blocker) |

## Credit / CDS (optional — only if extended to risky bonds)

Not needed this week; all 5 bonds are risk-free (issuer = "US TREASURY N/B",
blank in the pricer's credit-lookup sense). Deferred per pricer README §8.

---

## Summary

| # | Series | Status |
|---|---|---|
| 1 | USD OIS (SOFR) curve | pulled + bootstrapped + validated (found and fixed a real bug via cross-check) |
| 2 | Equity spots + dividends (37 unique names) | pulled (not yet validated) |
| 3 | USDJPY FX spot + forward curve | spot pulled (forward curve not started) |
| 4 | Volatilities (39 factors) | pulled + computed (historical realized, sane) |
| 5 | Correlation matrix (historical proxy) | built, PSD-confirmed, sanity-checked |
| 6 | Bond reference data (validation cross-check) | not started (optional) |

**USD curve unblocked** — Databento (paid, confirmed access) covers SOFR
futures for curve building; fetch/clean code is in place, bootstrapping is
the remaining step. **Still open:** FX forward points beyond spot (no free
or currently-confirmed source), and volatilities. Flagging for the Friday
check-in.
