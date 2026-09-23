"""Report patch, part D: Sections 10 to 15 and the appendices."""
import sys
sys.path.insert(0, "scripts")
from _patchlib import Patcher

p = Patcher("scripts/build_report.py")

# ---------------------------------------------------------------- 10 register rows
p.sub('["USD rates", "Hull-White 1F", "CIR, BK, LMM, constant", "Exact curve fit, analytic bonds, negative-rate capable, few parameters"],',
      '["Exposure", "The brief: max(V(t+10bd) - V(t-1bd), 0), signed prior-day variation margin, no initial margin; level exposure as a secondary view", "Level max(V,0) only; same-day full-VM MPOR shift", "It is what Capitolis specified (kickoff slides 8-9); the level view remains for the uncollateralized case"],\n'
      '             ["USD rates", "Hull-White 1F; sigma fitted to realised 2y-30y Treasury yield vol; Bloomberg long end spliced beyond the futures", "CIR, BK, LMM, G2++ (implemented and compared), overnight-SOFR sigma, flat extrapolation", "Exact curve fit, analytic bonds, negative-rate capable, few parameters; matches the yield moves the book depends on (Sections 3.2, 11.7)"],\n'
      '             ["Two-factor rates", "G2++ implemented, calibrated to the realised yield covariance; compared, not the default", "Two-factor default, swaption-calibrated 2F", "Adds a slope factor at 16% fit error; effect on exposure reported in Section 7.9"],')
p.sub('["Equities/FX", "Correlated GBM", "Heston, SABR, jumps", "No option surfaces; matches lognormal vol convention"],',
      '["Equities/FX", "Correlated GBM under the USD measure; quanto correction and rate-driven drifts for JPY names and USDJPY", "Heston, SABR, jumps", "No option surfaces; matches lognormal vol convention; drifts derived from the martingale condition and tested"],')
p.sub('["Correlation", "One static matrix, Cholesky", "Time-varying (DCC), stressed, factor", "Data supports one matrix; factor model offered as alternative"],',
      '["Correlation", "One static 40x40 matrix (USD rate on 10-year-yield shocks), Cholesky", "Time-varying (DCC), stressed, factor", "Data supports one matrix; factor model offered as alternative; correlation stress in Section 7.9"],')
p.sub('["JPY rates", "Real JPY Hull-White factor (built), not yet wired", "Constant differential only", "Negative-rate capable; real TONA sigma; correlation calibrated ~0"],',
      '["JPY rates", "Real JPY Hull-White factor, simulated and correlated with the USD rate, USDJPY and the equities", "Constant differential only", "Negative-rate capable; sigma from the real JPY OIS history; correlations calibrated"],')
p.sub('["Collateral", "Uncollateralized default; MPOR-shift option", "Assume full VM", "No CSA data; hypothetical shown separately"],',
      '["Collateral", "Close-out exposure with daily VM at the prior-day value; uncollateralized level exposure alongside", "Assume full VM with same-day margin", "No CSA data: the two definitions bracket the answer"],\n'
      '             ["xVA and capital", "CVA on both exposure definitions; DVA and FVA on assumed own credit and funding spreads; SA-CVA; SA-CCR EAD", "CVA only; BA-CVA", "Extra-credit scope; assumptions stated and sensitivities shown"],\n'
      '             ["Greeks", "Bump-and-reprice with common random numbers; subset repricing for equity and FX; pathwise for equity and FX as a fast check", "Independent draws, likelihood ratio, adjoint (needs pricer port)", "Works on the black-box pricers; cost measured (Section 9.4)"],\n'
      '             ["Model validation", "Martingale tests, VaR benchmark, Kupiec backtest, attribution, model-risk study, stress test", "Narrative stress test", "Quantified, out-of-sample where possible (Sections 7.3, 7.9, 7.10, 11)"],')

