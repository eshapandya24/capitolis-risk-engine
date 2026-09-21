p = "scripts/build_report.py"
s = open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert a in s, "MISSING: " + a[:80]
    s = s.replace(a, b, 1)


plan = '''    add(P("15. Improvement plan for the next week", H1))
    add(P("A review of this work against the requirements in the kickoff deck (project objectives on slide 5, exposure definition and key assumptions on slides 8 and 9, deliverables and extra credit on slide 10), and against an independent implementation of the same brief, identified the gaps below. Items in Priority 1 are needed for the deliverable to meet the brief in full; Priority 2 items complete the extra-credit and validation scope. The numbers in Sections 7 to 9 should be read with the first two known issues in mind until Priority 1 is done."))
    add(P("15.1 Requirements traceability", H2))
    add(tbl([["Kickoff requirement", "Status", "Action"],
             ["Stochastic models for rates, equity and FX, defended", "Done", "-"],
             ["Correlated joint simulation; correlation from history", "Done", "-"],
             ["Provided pricers called on simulated market states", "Done", "-"],
             ["Exposure = movement from the prior-day NPV over a 10-day close-out; no initial margin; variation margin equals the prior-day NPV (slide 9)", "Gap: headline exposure is uncollateralized max(V, 0); the margined view uses a different formula and is a side calculation", "Item 1"],
             ["PFE at the 99th percentile of the 10-day windows, MPE as its peak, EE, over a one-year horizon (slide 8)", "Partial: measures exist but on the uncollateralized definition and to January 2028", "Item 1"],
             ["Exposures per trade and aggregated to the counterparty (slide 8)", "Partial: counterparty and portfolio only are reported", "Item 1"],
             ["Netting-set exposure profiles", "Done", "-"],
             ["Evidence of convergence in the number of simulations (slide 9)", "Done (Section 5.5)", "-"],
             ["Greeks, bumped or pathwise, efficient across scenarios", "Done (Section 9)", "Re-run after Priority 1"],
             ["Speed and performance benchmarks; analytical accuracy benchmarks", "Done (Sections 5 and 11)", "-"],
             ["Market data: USD curve, equity spots and dividends, USDJPY spot and forward curve, vols, correlations (slide 6)", "Partial: the USD long end is flat and the JPY rate is not simulated", "Items 2 and 3"],
             ["Repository, technical report, presentation to the Risk department", "Done; presentation to be refreshed", "Item 8"],
             ["Extra credit: xVA outputs", "Partial: CVA and SA-CVA capital; no DVA or FVA", "Item 5"],
             ["Extra credit: risky bonds and CDS data for new sample trades", "Not done", "Item 9"]],
            widths=[3.6, 2.8, 1.0], font=7.2))
    add(P("15.2 Known issues in the current results", H2))
    add(B(["<b>Exposure definition.</b> The headline exposure numbers (Section 7) are uncollateralized. The brief defines exposure as the movement from the prior-day NPV over a 10-day close-out (slide 9), which is close to our margined calculation in Section 7.4 but not identical: ours compares the value 10 business days later with the same-day value floored at zero, whereas the brief uses the prior-day NPV without a floor. The margined figures in Section 7.4 (MPE99 of about $24.9M, $9.2M and $26.7M for CPTY_A, CPTY_B and CPTY_C) are indicative of the order of magnitude the corrected headline will take.",
           "<b>USD curve beyond seven years.</b> The SOFR-futures curve covers about 6.3 years and is extrapolated flat, so the 2049 Treasury underlying BF_0003 is discounted at 4.27% instead of about 4.64% at 20 years. Repricing with Bloomberg's zero curve gives an NPV of $120.9M for BF_0003 against $101.4M on our curve, about 16 percent higher. CPTY_C exposure, CVA and SA-CVA are therefore understated.",
           "<b>JPY rate not simulated.</b> The JPY Hull-White factor is built and calibrated but JPY equity and USDJPY drift still use a constant differential (Section 4.5)."]))
    add(P("15.3 Work plan", H2))
    add(P("<b>Priority 1: needed to meet the brief in full</b>", BODY))
    add(tbl([["Item", "Work", "Deliverable and check", "Day"],
             ["1", "Implement the exposure of slides 8 and 9: NPV at t plus 10 business days minus NPV at t minus 1 business day, netted, PFE at the 99th percentile of the 10-day windows, EE, MPE, one-year horizon; per trade and per counterparty; keep uncollateralized as a secondary view", "New exposure module and grid node at t-1; unit tests against hand calculations; per-trade and counterparty profiles; comparison with the current Section 7.4 numbers", "1"],
             ["2", "Replace the flat long end of the USD curve with the Bloomberg zero curve (or splice it beyond the last futures contract)", "Curve validated against Treasury and against the Bloomberg curve; BF_0003 NPV reconciled; all trades repriced", "2"],
             ["3", "Wire the JPY Hull-White factor into the simulation: simulate the JPY rate correlated with the USD rate (correlation -0.04), drive JPY equity drift and USDJPY drift from it", "Engine change with tests (JPY factor martingale test, forward-matching for USDJPY); impact on JPY trades reported", "2"],
             ["4", "Re-run everything on the corrected engine: exposure profiles, MPOR view, CVA, SA-CVA, Greeks, convergence at the recommended path count", "Refreshed data files; regression tests; comparison before and after", "3 to 4"]],
            widths=[0.5, 3.2, 3.0, 0.6], font=7.2))
    add(P("<b>Priority 2: completes extra credit and validation</b>", BODY))
    add(tbl([["Item", "Work", "Deliverable and check", "Day"],
             ["5", "Complete xVA: DVA from the negative exposure profile and a Capitolis credit curve, and FVA from a funding spread; net xVA by counterparty", "DVA and FVA with formula tests; net xVA table", "4"],
             ["6", "Backtest simulated PFE against realised outcomes with a Kupiec proportion-of-failures test, at 95 and 99 percent, on the equity names and where possible the book", "Backtest module with truncation of history at each as-of date (no look-ahead); pass or fail statement", "5"],
             ["7", "Optional: SA-CCR exposure-at-default chain (replacement cost, PFE add-on, multiplier) per counterparty for regulatory framing", "Per-counterparty EAD; hand-calculated tests", "5"],
             ["8", "Refresh the report and executive deck for the Risk department presentation; rehearse", "Updated PDF, LaTeX source and deck; slide on the changes and their effect on results", "5"],
             ["9", "Extra credit, risky bonds and CDS data: document the gap and, if a source becomes available, add a risky bond to a sample trade with a credit curve", "Gap statement or new sample trade", "if time"]],
            widths=[0.5, 3.2, 3.0, 0.6], font=7.2))
    add(P("15.4 Further model refinements (after the above)", H2))
    add(B(["Two-factor rate model and stochastic volatility, if Capitolis wants richer dynamics; the vol-of-vol correlation must be applied in the paths if it is fit.",
           "Brownian-bridge interpolation with conditional variance where exposure is read at off-grid dates.",
           "Model-risk study varying mean reversion, volatilities and correlation.",
           "Collateral terms (threshold, minimum transfer amount, initial margin) once Capitolis provides the credit support annexes, and wrong-way risk in CVA.",
           "Real counterparty ratings and credit curves to replace the BBB assumption."]))
    add(PageBreak())

'''
rep('    add(P("Appendix A. Glossary", H1))', plan + '    add(P("Appendix A. Glossary", H1))')

# limitations: two new bullets
rep('add(B(["<b>Uncollateralized and no CSA data.', 'add(B(["<b>Exposure definition and USD curve.</b> The headline exposure is uncollateralized rather than the brief\'s 10-day movement from the prior-day NPV, and the USD curve is flat beyond about seven years (Section 15.2); both are scheduled for correction in Section 15.3.",\n           "<b>Uncollateralized and no CSA data.')
open(p, "w", encoding="utf-8").write(s)
print("ok11")
