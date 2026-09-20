import re
p = "scripts/build_report.py"
s = open(p, encoding="utf-8").read()


def rep(a, b, count=1):
    global s
    assert a in s, "MISSING: " + a[:100]
    s = s.replace(a, b, count)


# ---------------------------------------------------------------- front matter
front = '''    add(titlepage("Monte Carlo Counterparty Credit Risk Engine",
                  "Methodology, calibration and results for the ESF derivatives book",
                  "Prepared for Capitolis | Berkeley MFE Industry Project",
                  "Valuation date 2026-08-28 | September 2026"))
    add("\\\\section*{Abstract}\\n")
    add(P("This report describes a Monte Carlo counterparty credit risk (CCR) engine for Capitolis' equity swap financing "
          "(ESF) derivatives book, which comprises 16 trades with three counterparties. The engine simulates the joint evolution "
          "of the USD short rate (one-factor Hull-White model), 37 equities and USDJPY (correlated geometric Brownian motion), "
          "reprices every trade in every scenario with the supplied pricer library, and reports Expected Exposure (EE), median "
          "PFE, Potential Future Exposure at the 99th percentile (PFE99) and Maximum PFE (MPE) by counterparty and for the "
          "portfolio. The report sets out the underlying concepts from first principles, the market data and calibration, each "
          "modelling choice together with the alternatives considered, the validation performed, and the results. Every "
          "quantity is either measured from the engine on real market data as of 2026-08-28 or is an explicitly stated assumption."))
    add(make_toc())
    add(PageBreak())
    add("\\\\section*{Summary of results}\\n")
    add(P("The table reports the portfolio results for the uncollateralized book (3,000 Latin Hypercube scenarios, PFE at the 99th percentile).", BODY))
    ce0 = {c: float(per[c]["EE"][0]) for c in per}
    add(tbl([["Measure", "Value", "Meaning"],
             ["Current exposure (portfolio)", m(tot["EE"][0]), "Loss if every counterparty defaulted today, after netting"],
             ["Peak EE", f"{m(tot['EE'].max())} at {D['rep_dates'][int(tot['EE'].argmax())]}", "Highest average future exposure"],
             ["Peak median PFE", f"{m(tot['MED'].max())} at {D['rep_dates'][int(tot['MED'].argmax())]}", "Typical (50th percentile) exposure at its highest date"],
             ["Maximum PFE99 (MPE)", f"{m(mpe99)} at {D['rep_dates'][j_mpe]}", "Highest 99th-percentile exposure over the life of the book"],
             ["Concentration", f"{ce0['CPTY_C']/max(tot['EE'][0],1)*100:.0f}% of current exposure is CPTY_C", "A single $500M bond forward (BF_0003) dominates"],
             ["Time profile", "Most exposure has run off by December 2026", "Trades mature; a small Bond TRS tail runs to January 2028"]],
            widths=[2.3, 2.3, 3.4]))
    add(P("<b>Principal modelling choices</b> (each is justified in Section 8):", BODY))
    add(B([
        "Monte Carlo under the risk-neutral measure. USD short rate: one-factor Hull-White (exact fit to today's SOFR curve). Equities and USDJPY: correlated geometric Brownian motion driven by the simulated rate.",
        "Correlation: one static 39x39 matrix estimated from 613 aligned daily returns and applied through a Cholesky factor; a PCA factor model (5 factors) is provided as an alternative.",
        "Sampling and size: Latin Hypercube sampling (lowest error of the five methods tested) with N = 5,000 scenarios for standard reporting (PFE99 relative standard error about 0.3%), N = 1,000 for iteration and N = 10,000 for limit sign-off (Section 5.5).",
        "Dates: standard market pillar dates (O/N to 10Y) with every trade's own reset and maturity date forced onto the grid.",
        "Mean reversion: a = 0.0167 for USD from the swaption cube; JPY reuses the USD value because real JPY volatility rises with tenor (two independent sources).",
        "JPY: a negative-rate-capable Hull-White factor is built (sigma from real TONA; correlation with the USD rate calibrated at approximately zero) but does not yet drive JPY equity drift.",
        "The book is treated as uncollateralized (no CSA data); an MPOR-shifted collateralized calculation is built and demonstrated as a hypothetical."]))
    add(PageBreak())
'''
s = re.sub(r"    add\(Spacer\(1, 0\.6 \* inch\)\)\n    add\(P\(\"Monte Carlo Counterparty Credit Risk Engine\".*?add\(P\(\"Contents\", TOCH\)\); add\(toc\); add\(PageBreak\(\)\)\n",
           lambda m_: front, s, flags=re.S)

