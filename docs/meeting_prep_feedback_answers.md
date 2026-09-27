# Meeting prep: answers to the five feedback points

Every number below is from the finished runs and is in the report (section numbers in brackets). Say the plain-language line first, then the numbers if asked.

---

## 1. Stress testing: "make it a robust test, not a paragraph" [Report 7.10]

**One-sentence answer.** We now run 11 fixed scenarios on the same random numbers, and read the results for every counterparty, every trade and every date, so we can say exactly what moves, when, and for which products.

**What data was used?**
- Equity prices for all 37 names, USDJPY (Yahoo Finance) and US Treasury yields from 3 months to 30 years (FRED), 2014 to 2026.
- Everything else is the base calibration (volatilities, correlations, mean reversion), so the stress isolates the shock.

**What were the inputs (the 11 scenarios)?**
- 8 round-number shocks: equities -30%, equities +30%, yen strengthens 15%, yen weakens 15%, rates +200bp, rates -200bp, "flight to quality" (equities -25%, yields -100bp), "stagflation" (equities -25%, yields +150bp).
- 3 historical replays, chosen by rule, not by hand: the worst 10-day equity window (6 to 20 March 2020: median stock -23%, worst -68%), the biggest 10-day rise in the 10-year yield (30 May to 13 June 2022: +58bp), the biggest 10-day yen surge (22 July to 5 Aug 2024: USDJPY -7.5%). Each replay applies the actual return of every name, the actual yield change at every tenor and the actual USDJPY move.
- Mechanics: the shock hits today's market; then we re-run the full exposure simulation from the shocked state. 1,000 scenarios, same seed as the base. Equity/FX shocks rescale the paths exactly; rate shocks rebuild the curve and re-simulate.

**How sensitive were outputs across the path?**
- The effect follows the life of the trades that carry the shocked factor. Example: rates -200bp raises the portfolio close-out PFE99 by up to 50% around day 63, and it is back to about 1.0 once the big bond forward (BF_0003) settles on 6 Dec 2026. Equity -30% scales the equity part by about 0.84 for as long as the baskets are alive.

**Was it sensitive for all products? No, and that is the finding.**
- Equity swaps: move about +/-30% under +/-30% equity shocks, essentially zero under rate shocks.
- Bond forwards / bond TRS: move -31% to +50% under rate shocks (BF_0003 most), zero under equity shocks.
- FX: only the two JPY compo swaps (EQTRS_0005, 0006) react (+17% / -13% for a 15% yen move).

**The headline insight (say this clearly).**
- On the brief's close-out definition the biggest portfolio move is only about -24% (stagflation) or +23% (rates -200bp). On the uncollateralized level exposure it is +86% (stagflation) and -68% (rates -200bp).
- Why: close-out exposure is the 10-day move from a margined start, so a shock to today's levels only changes the size of the positions. The level exposure is the level itself, so it moves with the shock. This is the reason margin matters so much.
- Example: equities -30% cuts the close-out MPE by 16% (positions are smaller) but raises the level MPE by 60% (we are short equities, so we gain).

**Honest limits.** Instant shocks to the starting state, not a projection; base-model vols; history starts 2014 (no 2008); 1,000 scenarios (about 3% noise).

---

## 2. Greeks: method, alternatives, cost, faster alternative [Report 9.1, 9.4]

**Plain description of what we did.** For each risk factor we nudge it (stock +/-1%, curve +/-1bp, vol +1%), re-generate the paths with the same random numbers, reprice the trades, recompute EE / median PFE / PFE99, and take the difference. Same random numbers is the key: the difference is then a sensitivity, not noise. With independent random numbers the estimate has a standard deviation of $245k; with common random numbers it is $1k (282 times smaller).

**The two tricks that make it efficient.**
1. A stock bump rescales every simulated path exactly (geometric Brownian motion), so no re-simulation is needed.
2. Only the trades that hold the bumped stock are repriced.

**Cost (measured on an idle machine, 300 scenarios, 8 cores).**
- Base run 105 s.
- 78 equity/FX bumps: 88 s in total (about 1 s each). Naive re-simulate-and-reprice would be about 8,200 s: 93 times more.
- 13 rate / vol bumps (parallel up/down, 8 buckets, 3 vega) need a re-simulation: about 109 s each, 1,420 s in total. No shortcut here.
- Whole Greeks set: about 1,600 s versus about 9,700 s naive (6 times faster). At 1,000 scenarios about 1.5 hours (the production run took 2.1 hours on a shared machine).