# ---------------------------------------------------------------- 11.2 martingale text, 11.4 stress pointer, 11.5 tests, new 11.7
p.replace('add(P("Under the risk-neutral measure discounted asset prices must have no drift.', '''
_mg = RN._j("martingale_results.json")
add(P("Under the risk-neutral measure discounted asset prices must have no drift. With %s paths: the bank-account check E[exp(-integral r)] = P(0,T) holds to a maximum relative difference of %.2f bp across nodes (a small, understood trapezoid-integration effect of the time grid); the discounted 'gains process' of %d names (four USD-listed and two JPY-listed, the latter valued in USD as S / X) has all |z| below %.1f; and the JPY bank account valued in USD, B_JPY / (X B_USD), is a martingale with z = %+.2f, while ln USDJPY drifts by %+.4f over the horizon (down, as it must when USD rates exceed JPY rates). "
      "This validates the drift terms in the engine itself, including the quanto correction and the JPY-rate drift, independent of any trade pricing. The earlier version of this test covered only the six highest-volatility names and so did not exercise the JPY drift; the USDJPY drift sign error found later (Section 12) was outside its reach." % (format(_mg["n_scenarios"], ","), _mg["bank_account_max_rel_bp"], len(_mg["equity_z"]), max(abs(z_) for z_ in _mg["equity_z"].values()) + 0.05, _mg["jpy_account_z"], _mg["usdjpy_mean_log_change"])))
''')
p.replace('add(P("Directional test with common random numbers (800 scenarios', '''
add(P("The earlier directional test (a few bumps of volatility and the curve, one paragraph of results) has been replaced by the structured programme of Sections 7.9 (one-at-a-time model perturbations) and 7.10 (stress scenarios with stated data and inputs, by netting set, by trade and along the time path), which answers what the inputs were, how sensitive the outputs are across the path, and whether all products react."))
''')
p.replace('add(P("82 automated tests pass.', '''
import subprocess as _sp
_col = _sp.run([sys.executable, "-m", "pytest", "tests", "--collect-only", "-q"], capture_output=True, text=True, cwd=ROOT).stdout
_ntests = int([l_ for l_ in _col.splitlines() if "tests collected" in l_ or "test collected" in l_][-1].split()[0])
add(P("%d automated tests pass. They cover: Hull-White reproducing the curve at t=0 to 1e-9; the GBM martingale property; the 1/sqrt(N) error law; antithetic variance reduction; Cholesky recovering a target "
      "correlation; MPOR look-ahead spacing and formula; pillar dates and forced event dates; negative-rate behaviour of Hull-White; the PCA factor model (exact at full rank, monotone error, variance "
      "preservation); the BOJ TONA and MOF JGB loaders and the empirical JPY findings; the tail-convergence result; median PFE, CVA and the SA-CVA aggregation, the credit-spread proxy curves, and the Greeks machinery (bump helpers, t=0 Greeks against analytic values, exposure measures); "
      "and, added in this version, the close-out exposure convention (signed variation margin, netting before the positive part, settlement inside the window, the t-1bd node), the Bloomberg long-end splice, the JPY factor (curve fit, shock correlations, and the USDJPY and JPY-name martingale properties including a regression test for the drift sign), "
      "the long-end volatility fit, the G2++ model (curve fit, martingale property, calibration recovery, engine integration), DVA and FVA against closed forms, SA-CCR against hand calculations, the Kupiec and Christoffersen tests and both backtests, the stress-scenario helpers, the pathwise Greeks against central bumps, and the risky-bond sample." % _ntests))
''')
p.insert_after('add(P("Common random numbers make bump-and-reprice statistically indistinguishable', '''
add(P("On the real book the pathwise estimator was also validated against the bump-and-reprice deltas of the close-out exposure (Section 9.4)."))
add(P("11.7 Backtesting: Kupiec proportion-of-failures tests", H2))
_bt_out, _ = RN.backtest_section(doc)
add(_bt_out)
_eq99 = {c: Bt["equity"][c]["confidences"]["0.99"] for c in ("CPTY_A", "CPTY_B", "CPTY_C")}
_eq95 = {c: Bt["equity"][c]["confidences"]["0.95"] for c in ("CPTY_A", "CPTY_B", "CPTY_C")}
_r = Bt["rates"]
_avg = lambda name, key: np.mean([_r[t][name][key]["phases_mean_rate"] for t in ("5", "10", "20")]) * 100
add(P("<b>What the backtest shows.</b> At the 99%% level the equity and FX quantiles are close to calibrated: the exceptions are %s against %s expected, and the Kupiec test does not reject for %s of the three netting sets at the 5%% level on the base offset (CPTY_B, with %d exceptions against %.1f, is the borderline case, consistent with the fat tails that geometric Brownian motion understates). At the 95%% level the model is conservative for CPTY_A and CPTY_C (mean exception rates %.1f%% and %.1f%% against 5%%): a Kupiec test is two-sided, so being too conservative also fails it. With about %d non-overlapping windows per series the test has limited power, which is why the counts, not only the p-values, are shown. "
      "On the rates leg both calibrations of sigma pass on average over 2020-2026, but they are not equivalent: the long-end fit gives mean exception rates of %.1f%% at the 95%% up-tail and %.1f%% at the 99%% up-tail (nominal 5%% and 1%%), while the overnight-SOFR calibration gives %.1f%% and %.1f%%, i.e. it was too wide on average, reflecting a calibration window that included the 2022-23 hiking cycle, and would be too narrow in a period such as the present, when SOFR is stable and long yields are not (its current value is %.0fbp against %.0fbp for the fit). The long-end fit is therefore the more stable calibration." % ("/".join(str(r_["x"]) for r_ in _eq99.values()), "/".join("%.1f" % r_["expected"] for r_ in _eq99.values()), sum(1 for r_ in _eq99.values() if r_["pass_5pct"]), _eq99["CPTY_B"]["x"], _eq99["CPTY_B"]["expected"], _eq95["CPTY_A"]["phases_mean_rate"] * 100, _eq95["CPTY_C"]["phases_mean_rate"] * 100, _eq99["CPTY_A"]["n"], _avg("long_end_fit", "0.95_up"), _avg("long_end_fit", "0.99_up"), _avg("sofr_overnight", "0.95_up"), _avg("sofr_overnight", "0.99_up"), Bt["rates_config"]["sigma_now_sofr"] * 1e4, Bt["rates_config"]["sigma_now_fit"] * 1e4)))
''')