# ---------------------------------------------------------------- 1.3 measures
rep('["PFE (Potential Future Exposure)", f"The {int(CONF*100)}th percentile of exposure at date t", "A worst-plausible level: in 99 of 100 scenarios exposure at t is below it. Used for limits"]',
    '["PFE99 (Potential Future Exposure)", f"The {int(CONF*100)}th percentile of exposure at date t", "In 99 of 100 scenarios exposure at t is below this level. Used to set limits"]')
s = re.sub(r'\["Median exposure", "50th percentile of exposure across scenarios at date t",',
           '["Median PFE", "50th percentile of exposure across scenarios at date t",', s, count=1)
s = re.sub(r'    add\(P\("<b>Confidence level\.</b>.*?labelled PFE95\."\)\)\n',
           '    add(P("<b>Confidence level.</b> PFE is reported at the 99th percentile throughout, together with the median PFE (the 50th percentile of the same exposure distribution), which describes the typical scenario."))\n',
           s, flags=re.S)
rep("with EE, median, PFE95 and PFE99 marked", "with EE, median PFE and PFE99 marked")
rep("the mean, median and percentiles differ so much", "EE, median PFE and PFE99 differ so much")

# ---------------------------------------------------------------- 3.3 wording
rep('add(P("<b>Is this matrix created every day? No.</b> It is one static matrix. We take',
    'add(P("<b>Estimation and stationarity.</b> The matrix is static, not re-estimated per date. We take')
rep("(US and Tokyo trade on different calendars, so we join by calendar date, not timestamp - a bug we hit once)",
    "(US and Tokyo trade on different calendars, so series are joined by calendar date rather than timestamp)")

# ---------------------------------------------------------------- 5.2 wording
s = re.sub(r'"Capitolis\' hint was to use <b>pillar dates</b>: the standard market curve tenors already used to build the SOFR curve',
           '"Following Capitolis\' guidance, we adopt <b>pillar dates</b>: the standard market curve tenors also used to build the SOFR curve', s)
rep('"This is also how production CCR systems space dates: dense short-term, sparse long-term. On top, every trade',
    '"This mirrors production CCR practice: dense short-term, sparse long-term. In addition, every trade')