**Alternatives considered.**

| Method | Verdict |
|---|---|
| Bump, independent random numbers | Noise swamps the answer (282x larger): rejected |
| Bump, common random numbers | **Used**: works on black-box pricers, works for quantiles |
| Pathwise (differentiate the payoff on each path) | **Implemented for equity and FX**, fast check |
| Likelihood ratio | High variance over many time steps: not used |
| Adjoint / algorithmic differentiation | Fastest in principle (all Greeks for about 3-5 valuations), but needs the pricers rewritten in a differentiable form; ours are black boxes |
| Delta-gamma / regression proxy | Adds proxy error, worst for quantiles: future |

**Is there a faster alternative? Yes, for equity and FX.** Pathwise: an equity swap is linear in the stock, so its delta is just position times S(t)/S0 on each path. It needs no repricing: 0.2 to 0.4 seconds for every name, counterparty and date, against about 260 seconds for the 76 bump runs. Validated on the same paths: EE deltas agree to a median 0.02% (worst 0.4%) of the largest name delta. Median-PFE and PFE99 deltas are noisier, so bump-and-reprice stays the reported number. Rate and vol Greeks (the expensive part) would need adjoint differentiation.

**Follow-up we tried: does Latin Hypercube sampling reduce Greeks noise too?** We already use it (with common random numbers) for the reported Greeks; the open question was whether the sampling scheme itself, separate from sharing draws, helps. We repeated the equity, FX and rate deltas at N=256 with 4-6 independent seeds per scheme (pseudo-random, antithetic, moment-matched, Sobol, Latin Hypercube) and compared the standard deviation of each delta across seeds.
- Result: mixed. Latin Hypercube cuts the noise of EE deltas (roughly 15-85% lower standard deviation), but is no better, and sometimes 2-4x worse, for the tail-quantile deltas (PFE99, median PFE). Sobol shows the same pattern.
- Why: Latin Hypercube stratifies each of about 660 dimensions (39 factors x 17 steps) on its own marginal, which helps an average (EE) but not a tail quantile driven by a handful of extreme scenarios among many draws.
- Bottom line: keep Latin Hypercube as the default (it is never much worse for what we report, EE and PFE99), but common random numbers, not the sampling scheme, is what actually controls Greeks noise. This is now Report Section 9.6.

---

## 3. PCA factors: what are they, how much speed? [Report 4.4]

**What they are.** PCA finds the few directions in which the 39 stocks/FX/rate move together. Each factor is a "mode" of the correlation matrix; a name's loading is its correlation with it.
- Factor 1 (20% of the variance): the market. Every name loads positively (banks and chips highest).
- Factor 2 (8.9%): Japan versus US. Tokyo listings load +0.4, US names about 0.
- Factor 3 (8.5%): defensives (Coca-Cola, P&G, Berkshire) against high-growth tech and power (KLA, Vistra, Semtech).
- Factor 4 (5.3%): energy (Marathon, Exxon) together with the USD rate, against the Indian ADRs.
- Factor 5 (4.0%): growth/power names (Constellation, Netflix) against banks and semis.
- 5 factors explain 47% of the variance, 10 explain 62%.

**How much speed did it add? None: it is slightly slower.** The correlated-shock step takes 1.91 s with the full matrix and 2.08 s (5 factors) / 2.29 s (10 factors) for 5,000 scenarios, because the engine then draws k + 40 random numbers instead of 40. And that step is only about 0.1% of the run (repricing takes about 2,134 s). So the honest answer to "how much speed" is: nothing that matters.

**Accuracy given up.** Netting-set volatility under 5 factors versus the full matrix: A +0.0%, B +1.7%, C +3.9%. Sampling error is not consistently lower (4.5-4.9% full versus 2.6-6.2% for PCA).

**Decision.** Keep the full matrix as default; the factor model stays as an explainable robustness option. It would only help if the systematic factors were drawn quasi-randomly and the noise pseudo-randomly (listed as future work).

**Bonus: an Excel benchmark, for anyone who wants to sanity-check the numbers by hand.** docs/Capitolis_CCR_Parametric_Benchmarks.xlsx recomputes the calibrated vols and the simulation's own vol using nothing but plain Excel formulas on public data (yfinance closes, FRED Treasury yields): =STDEV(LN(Pt/Pt-1))*SQRT(252) for equities/FX, =STDEV(diff)*SQRT(252) for rates, and the closed-form Hull-White formula sigma*(1-EXP(-a*T))/(a*T). Every one matches the engine's number to about 0.1-2%, and the simulated one-year vol matches the analytic GBM/Hull-White formula to about 1-2%, which is inside Monte Carlo noise. Report Section 5.6.

