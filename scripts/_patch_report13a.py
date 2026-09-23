"""Report patch, part A: imports, abstract, summary, sections 1 to 6."""
import sys
sys.path.insert(0, "scripts")
from _patchlib import Patcher

p = Patcher("scripts/build_report.py")

# ---------------------------------------------------------------- imports and data loads
p.sub("import report_greeks as RG\n", "import report_greeks as RG\nimport report_new as RN\nimport report_new2 as RN2\n")
p.sub("613", "616", count=20)                       # correlation matrix now on 10-year-yield shocks: 616 aligned days

p.insert_after('S0_ = load_spec()', '''
Xv = RN._j("xva_results.json")
Bt = RN._j("backtest_results.json")
Sa = RN._j("sa_ccr_results.json")
Sx = RN._j("stress_results.json")
Ad = RN._j("additivity.json")
''')

# ---------------------------------------------------------------- abstract
p.replace('add(P("This report describes a Monte Carlo counterparty credit risk (CCR) engine', '''
add(P("This report describes a Monte Carlo counterparty credit risk (CCR) engine for Capitolis' equity swap financing "
      "(ESF) derivatives book, which comprises 16 trades with three counterparties. The engine simulates the joint evolution "
      "of the USD short rate (a one-factor Hull-White model, with a two-factor Gaussian alternative), the JPY short rate, 37 equities and USDJPY "
      "(correlated geometric Brownian motion), reprices every trade in every scenario with the supplied pricer library, and reports Expected "
      "Exposure (EE), median PFE, Potential Future Exposure at the 99th percentile (PFE99) and Maximum PFE (MPE) by trade, by counterparty and for the "
      "portfolio on the 10-day close-out definition specified in the project brief. It prices counterparty credit risk (CVA, with DVA and FVA), "
      "computes the Basel SA-CVA capital requirement and the SA-CCR exposure at default, provides the full set of sensitivities (Greeks) of the book and of "
      "the exposure measures with the method and its cost stated, and is stress tested and backtested against realised history. The report sets out the "
      "underlying concepts from first principles, the market data and calibration, every modelling choice together with the alternatives considered, "
      "the validation performed, and the results. Every quantity is either measured from the engine on real market data as of 2026-08-28 or is an "
      "explicitly stated assumption."))
''')

# ---------------------------------------------------------------- summary table
p.replace('add(tbl([["Measure", "Value", "Meaning"],', '''
_at = Ad["at_portfolio_mpe_date"]
_stress_worst = max(Sx["scenarios"], key=lambda n_: Sx["scenarios"][n_]["closeout"]["__portfolio__"]["MPE"])
_bt99 = [Bt["equity"][c]["confidences"]["0.99"] for c in ("CPTY_A", "CPTY_B", "CPTY_C")]
add(tbl([["Measure", "Value", "Meaning"],
         ["Peak EE (close-out exposure)", f"{m(sp_['EE'])} at {sp_['EE_date']}", "Highest average 10-day close-out exposure within one year"],
         ["Peak median PFE (close-out)", m(sp_["MED"]), "Typical (50th percentile) close-out exposure at its highest date"],
         ["Maximum PFE99, MPE (close-out)", f"{m(sp_['PFE'])} at {sp_['PFE_date']}", "Highest 99th-percentile close-out exposure within one year"],
         ["Portfolio MPE against the sum of counterparty MPEs", f"{m(Ad['mpe_portfolio'])} against {m(sum(Ad['mpe'].values()))}", "No netting across counterparties, and peaks that coincide: little diversification (Section 7.2)"],
         ["Current exposure today (uncollateralized)", m(tot["EE"][0]), "Loss if every counterparty defaulted today with no margin, after netting"],
         ["MPE99, uncollateralized (secondary view)", f"{m(mpe99)} at {D['rep_dates'][j_mpe]}", "Highest 99th-percentile level exposure over the life of the book"],
         ["Concentration", f"{ce0['CPTY_C']/max(tot['EE'][0],1)*100:.0f}% of current exposure is CPTY_C", "A single $500M bond forward (BF_0003) dominates"],
         ["Time profile", "Most exposure has run off by December 2026", "Trades mature; a small Bond TRS tail runs to January 2028"],
         ["CVA, close-out exposure (BBB proxy)", "$" + format(Xv["conventions"]["closeout"]["total"]["CVA"], ",.0f"), "Price of counterparty default risk on the margined close-out exposure, unilateral (Section 8)"],
         ["CVA, uncollateralized exposure", "$" + format(Xv["conventions"]["level"]["total"]["CVA"], ",.0f"), "The same on the level exposure: the price if no margin were ever called"],
         ["DVA and FVA (close-out)", "$%s and $%s" % (format(Xv["conventions"]["closeout"]["total"]["DVA"], ",.0f"), format(Xv["conventions"]["closeout"]["total"]["FVA"], ",.0f")), "On assumed own credit and funding spreads (Section 8.5)"],
         ["SA-CVA capital", "$%.2fM (RWA $%.1fM)" % (Rc0["K_sa_cva"] / 1e6, Rc0["RWA"] / 1e6), "Basel standardised approach on the close-out exposure; dominated by counterparty credit spread risk"],
         ["SA-CCR exposure at default", m(Sa["total"]["EAD"]), "Regulatory EAD, uncollateralized; dominated by the replacement cost of BF_0003 (Section 8.6)"],
         ["Greeks", "t = 0 book Greeks; sensitivities of EE, median PFE and PFE99 to equities, USDJPY, USD rates and volatilities", "Complete, by netting set, method and cost stated (Section 9)"],
         ["Stress test", "%d scenarios; largest close-out MPE %s (%s)" % (len(Sx["scenarios"]), m(Sx["scenarios"][_stress_worst]["closeout"]["__portfolio__"]["MPE"]), RN2.SHORT.get(_stress_worst, _stress_worst)), "Hypothetical and historical replays, by product and along the time path (Section 7.10)"],
         ["Backtest (Kupiec)", "99% equity leg: %s exceptions against %s expected in the three netting sets" % ("/".join(str(r["x"]) for r in _bt99), "/".join("%.1f" % r["expected"] for r in _bt99)), "Realised 10-day moves against the model's quantiles, out of sample (Section 11.7)"]],
        widths=[2.3, 2.5, 3.2]))
''')