# ---------------------------------------------------------------- 12 defects
p.sub('["8", "JPY mean-reversion fit gave a negative a", "Diagnosed as a real structural property (three sources); lower bound a = 0.001 used"]],',
      '["8", "JPY mean-reversion fit gave a negative a", "Diagnosed as a real structural property (three sources); lower bound a = 0.001 used"],\n'
      '             ["9", "Headline exposure was the uncollateralized level max(V, 0), not the brief\'s move from the prior-day NPV over a 10-day close-out", "Found by reviewing the work against the kickoff deck and an independent implementation of the same brief; exposure module, t-1bd grid node and tests added (Section 7.1)"],\n'
      '             ["10", "USD curve extrapolated flat beyond the last futures contract (about 6.5 years), understating the long-dated Treasury forward BF_0003 by about 16%", "Found by repricing BF_0003 on Bloomberg\'s own zero curve; long end spliced (Section 3.1); NPV reconciled to within 0.4%"],\n'
      '             ["11", "USDJPY drift had the wrong sign (the drift of USD per JPY used for JPY per USD), so JPY-listed names drifted about 2 x 2.6% a year too low in USD value", "Found while deriving the drifts for the JPY factor from the martingale condition; the old martingale test only covered six high-volatility names. Drifts corrected, quanto term added, martingale tests for JPY names and the JPY bank account added (Section 4.2)"],\n'
      '             ["12", "USD Hull-White sigma taken from the overnight SOFR fixing understated the moves of the 2y-30y yields (10-day 20y-yield move: about 15bp realised against 11bp modelled)", "Found by comparing modelled and realised 10-day yield moves and confirmed by the rates backtest; sigma fitted to realised long-end volatility (Section 3.2)"],\n'
      '             ["13", "Equity histories on different exchange holidays left gaps that emptied the first backtest windows", "Last close carried over non-trading days (at most five) before returns are taken"]],')

