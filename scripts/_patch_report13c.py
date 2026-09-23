"""Report patch, part C: Sections 8 and 9."""
import sys
sys.path.insert(0, "scripts")
from _patchlib import Patcher

p = Patcher("scripts/build_report.py")

# ---------------------------------------------------------------- 8 intro and definition
p.replace('add(P("Sections 1 to 7 measure how much a counterparty could owe us.', '''
add(P("Sections 1 to 7 measure how much a counterparty could owe us. This section prices the risk that they fail to pay it (credit valuation adjustment, CVA, with its debit and funding counterparts DVA and FVA), "
      "computes the Basel regulatory capital held against the volatility of that CVA under the Standardised Approach (SA-CVA), and the SA-CCR exposure at default. CVA is computed on both exposure definitions: "
      "the brief's margined close-out exposure, which is what a counterparty with daily variation margin costs, and, as an upper bound, the uncollateralized level exposure, which is what it would cost if no margin were ever called. "
      "All reuse the exposure engine's simulated paths, so the credit numbers are consistent with the exposure numbers."))
''')
p.sub('"DEE(t) = E[ D(t) * max(V(t), 0) ]            D = pathwise risk-free discount factor\\n"',
      '"DEE(t) = E[ D(t) * exposure(t) ]              D = pathwise risk-free discount factor\\n"')
p.replace('add(P("The expected discounted exposure DEE is the exposure profile of Section 7', '''
add(P("The expected discounted exposure DEE is the exposure profile of Section 7 with each scenario discounted along its own simulated short rate; exposure(t) is either the brief's close-out exposure "
      "max(V(t + 10bd) - V(t - 1bd), 0) (the headline) or the level exposure max(V(t), 0). The default probability is implied by a credit spread s through the credit-triangle relation with a loss given default LGD of 60% "
      "(40% recovery, the market-consensus value for senior unsecured claims). The formula assumes that exposure and default are independent (no wrong-way risk) and that the bank itself cannot default; DVA and FVA (Section 8.5) relax the second assumption."))
''')

# ---------------------------------------------------------------- 8.3 results use the 5,000-scenario xVA run for the base CVA
p.insert_after('Rc = load_sa_cva()', 'Rc = RN.override_cva_with_xva(Rc, Xv)')
p.replace('add(P("CVA is concentrated where the exposure is:', '''
add(P("CVA is concentrated where the exposure is: CPTY_C carries %.0f%% of it. CVA scales approximately linearly with the credit spread, so the rating assumption moves the result by a factor of about %.1f between AA and BB. "
      "The CVA figures use %s scenarios (Latin Hypercube) on the brief's close-out exposure; on the uncollateralized level exposure the total is %s (Section 8.5). The SA-CVA sensitivities of Section 8.4 use %s scenarios with common random numbers." % (Rc["cva_by_cpty"]["CPTY_C"] / Rc["cva_total"] * 100, Rc["cva_vs_rating"]["BB"] / Rc["cva_vs_rating"]["AA"], format(Rc["n_scenarios_cva"], ","), "$" + format(Xv["conventions"]["level"]["total"]["CVA"], ",.0f"), format(Rc["n_scenarios"], ","))))
''')