---

## 4. Final results: equity vs rate exposure, and why the portfolio MPE is so high [Report 7.2]

**Is CPTY_A equity and CPTY_C rate? Yes, with one nuance.** Sensitivities today:

| | Equity delta (per +1%) | DV01 (per +1bp) |
|---|---|---|
| CPTY_A | -$2.25M | $31k |
| CPTY_B | -$0.96M | -$4k (plus USDJPY +$0.42M per 1%) |
| CPTY_C | -$1.24M | **$594k** |

A is the most equity-driven; C is the rate netting set (one $500M short forward on a 2049 Treasury). The nuance: C also holds equity swaps, with an equity delta bigger than B's. So C is not purely a rate set.

**Should bonds move inversely to equities?** It depends on the regime. Flight to quality: equities fall, bonds rally, yields fall. 2022-style inflation shock: both fall. In our three years of data the correlation between 10-year yield changes and the stocks averages 0.00 (range -0.29 to +0.16): essentially none. We are short equities (gain when they fall) and short the long bond (gain when yields rise). So in a flight to quality the two gains oppose each other; when both fall together they coincide.

**Why is the portfolio MPE so high?**
1. Portfolio exposure is the sum of the counterparties' exposures: nothing nets across counterparties (sum of max(V_c, 0), not max of the sum).
2. The three books all peak in the first weeks (20 Sept, 4 Sept, 28 Sept), so there is no timing diversification.
3. The exposures are positively dependent (rank correlation A-B 0.34, A-C 0.33, B-C 0.12) because every set holds pay-equity swaps.
4. Numbers: $51.0M portfolio against $65.1M sum, i.e. 78% (80% at the peak date). At the peak date A $25.9M, B $9.1M, C $28.5M. **Note:** the portfolio figure is close to A + C ($54.4M), not A + B ($35.0M). B is small.

**What the dependence assumption is worth (2,000 scenarios).** Base $51.5M. If yields fall with equities: $43.6M (-15%, exposures offset). If both fall together: $60.8M (+18%). So the answer to "should bonds be inverse to equities" changes the portfolio number by roughly +/-15%, and the data cannot settle it. Say this openly.

---

## 5. CVA walk-through and set-up for next time [Report 8.7]

**What CVA is.** The price of the risk that the counterparty defaults when they owe us. Formula: LGD x sum over time of (average discounted expected exposure) x (probability of default in that interval).

**Steps, with CPTY_C as the example.**
1. Exposure profile from the simulation: expected exposure at each date, discounted along each path.
2. Default probability: from a credit spread (no CDS available, so ICE BofA BBB index spreads: 59bp at 1 year, 91bp at 5 years), via the credit triangle. LGD 60%. Cumulative default probability over the life of the book: 1.4%.
3. Multiply and sum. CPTY_C close-out: $8k. CPTY_A $2.4k, B $1.4k. Total **$12k**.

**Why so small?** On the brief's definition exposure is only the 10-day move (about $5M expected at peak for C). If no margin were ever called the exposure is the whole mark-to-market ($125M for C), and CVA is **$247k** (C $237k). The two numbers bracket the truth; which one applies depends on whether any trade is margined.

**Other results.**
- Rating sensitivity (close-out total): AA $7k, A $8k, BBB $12k, BB $18k.
- DVA $11k, FCA $12k, FBA $11k, FVA $0.5k (close-out). On the level exposure DVA $8k, FVA $240k. DVA and FVA rest on an assumed own credit (BBB) and funding spread. Best number without double counting: CVA - DVA + FCA.
- SA-CVA capital: $0.10M (close-out) versus $2.23M (uncollateralized, RWA $27.8M). Counterparty credit-spread risk dominates both.
- SA-CCR exposure at default: $260M, dominated by the replacement cost of BF_0003.

**Questions to set up for next time.**
1. Which exposure definition should price CVA: margined close-out, or level?
2. Real ratings or CDS for A, B, C (the BBB proxy drives everything).
3. Capitolis' own credit and funding spread; is DVA recognised at all (Basel ignores it)?
4. Wrong-way risk: independence of exposure and default is assumed. Wanted?
5. SA-CVA or the basic approach as the capital reference; hedges included?
6. Margin terms: threshold, minimum transfer amount, initial margin.