# ---------------------------------------------------------------- 13 assumptions
p.replace('add(B(["<b>USD curve beyond seven years.</b>', '''
add(B(["<b>No CSA data.</b> The exposure headline assumes daily variation margin at the prior-day value and no initial margin, as the brief specifies; the uncollateralized level view brackets the other extreme. Threshold, minimum transfer amount and initial margin are unknown (Section 7.7 shows the size of the effect of margin).",
       "<b>Volatility is a 3-year realised proxy</b>, not implied. Regime shifts and skew are not captured; volatility is stressed in Sections 7.9 and 7.10.",
       "<b>One static correlation matrix</b> from 616 days; correlations tend to rise in stress and are stressed only in the model-risk study (Section 7.9).",
       "<b>GBM underestimates fat tails</b>, most relevant for PFE99 on high-vol names; the backtest shows it (CPTY_B at 99%).",
       "<b>Rates:</b> the base model has a single USD factor (no curve twist independent of the level); a two-factor G2++ is implemented and its effect measured, but it fits the realised covariance with a 16% error and is not the default. The JPY rate has mean reversion at its lower bound because every calibration gives a negative value.",
       "<b>Risk-neutral drift</b>: not a real-world forecast; regulatory PFE may need physical drift. The backtest compares model quantiles with realised moves and is the check on this.",
       "<b>Model risk vs sampling risk:</b> above a few thousand scenarios the uncertainty is in the models, not the random numbers (Section 7.9).",
       "<b>Own credit and funding</b> for DVA and FVA are assumptions (BBB proxy, funding spread equal to the own spread). <b>SA-CCR</b> is unmargined, single-name equity and USD interest-rate only, with no collateral. <b>Risky bonds</b> use a bond-index proxy for the issuer curve with deterministic spreads.",
       "<b>Stress tests</b> are instantaneous shocks to the starting state with the base model's volatilities, correlations and mean reversion; they are not a projection, and the historical replays cover 2014-2026 only (no 2008).",
       "<b>Backtests</b> have limited power at 99% (a few exceptions in about 240 windows) and test static positions, not the evolving book; the rates leg tests yield moves, not the book's rate exposure directly.",
       "<b>No wrong-way risk or credit dynamics of the counterparty itself</b>; this is exposure, not a loss estimate (that needs PD and LGD).",
       "<b>Bloomberg data is a single 2026-08-31 snapshot</b> (three days after the 2026-08-28 market data), re-based to our reference date; acceptable for shape and level, disclosed."]))
''')

# ---------------------------------------------------------------- 14 conclusions
p.replace('add(B([f"The engine is validated (t=0 self-check, martingale, VaR benchmark, stress test, 82 tests)', '''
_sc = Sx["scenarios"]
_cw = max(_sc, key=lambda n_: abs(_sc[n_]["closeout"]["__portfolio__"]["MPE"] / Sx["base"]["closeout"]["__portfolio__"]["MPE"] - 1))
_lw = max(_sc, key=lambda n_: abs(_sc[n_]["level"]["__portfolio__"]["MPE"] / Sx["base"]["level"]["__portfolio__"]["MPE"] - 1))
_old = RN._j("spec_run", "spec_exposure_before_fixes.json")
_gt = RN._j("greeks_results.json")
_pkn = RG.peak_node(_gt)
add(B([f"The engine is validated (t=0 self-check, martingale tests including the JPY components, delta-normal VaR benchmark, Kupiec backtest, {_ntests} automated tests) and reproducible with a single command per stage.",
       f"On the exposure definition in the brief (10-day close-out from the prior-day value), the portfolio MPE99 is {m(sp_['PFE'])} at {sp_['PFE_date']}, with peak EE of {m(sp_['EE'])} and peak median PFE of {m(sp_['MED'])} (Section 7.1). The earlier version of this work reported {m(RN._peaks(_old, '__portfolio__')['PFE'])} before the model corrections of Section 7.3.",
       f"The portfolio MPE99 is {Ad['mpe_portfolio']/sum(Ad['mpe'].values())*100:.0f}% of the sum of the counterparty MPE99s: netting does not cross counterparties and the three books peak within days of each other, so there is little diversification (Section 7.2).",
       f"The uncollateralized level exposure, kept as a secondary view, has peak portfolio PFE99 of {m(mpe99)} at {D['rep_dates'][j_mpe]}, versus EE of {m(tot['EE'].max())} and median PFE of {m(tot['MED'].max())}; the spread between these three is the point of reporting all of them.",
       "Risk is short-dated (about four months) and concentrated: CPTY_C, through the single 500M bond forward, dominates the level exposure and the current exposure; the equity netting sets CPTY_A and CPTY_B, which move together, set the close-out tail.",
       f"CVA is about ${Xv['conventions']['closeout']['total']['CVA']/1e3:,.0f}k on the close-out exposure and ${Xv['conventions']['level']['total']['CVA']/1e3:,.0f}k on the uncollateralized level exposure at a BBB proxy; DVA is ${Xv['conventions']['closeout']['total']['DVA']/1e3:,.0f}k and FVA ${Xv['conventions']['closeout']['total']['FVA']/1e3:,.0f}k on assumed own credit and funding spreads; the SA-CVA requirement is ${Rc0['K_sa_cva']/1e6:.2f}M (RWA ${Rc0['RWA']/1e6:.1f}M) and the SA-CCR exposure at default {m(Sa['total']['EAD'])}.",
       f"Greeks are complete for the book and for the exposure measures (Section 9). Their cost is dominated by the rate and volatility re-simulations; equity and FX Greeks cost a small fraction of naive bumping through subset repricing, and pathwise estimators give them in seconds. PFE99 at its peak date falls by about ${abs(_gt['equity_all']['delta']['__portfolio__']['PFE'][_pkn])/1e3:,.0f}k per +1% on all equities and moves by about ${abs(_gt['rate_parallel']['delta']['__portfolio__']['PFE'][_pkn])/1e3:,.0f}k per +1bp on USD rates.",
       f"Stress: the largest portfolio move of the close-out MPE99 is {(_sc[_cw]['closeout']['__portfolio__']['MPE']/Sx['base']['closeout']['__portfolio__']['MPE']-1)*100:+.0f}% ({RN2.SHORT.get(_cw, _cw)}) against {(_sc[_lw]['level']['__portfolio__']['MPE']/Sx['base']['level']['__portfolio__']['MPE']-1)*100:+.0f}% ({RN2.SHORT.get(_lw, _lw)}) for the level exposure: the margined measure is much less sensitive to level shocks than the uncollateralized one, and sensitivity is product specific (Section 7.10).",
       "Backtest: the 99% quantiles of the equity and FX leg are close to calibrated (CPTY_B slightly light-tailed), and the long-end yield-vol calibration is more stable than the overnight-SOFR one (Section 11.7).",
       "We recommend confirming with Capitolis whether any trade is margined, and on what terms; that fact matters more than any further modelling refinement.",
       "Use Latin Hypercube sampling with N = 5,000 for reporting, N = 1,000 for iteration and N = 10,000 for limit sign-off (Section 5.5).",
       "What remains is data and scope, not engineering: real counterparty ratings or CDS, CSA terms, wrong-way risk, and the items in Section 15."]))
''')

