import re
p = "scripts/build_report.py"
s = open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert a in s, "MISSING: " + a[:100]
    s = s.replace(a, b, 1)


rep('    se3000 = boot[-1]["se99"] * np.sqrt(boot[-1]["N"] / 3000.0)\n',
    '    c_se = float(np.mean([b["se99"] * np.sqrt(b["N"]) for b in boot[2:]]))  # SE(N) = c_se / sqrt(N)\n'
    '    se_at = lambda n_: c_se / np.sqrt(n_)\n    se3000 = se_at(3000)\n')
rep('rows = [["N", "PFE99 (USD)", "Relative SE", "Bias vs 30k pool", "Marginal SE gain", "Est. time", "Verdict"]]',
    'rows = [["N", "PFE99 at 1y (USD)", "Rel. SE at 1y", "Rel. SE at peak date (est.)", "Marginal SE gain (1y)", "Est. time", "Verdict"]]')
rep('rows.append([format(r["N"], ","), format(r["PFE_mean"], ",.0f"), "%.2f%%" % r["relative_se_pct"], "%+.2f%%" % r["bias_vs_pool_pct"],',
    'rows.append([format(r["N"], ","), format(r["PFE_mean"], ",.0f"), "%.2f%%" % r["relative_se_pct"], "%.2f%%" % se_at(r["N"]),')
rep('add(tbl(rows, widths=[0.7, 1.2, 0.9, 1.1, 1.1, 0.8, 2.2]))', 'add(tbl(rows, widths=[0.7, 1.1, 0.9, 1.3, 1.1, 0.8, 2.1]))')
rep('"Tail study (PFE99 of the portfolio at the one-year node, pool value $%s, 30,000 scenarios). Times assume 8 cores." % format(c99["pool_pfe_reference"], ",.0f")',
    '"Tail study at the one-year node (pool value $%s, 30,000 scenarios) and the corresponding estimate at the date of peak PFE99, where the exposure distribution is wider (relative SE = %.1f%% / sqrt(N/1000), fitted to the reporting-run bootstrap). Times assume 8 cores." % (format(c99["pool_pfe_reference"], ",.0f"), se_at(1000))')
s = re.sub(r'    add\(callout\("<b>Decision: number of paths\.</b>.*?adequate for its purpose\." % se3000\)\)\n',
           '''    add(callout("<b>Decision: number of paths.</b> Use <b>N = 5,000</b> for standard PFE99 reporting: relative standard error %.1f%% at the worst-case date (0.29%% at the one-year node), about 8 minutes on 8 cores. Use <b>N = 1,000</b> for iteration and what-if runs (%.1f%% at the worst-case date, about 2 minutes) and <b>N = 10,000</b> when a limit is being signed off (%.1f%%, about 15 minutes). We do not recommend more than 15,000: cost grows linearly while error falls only as 1/sqrt(N), and the remaining sampling error (below %.1f%%) is an order of magnitude smaller than the model sensitivities in Section 9.4 (a 50%% increase in equity volatility moves MPE by more than 10%%). The figures in this report use N = 3,000 (%.1f%% at the worst-case date)." % (se_at(5000), se_at(1000), se_at(10000), se_at(15000), se3000)))
''', s, flags=re.S)
rep('(PFE99 relative standard error about 0.3%), N = 1,000', '(PFE99 relative standard error about 1% at the worst-case date), N = 1,000')
open(p, "w", encoding="utf-8").write(s)

p2 = "scripts/report_tex.py"
t = open(p2, encoding="utf-8").read()
t = t.replace('spec = "".join(f"p{{\\\\dimexpr {w / tot:.4f}\\\\linewidth-2\\\\tabcolsep\\\\relax}}" for w in widths)',
              'spec = "".join(f">{{\\\\raggedright\\\\arraybackslash}}p{{\\\\dimexpr {w / tot:.4f}\\\\linewidth-2\\\\tabcolsep\\\\relax}}" for w in widths)')
t = t.replace("\\usepackage{longtable}", "\\usepackage{array}\n\\usepackage{longtable}")
open(p2, "w", encoding="utf-8").write(t)
print("ok3")
