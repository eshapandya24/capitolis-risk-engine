import re
p = "scripts/build_report.py"
s = open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert a in s, "MISSING: " + a[:80]
    s = s.replace(a, b, 1)


# ---- renumber headings/refs FIRST (highest numbers first) so the new Section 9 does not collide
rep('add(P("13. Conclusions and recommendations", H1))', 'add(P("14. Conclusions and recommendations", H1))')
rep('add(P("12. Assumptions and limitations", H1))', 'add(P("13. Assumptions and limitations", H1))')
rep('add(P("11. Defects identified and resolved", H1))', 'add(P("12. Defects identified and resolved", H1))')
rep('add(P("10. Validation: how we know the engine is right", H1))', 'add(P("11. Validation: how we know the engine is right", H1))')
rep('add(P("9. Every modelling choice, and what we rejected", H1))', 'add(P("10. Every modelling choice, and what we rejected", H1))')
for sub in range(6, 0, -1):
    s = s.replace('add(P("10.%d ' % sub, 'add(P("11.%d ' % sub)
rep("(Section 11). The curve is the starting", "(Section 12). The curve is the starting")
rep("martingale test (Section 10)", "martingale test (Section 11)")
rep("the sensitivity test (Section 10)", "the sensitivity test (Section 11)")
rep("verified in Section 10 by a martingale test", "verified in Section 11 by a martingale test")
rep("model sensitivities in Section 10.4", "model sensitivities in Section 11.4")
rep("(each is justified in Section 9)", "(each is justified in Section 10)")

# ---- module import
rep("from report_lib import GOLD, GREY, NAVY, ORANGE, PAL, TEAL, plt", "import report_greeks as RG\nfrom report_lib import GOLD, GREY, NAVY, ORANGE, PAL, TEAL, plt")

# ---- Section 9 insertion (before the modelling-choices section)
marker = '    add(P("10. Every modelling choice, and what we rejected", H1))'
block = '''    # ---------- 9 Greeks
    g_ = RG.load()
    from run_simulation import load_trades as _lt
    from risk_engine.models.calibration import _isin_to_ticker
    _tr = _lt()
    tickers_ = _isin_to_ticker()
    tm_ = {}
    for tid_, t_ in _tr.items():
        if hasattr(t_, "positions"):
            sign_ = -1.0 if t_.direction == "pay_equity" else 1.0
            tm_[tid_] = {}
            for p_ in t_.positions:
                s_ = calib["equity_spots"][p_.isin] / (calib["fx_spot"] if p_.currency == "JPY" else 1.0)
                tm_[tid_][p_.isin] = sign_ * p_.shares * s_ * 0.01
    RG.section(add, doc, g_, tickers_, tm_)

'''
rep(marker, block + marker)

