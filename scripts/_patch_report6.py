import re
p = "scripts/build_report.py"
s = open(p, encoding="utf-8").read()


def rep(a, b, count=1):
    global s
    assert a in s, "MISSING: " + a[:90]
    s = s.replace(a, b, count)


# ------------------------------------------------------------ figure functions
figs = '''
def load_sa_cva():
    return json.load(open(os.path.join(PROC, "sa_cva_results.json")))


def fig_credit_curves():
    from risk_engine.market.credit_spreads import rating_spread_curve
    ref = date(2026, 8, 28)
    fig, ax = plt.subplots(figsize=(5.6, 2.6))
    tn = np.linspace(0.5, 10, 40)
    for rt, c in zip(("AA", "A", "BBB", "BB"), (NAVY, TEAL, ORANGE, GOLD)):
        t, sp = rating_spread_curve(rt, ref, tn)
        ax.plot(t, sp * 1e4, color=c, label=rt, lw=1.8)
    ax.set_xlabel("maturity (years)"); ax.set_ylabel("proxy credit spread (bp)"); ax.legend(ncol=4)
    ax.set_title("Proxy credit spread curves by rating (ICE BofA OAS, FRED, 2026-08-28)")
    return fig


def fig_cva_results(R_):
    fig, ax = plt.subplots(1, 3, figsize=(7.6, 2.7))
    t = np.array(R_["times"]) * 365.25
    for c, col in zip(("CPTY_A", "CPTY_B", "CPTY_C"), (NAVY, TEAL, ORANGE)):
        ax[0].plot(t, np.array(R_["dee"][c]) / 1e6, color=col, label=c)
    ax[0].set_title("Discounted EE"); ax[0].set_xlabel("days"); ax[0].set_ylabel("USD M"); ax[0].legend()
    cs = ["CPTY_A", "CPTY_B", "CPTY_C"]
    ax[1].bar(range(3), [R_["cva_by_cpty"][c] / 1e3 for c in cs], color=[NAVY, TEAL, ORANGE])
    ax[1].set_xticks(range(3)); ax[1].set_xticklabels(cs, fontsize=7); ax[1].set_title("CVA (BBB proxy), USD thousand")
    rt = list(R_["cva_vs_rating"])
    ax[2].bar(range(len(rt)), [R_["cva_vs_rating"][r] / 1e3 for r in rt], color=PAL[:len(rt)])
    ax[2].set_xticks(range(len(rt))); ax[2].set_xticklabels(rt, fontsize=7); ax[2].set_title("Portfolio CVA vs rating, USD thousand")
    return fig


def fig_sa_cva(R_):
    S_ = R_["sensitivities"]
    fig, ax = plt.subplots(1, 3, figsize=(7.6, 2.7))
    ax[0].bar(range(5), np.array(S_["ir_delta"]) / 1e6, color=NAVY)
    ax[0].set_xticks(range(5)); ax[0].set_xticklabels(["1y", "2y", "5y", "10y", "30y"], fontsize=7)
    ax[0].set_title("IR delta: dCVA per +1bp (USD M)", fontsize=8)
    ct = list(S_["ccs_delta"])
    ax[1].bar(range(len(ct)), [S_["ccs_delta"][k] / 1e6 for k in ct], color=[ORANGE if "CPTY_C" in k else TEAL for k in ct])
    ax[1].set_xticks([]); ax[1].set_title("Counterparty spread delta: dCVA per 1.0 spread", fontsize=8)
    cap = R_["capital_by_class"]
    ks = list(cap)
    ax[2].barh(range(len(ks)), [cap[k] / 1e6 for k in ks], color=NAVY)
    ax[2].set_yticks(range(len(ks))); ax[2].set_yticklabels([k.replace("_", " ") for k in ks], fontsize=7)
    ax[2].invert_yaxis(); ax[2].set_title("SA-CVA capital by class (USD M)", fontsize=8)
    return fig

'''
i = s.index("# ------------------------------------------------------------------ report\ndef main():")
s = s[:i] + figs + "\n" + s[i:]