# ---------------------------------------------------------------- 15 remaining work
i0 = p.find('add(P("15. Improvement plan for the next week", H1))')
i1 = p.find('add(P("Appendix A. Glossary", H1))')
del p.lines[i0:i1]
p.insert_before('add(P("Appendix A. Glossary", H1))', '''
add(P("15. Remaining work and open questions", H1))
add(P("Everything in the plan that could be completed with the data and information available has been done and is reported above. What remains depends on information Capitolis holds, or is a longer-term refinement. It is listed here with what is needed, so the next session can decide which to take forward."))
add(tbl([["Item", "Why it is open", "What is needed"],
         ["Real counterparty ratings or CDS for CPTY_A, CPTY_B, CPTY_C", "The counterparties are anonymised and no CDS quotes could be sourced; the BBB proxy drives every credit number (Section 8.3 shows the range)", "Names or ratings, or CDS quotes"],
         ["Credit support annexes (threshold, minimum transfer amount, initial margin)", "Not in the data; the two exposure definitions of Section 7 bracket the answer", "Terms per netting set"],
         ["Wrong-way risk in CVA", "Independence of exposure and default is assumed", "A decision on the dependence model and on which counterparties it applies to"],
         ["Risky bonds and CDS beyond the proxy", "The sample of Section 8.9 uses a bond-index issuer curve with deterministic spreads; no CDS pricer exists in the library and no CDS data was obtainable", "CDS quotes; a CDS pricer; stochastic issuer spreads"],
         ["All-factor Greeks by adjoint differentiation", "The cheapest route for rate and volatility Greeks, but the supplied pricers are a black box (Section 9.4)", "A differentiable port of the pricers"],
         ["Two-factor model as the default", "G2++ is implemented and compared (Sections 4.6, 7.9); its calibration is to realised yield covariance with a 16% fit error", "Calibration to the swaption cube and a decision on adoption"],
         ["Hybrid sampling for the PCA factor model", "Section 4.4 shows the factor model adds no speed and no accuracy as implemented", "Draw the systematic factors quasi-randomly and the idiosyncratic noise pseudo-randomly, then re-measure"],
         ["Stochastic volatility and skew", "Needs single-name option surfaces, which the data does not include", "Option data, or an index-basis assumption"],
         ["Production hardening", "Vectorised pricers if scenario counts must exceed about 10,000; scheduling, monitoring and independent validation by Capitolis Risk", "Scope and infrastructure decisions"]],
        widths=[2.4, 3.6, 1.8], font=7.2))
add(P("The CVA questions to settle at the next session are listed at the end of Section 8.7."))
add(PageBreak())
''')