# ---- abstract / summary
rep("and computes the Basel SA-CVA capital requirement. The report sets out", "computes the Basel SA-CVA capital requirement, and provides the full set of sensitivities (Greeks) of the book and of the exposure measures. The report sets out")
rep('             ["CVA (BBB proxy)",', '             ["Greeks", "t = 0 book Greeks; sensitivities of EE, median PFE and PFE99 to equities, USDJPY, USD rates and volatilities", "Complete, by netting set (Section 9)"],\n             ["CVA (BBB proxy)",')
# ---- glossary, register, code map, tests
rep('["CVA", "Credit valuation adjustment', '["Delta, gamma", "First and second sensitivity of a value or exposure measure to a market factor (here per +1% spot, per +1bp rate)"],\n             ["DV01", "Change in value for a +1bp move of the interest rate curve, parallel or by tenor bucket"],\n             ["Vega", "Sensitivity to volatility (here per +1% relative shift)"],\n             ["CVA", "Credit valuation adjustment')
rep('             ["Precision", "Bootstrap resampling', '             ["Greeks", "Bump-and-reprice with common random numbers; equity and FX bumps reuse paths (exact GBM rescaling, subset repricing); rate and vol bumps re-simulate", "+1% spot, +1bp rates (parallel and 8 buckets), +1% vol; N = 2,000", "greeks/book.py, greeks/exposure.py, scripts/run_greeks.py"],\n             ["Precision", "Bootstrap resampling')
rep('["exposure/", "aggregate', '["greeks/", "book (t=0 Greeks by trade and netting set), exposure (sensitivities of EE, median PFE, PFE99), bumps (curve and parameter bump helpers)"],\n             ["exposure/", "aggregate')
s = s.replace("76 automated tests", "82 automated tests").replace("76 tests", "82 tests")
rep("median PFE, CVA and the SA-CVA aggregation, and the credit-spread proxy curves.", "median PFE, CVA and the SA-CVA aggregation, the credit-spread proxy curves, and the Greeks machinery (bump helpers, t=0 Greeks against analytic values, exposure measures).")
rep('"python scripts/run_sa_cva.py --scenarios 1000             # CVA and SA-CVA capital (21 runs)\\n"', '"python scripts/run_sa_cva.py --scenarios 1000             # CVA and SA-CVA capital (21 runs)\\n"\n             "python scripts/run_greeks.py --scenarios 2000             # book and exposure Greeks (about 75 min)\\n"')
# ---- conclusions: replace the PFE-Greeks next step, add a Greeks bullet
s = s.replace("; PFE Greeks (d PFE / d spot) using common random numbers", "")
rep('"We recommend confirming with Capitolis whether any trade is margined', 'f"Greeks are complete for the book and for the exposure measures (Section 9): PFE99 at its peak date falls by about ${abs(g_[\'equity_all\'][\'delta\'][\'__portfolio__\'][\'PFE\'][RG.peak_node(g_)])/1e3:,.0f}k per +1% on all equities and rises by about ${g_[\'rate_parallel\'][\'delta\'][\'__portfolio__\'][\'PFE\'][RG.peak_node(g_)]/1e3:,.0f}k per +1bp on USD rates.",\n           "We recommend confirming with Capitolis whether any trade is margined')
open(p, "w", encoding="utf-8").write(s)

d = open("scripts/build_exec_deck.py", encoding="utf-8").read()
d = d.replace("Next: wire JPY factor into the drift, PFE Greeks, two-factor rate model", "Next: wire JPY factor into the drift, two-factor rate model")
marker = '    S += [P("Assumptions, limits, next steps", TITLE)]'
new = '''    import report_greeks as RG
    g_ = RG.load()
    jpk = RG.peak_node(g_)
    S += [P("Greeks: book and exposure sensitivities", TITLE), fig(RG.fig_profiles(g_), 2.4 * inch)]
    S += bl(["Complete set, by netting set: t=0 delta, gamma, DV01 (parallel and 8 buckets), FX; and the sensitivities of EE, median PFE and PFE99 to all 37 equities, USDJPY, USD rates and volatilities.",
             "At peak PFE99 (%s): +1%% on all equities moves PFE99 by $%sk and EE by $%sk (pay-equity swaps: falling shares raise our claim); +1bp on USD rates moves PFE99 by +$%sk." % (
                 g_["dates"][jpk], format(g_["equity_all"]["delta"]["__portfolio__"]["PFE"][jpk] / 1e3, ",.0f"), format(g_["equity_all"]["delta"]["__portfolio__"]["EE"][jpk] / 1e3, ",.0f"), format(g_["rate_parallel"]["delta"]["__portfolio__"]["PFE"][jpk] / 1e3, ",.0f")),
             "Method: bump-and-reprice with common random numbers; equity and FX bumps reuse the simulated paths (exact GBM rescaling, only affected trades repriced), so 82 bumps cost a fraction of re-simulation.",
             "Validated against analytic t=0 deltas, bump-size stability, additivity of single-name deltas, and common random numbers versus independent draws."])
    S.append(PageBreak())

'''
d = d.replace(marker, new + marker)
open("scripts/build_exec_deck.py", "w", encoding="utf-8").write(d)
print("ok10")