# ------------------------------------------------------------ section 8 text
sec = '''
    # ---------- 8 CVA
    Rc = load_sa_cva()
    cpt = ["CPTY_A", "CPTY_B", "CPTY_C"]
    add(P("8. Credit valuation adjustment and SA-CVA capital", H1))
    add(P("Sections 1 to 7 measure how much a counterparty could owe us. This section prices the risk that they fail to pay it (credit valuation adjustment, CVA) and computes the Basel regulatory capital held against the volatility of that CVA under the Standardised Approach (SA-CVA). Both reuse the exposure engine unchanged."))
    add(P("8.1 Definition", H2))
    add(P("CVA is the expected loss from counterparty default, assuming the bank itself cannot default (unilateral CVA). Following Basel MAR50.32:"))
    add(code("CVA = LGD * sum_i  0.5 * [ DEE(t_{i-1}) + DEE(t_i) ] * PD(t_{i-1}, t_i)\\n"
             "DEE(t) = E[ D(t) * max(V(t), 0) ]            D = pathwise risk-free discount factor\\n"
             "PD(t_{i-1}, t_i) = exp(-s_{i-1} t_{i-1}/LGD) - exp(-s_i t_i/LGD)      (market-implied, from spreads)"))
    add(P("The expected discounted exposure DEE is the exposure profile of Section 7 with each scenario discounted along its own simulated short rate. The default probability is implied by a credit spread s through the credit-triangle relation with a loss given default LGD of 60% (40% recovery, the senior unsecured convention). Exposure and default are assumed independent, so wrong-way risk is excluded, and the book is treated as uncollateralized because no margin terms are available."))
    add(P("8.2 Credit inputs: rating proxies from bond spreads", H2))
    add(P("CDS spreads for the counterparties are not available, and the counterparties are anonymised. MAR50.32(3) permits an illiquid counterparty's spread to be proxied from liquid peers by credit quality, industry and region. We proxy by credit quality using public bond-market data: the ICE BofA US corporate option-adjusted spread indices by rating (FRED), with the maturity shape taken from the ICE BofA corporate index by maturity bucket, scaled to each rating. The rating-level spread is one number per rating, so the same maturity shape is used for all ratings (a disclosed simplification)."))
    add(doc.figure(fig_credit_curves(), "Proxy spread curves by rating on the valuation date. The BBB curve used for the counterparties runs from about %.0f bp at 6 months to about %.0f bp at 10 years." % (Rc["spread_curves_bp"]["CPTY_A"][0], Rc["spread_curves_bp"]["CPTY_A"][-1])))
    add(tbl([["Counterparty", "Assumed rating", "Assumed sector", "Basis"],
             ["CPTY_A", Rc["ratings"]["CPTY_A"], "Financials (SA-CVA bucket 2)", "Assumption: unrated counterparty proxied at BBB"],
             ["CPTY_B", Rc["ratings"]["CPTY_B"], "Financials (SA-CVA bucket 2)", "Assumption"],
             ["CPTY_C", Rc["ratings"]["CPTY_C"], "Financials (SA-CVA bucket 2)", "Assumption"]], widths=[1.2, 1.2, 2.2, 3.0]))
    add(P("The counterparty identities and ratings were not provided, so these are explicit assumptions. Because they matter more than any modelling choice, Section 8.3 reports CVA across the whole rating range so the reader can substitute the correct rating."))
    add(P("8.3 Results: CVA", H2))
    add(doc.figure(fig_cva_results(Rc), "Left: expected discounted exposure by counterparty. Middle: CVA by counterparty at the BBB proxy. Right: portfolio CVA if all counterparties had the rating shown."))
    rows = [["Counterparty", "CVA (USD)", "Share of total"]]
    for c in cpt:
        rows.append([c, format(Rc["cva_by_cpty"][c], ",.0f"), "%.0f%%" % (Rc["cva_by_cpty"][c] / Rc["cva_total"] * 100)])
    rows.append(["Portfolio", format(Rc["cva_total"], ",.0f"), "100%"])
    add(tbl(rows, widths=[2.0, 2.0, 1.5]))
    rows = [["Rating", "Portfolio CVA (USD)", "Multiple of BBB"]]
    for r_, v in Rc["cva_vs_rating"].items():
        rows.append([r_, format(v, ",.0f"), "%.2fx" % (v / Rc["cva_vs_rating"]["BBB"])])
    add(tbl(rows, widths=[1.2, 2.2, 1.5]))
    add(P("CVA is concentrated where the exposure is: CPTY_C carries %.0f%% of it, as it carries almost all of the exposure. CVA scales approximately linearly with the credit spread, so the rating assumption moves the result by a factor of about %.1f between AA and BB. These figures use %s scenarios (Latin Hypercube) with common random numbers across the sensitivity runs of Section 8.4." % (Rc["cva_by_cpty"]["CPTY_C"] / Rc["cva_total"] * 100, Rc["cva_vs_rating"]["BB"] / Rc["cva_vs_rating"]["AA"], format(Rc["n_scenarios"], ","))))
    add(P("8.4 Basel SA-CVA capital", H2))
    add(P("SA-CVA (MAR50.27 to 50.77) sets capital from the sensitivity of regulatory CVA to market risk factors. It is an adaptation of the market-risk standardised approach and needs supervisory approval, a CVA desk and monthly sensitivity calculation (MAR50.30); the figures here are therefore indicative of the requirement, not a filed number. For each risk factor k the CVA sensitivity s_k is computed by bump-and-reprice with common random numbers, converted to a weighted sensitivity WS_k = RW_k x s_k, and aggregated by bucket and risk class:"))
    add(code("K_b = sqrt( sum_k WS_k^2 + sum_{k!=l} rho_kl WS_k WS_l )        S_b = clip( sum_k WS_k, -K_b, +K_b )\\n"
             "K   = m_CVA * sqrt( sum_b K_b^2 + sum_{b!=c} gamma_bc S_b S_c )\\n"
             "Capital = sum over classes of ( K_delta + K_vega );   RWA = 12.5 * Capital"))
    add(P("Risk classes present in the book, the shift used for each sensitivity and the Basel parameters applied:"))
    add(tbl([["Risk class", "Risk factors and shift", "Risk weight", "Correlation"],
             ["Interest rate delta (USD)", "USD risk-free yield at 1, 2, 5, 10, 30y; +1bp with triangular weights", "1.11%, 0.93%, 0.74%, 0.74%, 0.74%", "Tenor matrix 31-91% (Table 4)"],
             ["Interest rate vega (USD)", "All USD rate volatilities, +1% relative", "100%", "Single factor"],
             ["FX delta (USDJPY)", "USDJPY spot, +1% relative", "11%", "Single factor; cross-bucket 0.6"],
             ["FX vega", "USDJPY volatility, +1% relative", "100%", "Single factor"],
             ["Counterparty credit spread", "Each counterparty at 0.5, 1, 3, 5, 10y; +1bp", "5% (financials, investment grade)", "Tenor 0.9 x name 0.5 (unrelated)"],
             ["Equity delta", "All names in an equity bucket, +1% relative spot", "30-55% by bucket", "Cross-bucket 0.15"],
             ["Equity vega", "All volatilities in a bucket, +1% relative", "78% large cap, 100% small cap", "Cross-bucket 0.15"],
             ["Reference credit, commodity", "None: no such drivers of exposure", "-", "-"]], widths=[1.6, 3.0, 1.7, 1.6], font=7.4))
    add(Spacer(1, 4))
    eqb = Rc["equity_buckets"]
    add(P("Equity names are assigned to Basel buckets by size (market capitalisation of at least USD 2 billion), region (advanced versus emerging economy) and sector, using yfinance data: " + ", ".join("bucket %s: %d names" % (b, n_) for b, n_ in sorted(eqb.items(), key=lambda kv: int(kv[0]))) + "."))
    add(doc.figure(fig_sa_cva(Rc), "Left: CVA sensitivity to a 1bp rise in USD yields at each SA-CVA tenor. Middle: sensitivity of CVA to the counterparty credit spreads (three counterparties by five tenors). Right: SA-CVA capital by risk class."))
    cap = Rc["capital_by_class"]
    rows = [["Risk class", "Capital K (USD)"]]
    for k_, v in cap.items():
        rows.append([k_.replace("_", " "), format(v, ",.0f")])
    rows.append(["Total SA-CVA capital requirement (m_CVA = 1)", format(Rc["K_sa_cva"], ",.0f")])
    rows.append(["Risk-weighted assets (12.5 x capital)", format(Rc["RWA"], ",.0f")])
    rows.append(["Total if the pre-2023 multiplier m_CVA = 1.25 applied", format(Rc["K_sa_cva_m125"], ",.0f")])
    add(tbl(rows, widths=[4.0, 2.0]))
    top = max(cap, key=cap.get)
    add(P("The requirement is dominated by %s (%.0f%% of the total), as is typical: a 5%% risk weight on credit spreads is large relative to a 100 bp spread level, so the capital charge is a multiple of the CVA itself. Interest rate, FX and equity classes are comparatively small. The multiplier m_CVA is 1 in the framework in force from 2023 (it was 1.25 in the original 2017 text); both are shown." % (top.replace("_", " "), cap[top] / Rc["K_sa_cva"] * 100)))
    add(P("8.5 Assumptions and limitations of the CVA work", H2))
    add(B(["<b>Counterparty ratings are assumed</b> (BBB financials). CVA and the credit-spread capital scale with this assumption; Section 8.3 shows the range.",
           "<b>Spreads are bond-index proxies</b>, not CDS: the maturity shape is common to all ratings, and the indices are US corporate spreads regardless of counterparty region or sector.",
           "<b>Unilateral, independent, uncollateralized.</b> No DVA, no wrong-way risk (exposure and default dependence) and no margin, which MAR50.32 allows to be recognised only where terms are known.",
           "<b>Interest rate risk is USD only:</b> the JPY rate is not simulated, so JPY rate sensitivity is captured through the USD curve; inflation risk factors are omitted (no inflation exposure).",
           "<b>Sensitivities are one-sided bumps</b> from 1,000 Latin Hypercube scenarios with common random numbers, not adjoint sensitivities; vega shifts apply to the volatilities driving the simulated paths (the trades contain no options, so there are no option-pricing volatilities).",
           "<b>Parameters</b> are transcribed from the BIS text (July 2020 revisions); the vega risk weights follow the 100% and 78% values in that text. Regulatory use requires supervisory approval and validation of the sensitivity calculation.",
           "The Basel Basic Approach (BA-CVA) is not computed; it needs only counterparty exposure and maturity and is the natural fallback if SA-CVA approval is not held."]))
    add(PageBreak())

'''
marker = '    add(P("8. Every modelling choice, and what we rejected", H1))'
rep(marker, sec + marker.replace("8. Every", "9. Every"))

# ------------------------------------------------ renumber later sections (do highest first)
rep('add(P("12. Conclusions and recommendations", H1))', 'add(P("13. Conclusions and recommendations", H1))')
rep('add(P("11. Assumptions and limitations", H1))', 'add(P("12. Assumptions and limitations", H1))')
rep('add(P("10. Defects identified and resolved", H1))', 'add(P("11. Defects identified and resolved", H1))')
rep('add(P("9. Validation: how we know the engine is right", H1))', 'add(P("10. Validation: how we know the engine is right", H1))')
for sub in range(6, 0, -1):
    s = s.replace('add(P("9.%d ' % sub, 'add(P("10.%d ' % sub)
open(p, "w", encoding="utf-8").write(s)
print("ok6")
