p = "scripts/report_new2.py"
s = open(p, encoding="utf-8").read()
i = s.index('    out.append(P("Rank correlations of the counterparty exposures at that date:')
j = s.index('    rows = [["Rate-equity dependence assumed"')
new = '''    eqd, dvd = d["equity_delta_per_1pct"], d["dv01_per_bp"]
    out.append(P("Rank correlations of the counterparty exposures at that date: A-B %+.2f, A-C %+.2f, B-C %+.2f. Probability that one counterparty is above its own 99th percentile given another is: A given B %.0f%%, A given C %.0f%%, C given B %.0f%% (an independent pair would give 1%%). All three exposures are positively dependent, for a common reason: every netting set holds pay-equity swaps (equity delta per +1%%: A %s, B %s, C %s), so all three gain when the equity market falls. CPTY_C is therefore not a pure interest-rate netting set: its DV01 of %s per bp is dominated by BF_0003, but it also carries an equity delta comparable to CPTY_B's. The dependence is moderate rather than strong, which is why the portfolio 99th percentile sits at %.0f%% of the sum of the standalone ones and not lower." % (rc["CPTY_A-CPTY_B"], rc["CPTY_A-CPTY_C"], rc["CPTY_B-CPTY_C"], tc["CPTY_A|CPTY_B"] * 100, tc["CPTY_A|CPTY_C"] * 100, tc["CPTY_C|CPTY_B"] * 100, _m(eqd["CPTY_A"]), _m(eqd["CPTY_B"]), _m(eqd["CPTY_C"]), _k(dvd["CPTY_C"]), at["portfolio"] / ssum * 100)))
    a_, b_, c_ = at["pfe99"]["CPTY_A"], at["pfe99"]["CPTY_B"], at["pfe99"]["CPTY_C"]
    out.append(P("<b>Which pair is the portfolio close to?</b> At that date the standalone PFE99 are A %s, B %s and C %s: the two large ones, A and C, sum to %s (%.0f%% of the portfolio figure %s), and B adds the rest. The portfolio figure is therefore close to the sum of A and C, with B small, not to the sum of A and B." % (_m(a_), _m(b_), _m(c_), _m(a_ + c_), (a_ + c_) / at["portfolio"] * 100, _m(at["portfolio"]))))
'''
s = s[:i] + new + s[j:]
open(p, "w", encoding="utf-8").write(s)
print("ok")