# ---------------------------------------------------------------- principal modelling choices
i = p.find('add(P("<b>Principal modelling choices</b>')
p.replace("add(B([", '''
add(B([
    "Monte Carlo under the risk-neutral measure. USD short rate: one-factor Hull-White fitted exactly to today's SOFR curve, with the Bloomberg long end spliced beyond the last futures contract and sigma fitted to the realised volatility of 2y-30y Treasury yields. Equities and USDJPY: correlated geometric Brownian motion driven by the simulated rates; a two-factor Gaussian (G2++) alternative is implemented and compared.",
    "Exposure: the brief's definition, max(V(t + 10bd) - V(t - 1bd), 0) with variation margin equal to the prior-day value, per trade and per counterparty over one year; the uncollateralized level exposure is kept as a secondary view.",
    "Correlation: one static 40x40 matrix (37 equities, USDJPY, USD rate on 10-year-yield shocks, JPY rate) estimated from 616 aligned daily returns and applied through a Cholesky factor; a PCA factor model (5 factors) is provided as an alternative and its cost and benefit are measured (Section 4.4).",
    "Sampling and size: Latin Hypercube sampling (lowest error of the five methods tested) with N = 5,000 scenarios for standard reporting, N = 1,000 for iteration and N = 10,000 for limit sign-off (Section 5.5).",
    "Dates: standard market pillar dates (O/N to 10Y) with every trade's own reset and maturity date, and the t - 1bd and t + 10bd nodes required by the exposure definition, on the grid.",
    "Mean reversion: a = 0.0167 for USD from the swaption cube; for JPY the lower bound a = 0.001, because real JPY volatility rises with tenor (three independent sources).",
    "JPY: a negative-rate-capable Hull-White factor (sigma from the real JPY OIS history, correlated with the USD rate, USDJPY and the equities) drives the drift of JPY-listed names and USDJPY.",
    "Credit: unilateral CVA (MAR50.32) with counterparty spreads proxied from ICE BofA bond indices by an assumed BBB rating and 60% LGD, computed on both exposure definitions; DVA and FVA on assumed own credit and funding spreads; SA-CVA capital and SA-CCR EAD.",
    "Model risk: attribution of every correction, a one-at-a-time perturbation study, a structured stress test and a Kupiec backtest (Sections 7.3, 7.9, 7.10, 11.7)."]))
''', start=i + 1)

# ---------------------------------------------------------------- section 2: figure caption
p.replace('add(doc.figure(fig_t0_npv(D, npv0)', '''
add(doc.figure(fig_t0_npv(D, npv0), "Today's mark-to-market per trade. CPTY_C's total is dominated by BF_0003 (+%.0fM); CPTY_B nets to a small positive, so its exposure today is small." % (npv0[ids.index("BF_0003")] / 1e6)))
''')

# ---------------------------------------------------------------- section 3: data table rows
p.sub('["Volatilities (39)", "Realised, 3 years of daily data", "Diffusion size", "No options data available; documented proxy"],',
      '["Volatilities (39)", "Realised, 3 years of daily data; USD rate sigma fitted to Treasury yield vols", "Diffusion size", "No options data available; documented proxy"],')
