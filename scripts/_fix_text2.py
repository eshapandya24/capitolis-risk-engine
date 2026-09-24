p = "scripts/report_new2.py"
s = open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert a in s, a[:80]
    s = s.replace(a, b, 1)


# ---- pathwise validation keys
rep('''against %.0f seconds for the %d bump-and-reprice runs. Against those bump results, on the same scenarios:" % (V["pathwise_seconds"], V["bump_seconds"]["equity_fx_bumps_s"] or tc["subset_bumps_s"], V["bump_seconds"]["n_equity_fx_bumps"] or nb_fx)))''',
    '''against %.0f seconds for the %d bump-and-reprice runs. Compared on the same paths and NPVs, so that both see identical inputs:" % (V["pathwise_seconds"], V["bump_seconds"], V["n_bumps"])))''')
rep('''Differences are the maximum over reporting dates as a percentage of the peak absolute delta. EE matches (the estimators are algebraically the same up to the kink at zero); the median and PFE99 pathwise deltas are local averages over a few dozen scenarios and are therefore noisier, which is why the bump-and-reprice values remain the reported ones and pathwise is used as an independent check and as the fast path for equity and FX. The remaining cost is the rate and volatility bumps, which no pathwise formula covers here.''',
    '''Differences are the maximum over reporting dates, as a percentage of the largest single-name delta of the same netting set and measure. The EE deltas agree to numerical precision (the two estimators are algebraically the same up to the kink at zero); the median and PFE99 pathwise deltas are local averages over a few dozen scenarios and are noisier, which is why the bump-and-reprice values remain the reported ones and pathwise is the independent check and the fast path for equity and FX. The remaining cost is the rate and volatility bumps, which no pathwise formula covers here.''')

# ---- PCA: readings, speed and sampling conclusions written from the measured results
rep('''        if f["index"] == 1:
            rd = "Market factor: all names, both regions"
        elif abs(us - jp) > 0.25:
            rd = "Japan versus US"
        else:
            rd = "A group of names (see the extremes)"''',
    '''        tops = {a for a, _ in f["top_positive"][:4]} | {a for a, _ in f["top_negative"][:4]}
        if f["index"] == 1:
            rd = "Market factor: all names, both regions"
        elif abs(us - jp) > 0.25:
            rd = "Japan versus US"
        elif {"KO", "PG"} & tops:
            rd = "Defensive staples against high-growth technology and power names"
        elif {"MPC", "XOM"} & tops:
            rd = "Energy and the USD rate against the Indian ADRs"
        else:
            rd = "A group of growth and financial names (see the extremes)"''')
rep('''"%.3f%%" % (sp[mode]["draws_s"] / dr * 100) if dr else "n/a"])''', '''"%.3f%%" % (sp[mode]["draws_s"] / dr * 100) if dr else "n/a"])''')
rep('''str(sp[mode]["n_factors"] + (0 if mode == "full" else int(mode[3:])))''', '''str(sp["full"]["n_factors"] + (0 if mode == "full" else int(mode[3:])))''')
i = s.index('    out.append(P("<b>How much speed does it add?</b>')
j = s.index('    S = R["sampling"]')
new = '''    out.append(P("<b>How much speed does it add?</b> None, and slightly the opposite. The factor model replaces a 40x40 matrix product per step with a 40x5 one plus independent noise, but the engine then has to draw k systematic and 40 idiosyncratic normals per step instead of 40, and the measured time of the correlated-shock step is not lower (%s). In any case that step is a vanishing part of the run, which is dominated by repricing every trade at every node (%s for 5,000 scenarios on the close-out grid):" % (", ".join("%s %.2f s" % (lab, sp[mode]["draws_s"]) for mode, lab in (("full", "full"), ("pca5", "5 factors"), ("pca10", "10 factors"))), "%.0f s" % dr if dr else "about 35 minutes")))
    out.append(tbl(rows, widths=[1.6, 1.6, 2.6, 1.6], font=7.4))
    out.append(P("The correlated-shock step is %.2f s (full) against %.2f s (5 factors) in a run of %s, so the end-to-end speed added is nil; whichever is faster, the difference is under 0.1%% of the run." % (full, p5, "%.0f s" % dr if dr else "roughly 35 minutes")))
'''
s = s[:i] + new + s[j:]
rep('''out.append(callout("Conclusion: the PCA factor model is explainable (a market factor, a Japan-versus-US factor and group factors) but it approximates the correlation matrix, it does not speed up the run, and it does not reduce sampling error in its present form. The full-rank Cholesky remains the default; the factor model is kept as a robustness option, and would become useful only if the systematic factors alone were drawn quasi-randomly and the idiosyncratic noise pseudo-randomly."))''',
    '''out.append(callout("Conclusion: the PCA factor model is explainable (a market factor, a Japan-versus-US factor and group factors) but it approximates the correlation matrix (the volatility of a netting set differs from the full matrix by several percent), it adds no speed, and its sampling error is not consistently lower than the full-rank model's (it varies with the number of factors and the netting set). The full-rank Cholesky remains the default; the factor model is kept as a robustness option, and would become useful only if the systematic factors alone were drawn quasi-randomly and the idiosyncratic noise pseudo-randomly."))''')

# ---- stress finding (4)
i = s.index("(4) Combined scenarios are not the sum of their parts")
j = s.index('return out, R', i)
new4 = '''(4) Combined scenarios show how the pieces interact: the flight-to-quality and stagflation scenarios apply the same equity shock with opposite rate shocks. In both, CPTY_A and CPTY_B fall by about the same amount (their positions are smaller after the equity fall), but CPTY_C rises with the fall in yields (a 22-year bond has more duration at lower yields) and falls with the rise, so the portfolio close-out MPE99 is %s in flight to quality and %s in stagflation, against %s in the base." % (port_co[wco] * 100, SHORT.get(wco, wco), port_lv[wlv] * 100, SHORT.get(wlv, wlv), n_valid, min(n_trade_moves.values()), max(n_trade_moves.values()), _m(sc["FLIGHT_TO_QUALITY"]["closeout"]["__portfolio__"]["MPE"]), _m(sc["STAGFLATION"]["closeout"]["__portfolio__"]["MPE"]), _m(base["closeout"]["__portfolio__"]["MPE"]))))
    '''
seg = s[i:j]
k = seg.index('" % (port_co[wco]')
s = s[:i] + new4 + s[j:]
open(p, "w", encoding="utf-8").write(s)
print("ok")