# ---------------------------------------------------------------- appendices
p.sub('["Pillar dates", "Standard curve tenor points: O/N, T/N, 1W, 2W, 1M ... 10Y"],',
      '["Pillar dates", "Standard curve tenor points: O/N, T/N, 1W, 2W, 1M ... 10Y"],\n'
      '             ["Close-out exposure", "max(V(t + 10bd) - V(t - 1bd), 0): the move of the netted value over a 10-business-day close-out from the prior-day value, which is the variation margin; the brief\'s definition"],\n'
      '             ["DVA, FVA", "Debit valuation adjustment (own default, on the negative exposure); funding valuation adjustment (cost of funding the exposure less the benefit)"],\n'
      '             ["SA-CCR, EAD", "Basel standardised approach for counterparty credit risk; exposure at default = 1.4 x (replacement cost + multiplier x add-on)"],\n'
      '             ["G2++", "Two-factor Gaussian short-rate model (equivalent to a two-factor LGM) with a level and a slope factor"],\n'
      '             ["Kupiec test", "Likelihood-ratio test of whether the observed frequency of exceptions matches the nominal probability"],\n'
      '             ["Pathwise delta", "Sensitivity obtained by differentiating the payoff along each simulated path instead of bumping and repricing"],\n'
      '             ["Stress scenario", "An instantaneous shock to today\'s market state, followed by the full exposure simulation from that state"],')
p.sub('["Equity sector, country, market cap", "yfinance", "Public API", "SA-CVA equity buckets", "Live"]],',
      '["Equity sector, country, market cap", "yfinance", "Public API", "SA-CVA equity buckets", "Live"],\n'
      '             ["Treasury constant-maturity yields 3M-30Y", "FRED (DGS3MO ... DGS30)", "Public CSV", "USD rate sigma, correlations, G2++, backtest, stress replays", "Public"],\n'
      '             ["Long price history 2014-2026 (37 names) and USDJPY", "yfinance", "Public API, cached in data/raw", "Backtest and historical stress windows", "Public"],\n'
      '             ["USD SOFR zero curve, long end", "Bloomberg one-time export, 2026-08-31", "Provided by the project team", "Spliced onto the futures curve beyond the last contract", "Licensed: derived numbers only"]],')
p.sub('["USD rates", "One-factor Hull-White, shifted Ornstein-Uhlenbeck, exact transition, analytic bond price", "sigma 0.63% (realised SOFR); a 0.0167 (swaption cube)", "models/rates.py"],',
      '["USD rates", "One-factor Hull-White, shifted Ornstein-Uhlenbeck, exact transition, analytic bond price", "sigma fitted to realised 2y-30y Treasury yield vol; a 0.0167 (swaption cube)", "models/rates.py, market/treasury.py"],\n'
      '             ["Two-factor rates", "G2++, exact joint transition, analytic bond price; calibrated to the realised covariance of 3M-30Y yield changes", "sigma, a, eta, b, rho; 16% relative fit error", "models/g2pp.py"],')
p.sub('["USD curve", "Bootstrap of SOFR futures: implied forward rate to chained discount factors, ACT/360", "33 live contracts, about 6.3y coverage, flat extrapolation beyond", "market/sofr.py"],',
      '["USD curve", "Bootstrap of SOFR futures: implied forward rate to chained discount factors, ACT/360; Bloomberg forward structure spliced beyond the last contract", "33 live contracts, about 6.5y coverage, continuous splice", "market/sofr.py"],')
p.sub('["Exposure measures", "Netting by counterparty, max(V,0); EE, median PFE, PFE99, MPE", "PFE at the 99th percentile", "exposure/aggregate.py"],',
      '["Exposure measures", "Close-out exposure max(V(t+10bd) - V(t-1bd), 0), netted by counterparty and per trade; level exposure max(V,0) alongside; EE, median PFE, PFE99, MPE", "PFE at the 99th percentile; one-year horizon", "exposure/spec_exposure.py, exposure/aggregate.py"],')
