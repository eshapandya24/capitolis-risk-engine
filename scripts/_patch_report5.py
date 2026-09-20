import re
p = "scripts/build_report.py"
s = open(p, encoding="utf-8").read()
i = s.index("    fg, opt, real = fig_vr()")
j = s.index("    add(PageBreak())\n\n    add(P(\"5.5 Number of scenarios\", H2))")
new = '''    fg, opt, real = fig_vr()
    rel99 = {k: real[k]["std"] / real[k]["mean"] * 100 for k in real}
    rel50 = {k: real[k]["med_std"] / real[k]["med_mean"] * 100 for k in real}
    add(doc.figure(fg, "Left: on a European call with a known Black-Scholes value, Latin Hypercube has about %.0fx lower error than pseudo-random. Right: on the real 663-dimensional engine (300 scenarios, 8 repeats) the methods are much closer, and no method is best for both PFE99 and the median PFE." % (opt["pseudo_random"]["rmse"] / opt["latin_hypercube"]["rmse"])))
    verdicts = {"pseudo_random": "Baseline",
                "antithetic": "Improves both measures modestly on the real engine, but only 1.4x on the controlled test",
                "moment_matched": "Helps the median only; no PFE99 benefit",
                "sobol": "Best PFE99 on the real engine but no median benefit; unscrambled Sobol degrades in high dimension and is harder to replicate",
                "latin_hypercube": "SELECTED: 50x on the controlled test and improves both PFE99 and median PFE on the real engine"}
    rows = [["Method", "Call RMSE", "vs pseudo-random", "PFE99 rel. std (real engine)", "Median PFE rel. std (real engine)", "Verdict"]]
    for k in opt:
        rows.append([k.replace("_", " "), "%.4f" % opt[k]["rmse"], "%.1fx better" % (opt["pseudo_random"]["rmse"] / opt[k]["rmse"]) if k != "pseudo_random" else "-",
                     "%.2f%% (%.2fx)" % (rel99[k], rel99["pseudo_random"] / rel99[k]), "%.2f%% (%.2fx)" % (rel50[k], rel50["pseudo_random"] / rel50[k]), verdicts[k]])
    add(tbl(rows, widths=[1.2, 0.8, 1.0, 1.4, 1.5, 3.0]))
    add(P("Relative standard deviation of the estimator across 8 independent repeats at 300 scenarios (portfolio, about 6 weeks out, near the PFE99 peak); the multiple in brackets is the improvement over pseudo-random. With only 8 repeats each standard deviation is itself uncertain by roughly a quarter, so real-engine differences between the better methods are indicative rather than conclusive.", SMALL))
    add(P("<b>Finding.</b> The controlled test gives a clear ordering (Latin Hypercube, Sobol, moment matching, antithetic, pseudo-random). On the real engine, at 663 effective dimensions (39 factors x 17 time steps), the advantages compress and the ranking depends on the statistic: the tail (PFE99) and the centre (median PFE) respond to different methods. Latin Hypercube is the only method that is both best on the controlled test and better than pseudo-random on both real-engine statistics."))
    add(callout("<b>Decision: Latin Hypercube sampling.</b> It is the best method on the controlled test and the most consistent across both reported statistics on the real engine, at negligible additional cost over plain pseudo-random draws. Sobol is the runner-up on the controlled test but is not recommended here because its benefit disappears for the median PFE and it is less robust at this dimensionality."))
'''
s = s[:i] + new + s[j:]
open(p, "w", encoding="utf-8").write(s)

p = "scripts/build_exec_deck.py"
d = open(p, encoding="utf-8").read()
a = d.index('    S += bl(["Decision: Latin Hypercube sampling')
b = d.index('             "Decision: 5,000 paths')
d = d[:a] + '''    rr = vr["real_engine_check"]
    S += bl(["Decision: Latin Hypercube sampling: %.0fx lower error than pseudo-random on the controlled test, and better on both PFE99 (%.2fx) and median PFE (%.2fx) on the real engine." % (
                 vr["option_study"]["results"]["pseudo_random"]["rmse"] / vr["option_study"]["results"]["latin_hypercube"]["rmse"],
                 (rr["pseudo_random"]["std"] / rr["pseudo_random"]["mean"]) / (rr["latin_hypercube"]["std"] / rr["latin_hypercube"]["mean"]),
                 (rr["pseudo_random"]["med_std"] / rr["pseudo_random"]["med_mean"]) / (rr["latin_hypercube"]["med_std"] / rr["latin_hypercube"]["med_mean"])),
''' + d[b:]
open(p, "w", encoding="utf-8").write(d)
print("ok5")