# ---------------------------------------------------------------- 5.4 + 5.5 blocks
newblock = '''    fg, opt, real = fig_vr()
    add(doc.figure(fg, "Left: on a European call with a known Black-Scholes value, Latin Hypercube has ~%.0fx lower error than pseudo-random. Right: on the real 663-dimensional engine the ranking is preserved but compressed; Latin Hypercube gives %.2fx lower variability in the PFE99 estimate." % (opt["pseudo_random"]["rmse"] / opt["latin_hypercube"]["rmse"], real["pseudo_random"]["std"] / real["latin_hypercube"]["std"])))
    verdicts = {"pseudo_random": "Baseline", "antithetic": "Not recommended: no benefit at high dimension",
                "moment_matched": "Not recommended: helps only in low dimension", "sobol": "Second best; slower per trial, advantage shrinks with dimension",
                "latin_hypercube": "SELECTED: lowest error on both tests at negligible extra cost"}
    rows = [["Method", "Call RMSE", "vs pseudo-random", "PFE99 estimator std, real engine (USD)", "vs pseudo-random", "Verdict"]]
    for k in opt:
        rows.append([k.replace("_", " "), "%.4f" % opt[k]["rmse"], "%.1fx better" % (opt["pseudo_random"]["rmse"] / opt[k]["rmse"]) if k != "pseudo_random" else "-",
                     "%s" % format(real[k]["std"], ",.0f"), "%.2fx" % (real["pseudo_random"]["std"] / real[k]["std"]) if k != "pseudo_random" else "-", verdicts[k]])
    add(tbl(rows, widths=[1.3, 0.9, 1.1, 1.9, 1.1, 2.6]))
    add(P("<b>Finding.</b> Antithetic and moment-matching sampling, which help in one dimension, give no benefit at 663 effective dimensions (39 factors x 17 time steps). Sobol's advantage shrinks (the curse of dimensionality). Latin Hypercube retains a clear advantage because it stratifies each dimension's marginal distribution independently."))
    add(callout("<b>Decision: Latin Hypercube sampling.</b> It has the lowest error in both the controlled test and the real engine, at negligible additional cost over plain pseudo-random draws."))
    add(PageBreak())

    add(P("5.5 Number of scenarios", H2))
    add(P("Monte Carlo error falls as 1/sqrt(N). Rather than rerun the expensive repricing at every candidate N, we estimate the standard error by bootstrap resampling of a simulated pool. Two studies are combined: (i) resampling of the 3,000-scenario reporting run, at the date of peak PFE99, for both PFE99 and the median PFE; (ii) a dedicated 30,000-scenario pool for the 99th percentile at the one-year node, which extends the range to large N."))
    fg, c99, r99, boot, jdate = fig_conv(D, meta)
    add(doc.figure(fg, "Left: relative standard error of PFE99 and median PFE at the peak-PFE date (%s); the error follows the 1/sqrt(N) law. Middle and right: PFE99 tail study at one year; error is larger for the same N, and the marginal gain per additional batch peaks at N = 5,000 and then declines." % jdate))
    rows = [["N", "Relative SE of PFE99", "Relative SE of median PFE"]]
    for b in boot:
        rows.append([format(b["N"], ","), "%.2f%%" % b["se99"], "%.2f%%" % b["se50"]])
    se3000 = boot[-1]["se99"] * np.sqrt(boot[-1]["N"] / 3000.0)
    add(tbl(rows, widths=[1.0, 2.0, 2.0]))
    add(P("Relative standard errors at the peak-PFE date, bootstrapped from the reporting run (finite-pool corrected). Extrapolating with the 1/sqrt(N) law, the 3,000-scenario run used for this report has a PFE99 relative standard error of about %.2f%% at its peak." % se3000, SMALL))
    verdicts_n = {500: "Screening only", 1000: "Iteration and what-if runs", 2000: "Acceptable for routine monitoring", 5000: "RECOMMENDED: standard reporting",
                  10000: "Recommended for limit sign-off", 15000: "Diminishing returns", 20000: "Diminishing returns", 25000: "Diminishing returns"}
    rows = [["N", "PFE99 (USD)", "Relative SE", "Bias vs 30k pool", "Marginal SE gain", "Est. time", "Verdict"]]
    for r in c99["results"]:
        if r["N"] == c99["N_pool"]:
            continue
        rows.append([format(r["N"], ","), format(r["PFE_mean"], ",.0f"), "%.2f%%" % r["relative_se_pct"], "%+.2f%%" % r["bias_vs_pool_pct"],
                     "-" if r["marginal_se_improvement_pct"] is None else "%+.1f%%" % r["marginal_se_improvement_pct"],
                     "%ss" % format(r["est_time_s"], ",.0f"), verdicts_n[r["N"]]])
    add(tbl(rows, widths=[0.7, 1.2, 0.9, 1.1, 1.1, 0.8, 2.2]))
    add(P("Tail study (PFE99 of the portfolio at the one-year node, pool value $%s, 30,000 scenarios). Times assume 8 cores." % format(c99["pool_pfe_reference"], ",.0f"), SMALL))
    add(callout("<b>Decision: number of paths.</b> Use <b>N = 5,000</b> for standard PFE99 reporting (relative standard error 0.29%%, about 8 minutes). Use <b>N = 1,000</b> for iteration and what-if analysis (0.66%%, about 2 minutes) and <b>N = 10,000</b> when a limit is being signed off (0.21%%, about 15 minutes). Do not exceed 15,000: beyond that the marginal gain per additional batch falls while cost rises, and model uncertainty (mean reversion, volatility proxy) exceeds the remaining sampling error. The figures in this report use N = 3,000 (PFE99 error about %.2f%%), which is adequate for its purpose." % se3000))
    add(PageBreak())

'''
s = re.sub(r"    fg, opt, real = fig_vr\(\)\n.*?(?=    # ---------- 6 calibration)", lambda m_: newblock, s, flags=re.S)