p.sub('["SOFR level history", "FRED", "Rate vol, USD-JPY correlation", "From April 2018"],',
      '["SOFR level history", "FRED", "USD-JPY correlation; rate-vol comparison", "From April 2018"],\n'
      '             ["Treasury constant-maturity yields, 3M to 30Y, 1981 to date", "FRED (DGS series)", "USD rate sigma and correlations; G2++ calibration; backtest; stress replays", "Public"],\n'
      '             ["Long price and USDJPY history, 2014-2026", "yfinance", "Backtest and historical stress windows", "Public"],\n'
      '             ["USD SOFR zero curve (long end beyond the last futures contract)", "Bloomberg one-time export, 2026-08-31", "Spliced onto the futures curve beyond about 6.5 years", "Licensed data: derived numbers only"],')

# ---------------------------------------------------------------- 3.1 and 3.2
p.replace('add(P("Databento provides the futures, not a ready OIS curve', '''
add(P("Databento provides the futures, not a ready OIS curve, so we build one: each 3-month SOFR future price gives an implied forward rate (100 - price) for its "
      "reference quarter; chaining consecutive quarters multiplies discount factors. The futures end about 6.5 years out. Beyond the last contract the curve now follows the "
      "forward structure of the Bloomberg USD SOFR zero curve (below); earlier versions extrapolated flat, which was one of the defects corrected in this version (Section 12). "
      "Two real bugs in the futures bootstrap were found by cross-checking with the Treasury curve (Section 12). The curve is the starting point of the Hull-White model and the discount curve at t=0."))
''')
p.replace('add(doc.figure(fig_curve(calib)', '''
add(doc.figure(fig_curve(calib), "The bootstrapped USD SOFR curve, with the long end spliced beyond the last futures contract. The upward slope (zero rate about 3.7% at the front, above 4% by 6 years) means forwards exceed spot rates."))
add(RN.curve_splice(doc, calib, bf3_old=Sx_old_bf3))
''')
p.insert_before('add(P("3.1 The USD curve", H2))', 'Sx_old_bf3 = RN._j("spec_run", "spec_exposure_before_fixes.json")["per_trade"]["BF_0003"]["mtm_t0"]')
i = p.find('add(P("Volatility is the annualised standard deviation of daily changes')
p.replace('add(P("Volatility is the annualised standard deviation of daily changes', '''
add(P("Volatility is the annualised standard deviation of daily changes over the last three years (log returns for equities and FX; simple differences for rates, "
      "because rate LEVELS near or below zero make log returns meaningless). The USD rate volatility is treated separately, below."))
''')
p.replace('add(doc.figure(fig_vols(calib)', '''
add(doc.figure(fig_vols(calib), "Realised volatility spans an order of magnitude across the 37 names. A few names carry 50-76% vol, which dominates tail exposure of the trades that reference them."))
add(RN.rates_vol(doc, calib))
''')
p.sub('the sensitivity test (Section 11) shows how much the results move if vols are 50% higher', 'the model-risk study (Section 7.9) shows how much the results move if vols are 25% and 100% higher')

# ---------------------------------------------------------------- 3.3 correlation text
p.sub("(US and Tokyo trade on different calendars, so series are joined by calendar date rather than timestamp), and compute one pairwise correlation matrix.",
      "(US and Tokyo trade on different calendars, so series are joined by calendar date rather than timestamp), and compute one pairwise correlation matrix. The USD rate factor's row uses daily changes of the 10-year Treasury yield rather than the overnight SOFR fixing, which moves in steps on Fed dates and correlates with nothing.")

# ---------------------------------------------------------------- section 4.1 parameters
p.replace('add(P("<b>Parameters.</b> sigma = ', '''
add(P("<b>Parameters.</b> sigma = %.2f%% (fitted to realised 2y-30y Treasury yield volatility, Section 3.2); a = %.4f (calibrated, Section 6). Today's short rate r(0) = %.2f%%." % (meta["hw_sigma"] * 100, meta["hw_a"], meta["hw_r0"] * 100)))
''')

# ---------------------------------------------------------------- 4.2 SDEs
p.replace('add(code("dS_i / S_i = ( r(t) - q_i ) dt + sigma_i dW_i        USD-quoted names', '''
add(code("dS_i / S_i = ( r_USD - q_i ) dt + sigma_i dW_i                         USD-quoted names\\n"
         "dS_i / S_i = ( r_JPY - q_i + rho_iX sigma_i sigma_X ) dt + sigma_i dW_i   JPY-quoted names (S in JPY)\\n"
         "dX / X     = ( r_JPY - r_USD + sigma_X^2 ) dt + sigma_X dW_X             USDJPY, X = JPY per USD"))
''')
p.replace('add(P("Each step is the exact log-normal step', '''
add(P("Each step is the exact log-normal step ln S(t+dt) = ln S(t) + (drift - sigma^2/2) dt + sigma sqrt(dt) Z, with the short rates at the start of the step (so equities, FX and rates are linked). The drifts follow from requiring that every "
      "USD-denominated tradable asset, discounted at the USD money market, is a martingale. A JPY bank account valued in USD, B_JPY / X, must earn the USD rate, which gives USDJPY (JPY per USD) a drift of r_JPY - r_USD: it falls when USD rates exceed JPY rates. A JPY-listed name held by a USD investor has USD value S / X and must also earn r_USD - q, "
      "which gives the JPY-currency price the drift r_JPY - q plus a quanto correction rho sigma_S sigma_X. Both are verified by martingale tests (Section 11.2). An earlier version used the drift of USD-per-JPY for a JPY-per-USD quote, with the wrong sign; the correction is documented in Section 12 and its effect in Section 7.3."))
''')