# ---------------------------------------------------------------- 8.4 note, then 8.5 to 8.7
p.insert_after('add(P("SA-CVA (MAR50.27 to 50.77) sets capital', '''
add(P("On this version the CVA sensitivities are taken on the brief's close-out exposure (%s scenarios, common random numbers). Equity and FX delta bumps reuse the base paths and reprice only the trades that hold the factor, exactly as for the Greeks (Section 9.4); interest-rate and volatility bumps re-simulate." % format(Rc["n_scenarios"], ",")))
''')
p.insert_before('add(P("8.5 Assumptions and limitations of the CVA work", H2))', '''
add(P("8.5 DVA and FVA", H2))
add(P("CVA prices the counterparty's default. Two further adjustments complete the xVA picture. <b>DVA</b> is its mirror image: the bank's own default probability applied to what we owe the counterparty, the negative exposure. "
      "<b>FVA</b> is the cost of funding the positive exposure (funding cost, FCA) less the benefit of the negative exposure (funding benefit, FBA) at a funding spread. With EPE and ENE the discounted expected positive and negative exposures:"))
add(code("DVA = LGD_own * sum 0.5 (ENE_{i-1} + ENE_i) * PD_own(t_{i-1}, t_i)\\n"
         "FCA = sum s_f(t_i) dt_i * 0.5 (EPE_{i-1} + EPE_i)       FBA = same with ENE       FVA = FCA - FBA"))
add(P("Both need inputs that are not in the data: Capitolis' own credit and its funding spread. They are assumptions: own credit is proxied by the same BBB bond-index curve as the counterparties (an unrated fintech is at best a BBB proxy) and the funding spread is set equal to the own credit spread, the standard symmetric assumption. "
      "Under that assumption the funding benefit and DVA capture the same economic benefit, so the figure that avoids double counting is CVA - DVA + FCA. The Basel capital framework ignores DVA. The results depend on these assumptions and are shown with their sensitivity to own credit quality."))
_xv_out, _ = RN.xva_section(doc)
add(_xv_out)
_c, _l = Xv["conventions"]["closeout"]["total"], Xv["conventions"]["level"]["total"]
add(P("<b>Reading the table.</b> On the margined close-out exposure the total CVA is %s and DVA %s, so the net credit charge is %s; funding costs %s (FCA %s less FBA %s). On the level exposure CVA is %s and DVA %s, the difference from the close-out figures being the whole mark-to-market that margin would otherwise cover. The dominant asymmetry is that the book is mostly in our favour (CPTY_C's bond forward): the positive exposure, and therefore CVA and FCA, is much larger than the negative exposure that drives DVA and FBA." % (RN._k(_c["CVA"]), RN._k(_c["DVA"]), RN._k(_c["CVA"] - _c["DVA"]), RN._k(_c["FVA"]), RN._k(_c["FCA"]), RN._k(_c["FBA"]), RN._k(_l["CVA"]), RN._k(_l["DVA"]))))
add(P("8.6 SA-CCR exposure at default", H2))
add(RN.sa_ccr_section(doc, S_))
add(P("8.7 CVA walk-through and set-up for the next session", H2))
add(RN2.cva_walkthrough(doc, calib["ref_date"]))
''')

# ---------------------------------------------------------------- 8.8 limitations
p.replace('add(B(["<b>Counterparty ratings are assumed</b> (BBB financials).', '''
add(B(["<b>Counterparty ratings are assumed</b> (BBB financials). CVA and the credit-spread capital scale with this assumption; Section 8.3 shows the range.",
       "<b>Spreads are bond-index proxies</b>, not CDS: the maturity shape is common to all ratings, and the indices are US corporate spreads regardless of counterparty region or sector.",
       "<b>Independence and margin.</b> Headline CVA is unilateral, with exposure and default independent (no wrong-way risk). The two exposure definitions bracket the truth: the close-out exposure assumes daily variation margin at the prior-day value, the level exposure assumes none. Threshold, minimum transfer amount and initial margin are not in the data. DVA and FVA rest on an assumed own credit and funding spread.",
       "<b>Interest rate risk:</b> SA-CVA interest-rate delta and vega are computed for the USD curve. The JPY rate is simulated but only drives the drift of JPY-listed names and USDJPY, and no trade is discounted on JPY, so no JPY rate class is needed; inflation risk factors are omitted (no inflation exposure).",
       "<b>Sensitivities are one-sided bumps</b> with common random numbers, not adjoint sensitivities; vega shifts apply to the volatilities driving the simulated paths (the trades contain no options, so there are no option-pricing volatilities).",
       "<b>Parameters</b> are transcribed from the BIS text (July 2020 revisions); the vega risk weights follow the 100% and 78% values in that text. Regulatory use requires supervisory approval and validation of the sensitivity calculation.",
       "The Basel Basic Approach (BA-CVA) is not computed; it needs only counterparty exposure and maturity and is the natural fallback if SA-CVA approval is not held."]))
''')
p.save()

# ---------------------------------------------------------------- report_greeks.py (Section 9)
g = Patcher("scripts/report_greeks.py")
g.sub("for the uncollateralized book, on the pillar date grid.", "on the brief's close-out exposure, on the pillar date grid with the t - 1bd and t + 10bd nodes.")
g.sub("Exposure Greeks are for the uncollateralized book at 99%; a collateralized book would have different (much smaller) sensitivities.",
      "Exposure Greeks are for the close-out exposure over the first year at 99%; the uncollateralized level exposure has much larger sensitivities (its delta is the delta of the mark-to-market itself).")
g.sub("Interest rate Greeks are for the USD curve only: the JPY rate is not simulated, so JPY rate risk enters through the USD curve.",
      "Interest rate Greeks are for the USD curve only: the simulated JPY rate drives only the drift of JPY-listed names and USDJPY, and no trade is discounted on JPY.")
g.insert_after('add(P("The equity and FX Greeks, which are 37 names plus FX', '''
add(RN2.greeks_method_section(doc, g))
''')
g.sub("from report_tex import B, H1, H2, SMALL, callout, code, P, tbl", "from report_tex import B, H1, H2, SMALL, callout, code, P, tbl\nimport report_new2 as RN2")
g.save()
print("13c done")