# ---------------------------------------------------------------- 7.2
rep('"EE, median, PFE95 and PFE99 for each counterparty and the portfolio. The shaded band runs from the median to PFE99."',
    '"EE, median PFE and PFE99 for each counterparty and the portfolio. The shaded band runs from the median PFE to PFE99."')
rep('rows = [["Counterparty", "EE(0)", "Peak EE", "Peak median", "Peak PFE95", "MPE (peak PFE99)", "MPE date"]]',
    'rows = [["Counterparty", "EE(0)", "Peak EE", "Peak median PFE", "MPE (peak PFE99)", "MPE date"]]')
s = s.replace('m(p["MED"].max()), m(p["P95"].max()), m(p["P99"].max())', 'm(p["MED"].max()), m(p["P99"].max())')
rep("add(tbl(rows, widths=[1.2, 0.9, 0.9, 1.0, 1.0, 1.4, 1.1]))", "add(tbl(rows, widths=[1.3, 1.0, 1.0, 1.3, 1.5, 1.2]))")
rep("<b>EE versus median versus PFE.</b> The median is far below EE", "<b>EE, median PFE and PFE99.</b> The median PFE is far below EE")
rep("the median describes the typical outcome, and PFE99 describes the bad tail. Reporting all three prevents any single number from misleading.",
    "the median PFE describes the typical outcome, and PFE99 describes the adverse tail. Reporting all three prevents any single statistic from misleading.")
rep("the median exposure is zero even though EE and PFE are large", "the median PFE is zero even though EE and PFE99 are large")

# ---------------------------------------------------------------- misc wording
rep('net by counterparty -> max(.,0) -> EE, median, PFE, MPE', 'net by counterparty -> max(.,0) -> EE, median PFE, PFE99, MPE')
rep('["Confidence", "PFE99 (+ median, EE, PFE95 for context)", "99.9%, 95%", "99% intended target; 99.9% needed far more paths for little insight"]',
    '["Confidence", "PFE99 and median PFE (with EE)", "99.9%, 95%", "99% is the specified target; 99.9% needs far more paths for little added insight"]')
rep('["Scenario count", "3,000 (reporting); 10-15k for tight PFE99", "30,000 pool", "Diminishing returns; model risk dominates beyond a few thousand"]',
    '["Scenario count", "5,000 (reporting); 1,000 (iteration); 10,000 (sign-off)", "30,000 pool", "Diminishing returns beyond 10-15k; model risk dominates"]')
rep('["7", "PFE confidence was 99.9% by mistake in the tail study", "Corrected to 99% and fully re-run; tests updated"]',
    '["7", "Tail-convergence study initially run at 99.9% rather than the specified 99%", "Re-run at 99%; tests and documentation updated"]')
rep('"Ask Capitolis whether any trade is margined and on what terms; that single fact matters more than any modelling refinement.",',
    '"We recommend confirming with Capitolis whether any trade is margined, and on what terms; that fact matters more than any further modelling refinement.",')
rep('"Use 3,000 Latin-Hypercube scenarios for reporting; 10,000-15,000 for a tight PFE99.",',
    '"Use Latin Hypercube sampling with N = 5,000 for reporting, N = 1,000 for iteration and N = 10,000 for limit sign-off (Section 5.5).",')
s = re.sub(r"and median of \{m\(tot\['MED'\]\.max\(\)\)\}", "and median PFE of {m(tot['MED'].max())}", s)
rep('["Median exposure", "50th percentile exposure at a date"],', '["Median PFE", "50th percentile of exposure at a date"],')
rep('"Each was caught because something was checked against an independent source, a hand calculation or a full end-to-end run, not because the first attempt was assumed right."',
    '"Each defect was identified by checking against an independent source, a hand calculation or a full end-to-end run."')
rep('add(P("10. Bugs found and fixed", H1))', 'add(P("10. Defects identified and resolved", H1))')
rep('add(P("11. Assumptions and limitations (what a reader should not over-trust)", H1))', 'add(P("11. Assumptions and limitations", H1))')
rep('["Bloomberg data is a single', '["Bloomberg data is a single') if False else None
rep('"Licensed: derived numbers only appear here, never the raw data"', '"Licensed data: only derived quantities are reported"')
open(p, "w", encoding="utf-8").write(s)
print("ok2")