p.sub('["Validation", "t=0 self-check, martingale test, delta-normal VaR, stress test, unit tests", "82 automated tests", "scripts/, tests/"]],',
      '["xVA and capital", "DVA and FVA from discounted EPE and ENE; SA-CCR EAD", "Own credit BBB proxy; funding spread = own spread", "exposure/xva.py, exposure/sa_ccr.py"],\n'
      '             ["Stress test", "Instantaneous shocks (8 hypothetical, 3 historical replays) followed by the full exposure simulation", "Same random numbers as the base case", "stress/scenarios.py, scripts/run_stress.py"],\n'
      '             ["Backtest", "Rolling out-of-sample Kupiec and Christoffersen tests, non-overlapping 10-day windows, 10 offsets", "3-year calibration window; 95% and 99%", "validation/backtest.py, scripts/run_backtest.py"],\n'
      '             ["Validation", "t=0 self-check, martingale tests, delta-normal VaR, backtest, attribution, unit tests", "%d automated tests" % _ntests, "scripts/, tests/"]],')
p.sub('"+1% spot, +1bp rates (parallel and 8 buckets), +1% vol; N = 2,000"', '"+1% spot, +1bp rates (parallel and 8 buckets), +1% vol; N = 1,000; pathwise for equity and FX as a check"')
p.sub('"greeks/book.py, greeks/exposure.py, scripts/run_greeks.py"', '"greeks/book.py, greeks/exposure.py, greeks/pathwise.py, scripts/run_greeks.py"')
p.sub('["greeks/", "book (t=0 Greeks by trade and netting set), exposure (sensitivities of EE, median PFE, PFE99), bumps (curve and parameter bump helpers)"],',
      '["greeks/", "book (t=0 Greeks by trade and netting set), exposure (sensitivities of EE, median PFE, PFE99; close-out context), pathwise (equity and FX deltas without repricing), bumps (curve and parameter bump helpers)"],\n'
      '             ["stress/, validation/", "stress/scenarios (hypothetical and historical-replay shocks, curve shift); validation/backtest (Kupiec, Christoffersen, equity and rates backtests)"],')
p.sub('["exposure/", "aggregate (netting, EE, median PFE, PFE, MPE), collateral (MPOR-shifted), cva (regulatory CVA), sa_cva (Basel aggregation)"],',
      '["exposure/", "spec_exposure (the brief\'s close-out exposure), aggregate (netting, level exposure), collateral (MPOR-shifted illustration), cva (regulatory CVA), xva (DVA, FVA), sa_cva (Basel aggregation), sa_ccr (EAD)"],')
p.sub('["models/", "rates (Hull-White), equity_fx (GBM), calibration and hw_calibration (parameters), equity_factor_model (PCA), credit (PD from spreads)"],',
      '["models/", "rates (Hull-White), g2pp (two-factor), equity_fx (GBM with JPY drifts), calibration and hw_calibration (parameters), equity_factor_model (PCA), credit (PD from spreads)"],')
p.sub('["tests/", "82 tests: engine, time grid, MPOR, negative rates, factor model, BOJ and MOF data, tail convergence, median PFE, CVA and SA-CVA"]],',
      '["tests/", "%d tests: engine, time grid, MPOR, negative rates, factor model, BOJ and MOF data, tail convergence, median PFE, CVA and SA-CVA, close-out exposure, curve splice, JPY factor, G2++, xVA, SA-CCR, backtests, stress, pathwise, risky bond" % _ntests]],')
p.sub('"python scripts/run_greeks.py --scenarios 2000             # book and exposure Greeks (about 75 min)\\n"\n             "python -m pytest tests                                    # 82 tests"))',
      '"python scripts/run_greeks.py --scenarios 1000             # book and exposure Greeks, close-out\\n"\n             "python scripts/run_spec_simulation.py --scenarios 5000    # the close-out exposure (Section 7.1)\\n"\n             "python scripts/run_xva.py && python scripts/run_sa_ccr.py   # CVA/DVA/FVA and SA-CCR\\n"\n             "python scripts/run_backtest.py                            # Kupiec backtest\\n"\n             "python scripts/run_stress.py --scenarios 1000             # stress test\\n"\n             "python -m pytest tests                                    # all automated tests"))')
p.insert_after('add(B(["<b>Counterparty ratings are assumed</b> (BBB financials).', '''
add(P("8.9 Extra credit: a risky-bond sample trade", H2))
add(RN2.risky_bond_section(doc))
''')
p.save()
print("13d done")