# ---------------------------------------------------------------- 4.4 PCA
p.sub("Section 7.6 compares its exposure profiles with the full-rank engine.", "Section 7.8 compares its exposure profiles with the full-rank engine.")
p.insert_after('add(P("<b>Trade-off.</b> The factor model is smoother', 'add(RN2.pca_section(doc))')

# ---------------------------------------------------------------- 4.5 JPY
p.replace('add(tbl([["JPY factor parameter", "Value", "Source / status"],', '''
_jc = calib["jpy_rate_corr_detail"]
add(tbl([["JPY factor parameter", "Value", "Source / status"],
         ["Curve", "JPY OIS zero curve, 2026-08-28", "Bootstrapped from the daily JPY OIS par history (project-team Bloomberg file); matches Bloomberg's own zero curve to within 1bp at all tenors"],
         ["sigma", "%.3f%%/yr" % (hj["sigma"] * 100), "Realised vol of the overnight call rate, 3y window, from the same OIS file (Bank of Japan TONA gives 0.276%, consistent)"],
         ["a (mean reversion)", "%.4f" % hj["a"], "Lower bound: all three real JPY calibrations gave a negative a (Section 6.2)"],
         ["USD-JPY rate-factor correlation", "%+.3f" % meta["usd_jpy_corr"], "Calibrated from real SOFR vs TONA daily changes (n=%d, p=%.2f): statistically zero" % (meta["usd_jpy_corr_detail"]["n_obs"], meta["usd_jpy_corr_detail"]["p_value"])],
         ["Correlation with USDJPY and the equities", "USDJPY %+.2f; equities %+.2f to %+.2f" % (_jc and calib["jpy_rate_corr"]["FX_USDJPY"], min(v for k, v in calib["jpy_rate_corr"].items() if k != "FX_USDJPY"), max(v for k, v in calib["jpy_rate_corr"].items() if k != "FX_USDJPY")), "Daily changes of the 1-year JPY OIS rate against daily returns, same 3-year window (n=%d)" % _jc["n_obs"]],
         ["Wired into simulate_paths()?", "YES", "The simulated JPY rate drives the drift of the JPY-listed names and USDJPY, and a JPY discount curve is available at every node"]],
        widths=[1.8, 1.6, 4.3]))
''')
p.replace('add(P("<b>Why this matters little for the results:</b>', '''
add(P("<b>Effect on the results.</b> Only 2 of 16 trades hold JPY names, so the effect is confined to their netting sets; its size, together with that of the USDJPY drift correction, is measured in the attribution of Section 7.3."))
''')
p.insert_before('add(PageBreak())', '''
add(P("4.6 A two-factor rates model: G2++", H2))
add(RN.g2_section(doc, calib))
''', start=p.find('add(P("<b>Effect on the results.</b>'))

# ---------------------------------------------------------------- 5.1 pipeline
p.replace('add(code("1. calibrate:   curve, sigma, a, vols, correlation (real data)', '''
add(code("1. calibrate:   curve (futures + long end), sigma, a, JPY factor, vols, correlation (real data)\\n"
         "2. grid:        pillar dates + trade event dates + t-1bd and t+10bd nodes around every reporting date\\n"
         "3. draw:        random numbers (Latin Hypercube) -> correlated shocks (Cholesky or PCA)\\n"
         "4.  step:       advance USD and JPY short rates, 37 equities, USDJPY along every path\\n"
         "5. reprice:     for every (scenario, node): build MarketState, call npv() of all 16 trades\\n"
         "6. aggregate:   exposure(t) = max(V(t+10bd) - V(t-1bd), 0), netted by counterparty -> EE, median PFE, PFE99, MPE"))
''')

# ---------------------------------------------------------------- 6: practical impact
p.replace('add(P("<b>Practical impact:</b> small.', '''
add(P("<b>Practical impact:</b> small. JPY affects two trades, and the USD parameters are the ones used for discounting the whole book."))
''')

p.save()
print("13a done")
