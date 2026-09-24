"""Text corrections found while checking the generated report against the result files."""
import sys
sys.path.insert(0, "scripts")
from _patchlib import Patcher


def edit(path, pairs):
    s = open(path, encoding="utf-8").read()
    for a, b in pairs:
        assert a in s, (path, a[:80])
        s = s.replace(a, b, 1)
    open(path, "w", encoding="utf-8").write(s)


# ------------------------------------------------------------------ report_new: number formats
# ------------------------------------------------------------------ report_new2
edit("scripts/report_new2.py", [
    # additivity: which factor drives each set
    ('''        parts = []
        if e < -1e4:
            parts.append("equities fall")
        if e > 1e4:
            parts.append("equities rise")
        if r > 1e3:
            parts.append("yields rise")
        if r < -1e3:
            parts.append("yields fall")
        txt[c] = " and ".join(parts) or "little"''', '''        parts = []
        big_e = max(abs(v) for v in d["equity_delta_per_1pct"].values())
        big_r = max(abs(v) for v in d["dv01_per_bp"].values())
        fxv = d["fx_delta_per_1pct"][c]
        if abs(e) > 0.1 * big_e:
            parts.append("equities fall" if e < 0 else "equities rise")
        if abs(r) > 0.1 * big_r:
            parts.append("yields rise" if r > 0 else "yields fall")
        if abs(fxv) > 1e5:
            parts.append("USDJPY rises (yen weakens)" if fxv > 0 else "USDJPY falls (yen strengthens)")
        txt[c] = " and ".join(parts) or "little"'''),
    ('''The peak dates of the individual counterparties fall within days of each other (%s) because all three books are largest in the first weeks, before the equity swaps mature, so there is little timing diversification." % (A["portfolio_mpe_date"]''',
     '''The peak dates of the individual counterparties (%s) fall within about %d days of each other because all three books are largest in the first weeks, before the equity swaps mature, so there is little timing diversification." % (A["portfolio_mpe_date"]'''),
    ('''_m(ssum), _m(at["portfolio"]), at["portfolio"] / ssum * 100, (1 - at["portfolio"] / ssum) * 100, ", ".join("%s %s" % (c[-1], A["mpe_date"][c]) for c in CP))))''',
     '''_m(ssum), _m(at["portfolio"]), at["portfolio"] / ssum * 100, (1 - at["portfolio"] / ssum) * 100, ", ".join("%s %s" % (c[-1], A["mpe_date"][c]) for c in CP), (max(date.fromisoformat(v) for v in A["mpe_date"].values()) - min(date.fromisoformat(v) for v in A["mpe_date"].values())).days)))'''),
    ("the sensitivity of the total to the rating is in the table of Section 8.1)", "the sensitivity of the total to the rating is in the table of Section 8.3)"),
    # greeks method text
    ("(%.0fx lower, equivalent to about %.0fx more scenarios).\" % (_k(crn[\"crn_std\"]), _k(crn[\"independent_std\"]), ratio, ratio ** 2))",
     "(%.0fx lower).\" % (_k(crn[\"crn_std\"]), _k(crn[\"independent_std\"]), ratio))"),
    # stress path claim
    ("(3) Along the path, the effect is strongest at the dates where the shocked positions are still alive and fades as trades mature; the ratio plot shows the dates at which each scenario bites. (4)",
     "(3) Along the path the effect follows the life of the positions that carry the shocked factor: for the rates -200bp scenario the ratio of portfolio close-out PFE99 to the base rises to %.2f (at about day %d) and is back near %.2f once BF_0003 settles on 6 December 2026, whereas the equity scenarios keep their constant scaling (%.2f for -30%%) while the baskets are alive. (4)"),
])
s = open("scripts/report_new2.py", encoding="utf-8").read()
# add the computed values to the format arguments of the stress findings paragraph
a = "(port_co[wco] * 100, SHORT.get(wco, wco), port_lv[wlv] * 100, SHORT.get(wlv, wlv), n_valid, min(n_trade_moves.values()), max(n_trade_moves.values()), _m(sc[\"FLIGHT_TO_QUALITY\"]"
assert a in s
b = "(port_co[wco] * 100, SHORT.get(wco, wco), port_lv[wlv] * 100, SHORT.get(wlv, wlv), n_valid, min(n_trade_moves.values()), max(n_trade_moves.values()), _rd_max, _rd_day, _rd_after, _eq_ratio, _m(sc[\"FLIGHT_TO_QUALITY\"]"
s = s.replace(a, b, 1)
a = "    wco = max(port_co, key=lambda n: abs(port_co[n]))"
assert a in s
b = '''    _rb = np.array(base["closeout"]["__portfolio__"]["PFE"])
    _rr = np.array(sc["RATES_DOWN_200"]["closeout"]["__portfolio__"]["PFE"]) / np.maximum(_rb, 1.0)
    _kk = np.where(keep)[0]
    _jm = _kk[int(np.argmax(_rr[_kk]))]
    _rd_max, _rd_day = float(_rr[_jm]), int(days[_jm])
    _after = [i for i in _kk if days[i] > 105 and _rb[i] > 1e5]
    _rd_after = float(np.median(_rr[_after])) if _after else float("nan")
    _eq_ratio = float(np.median((np.array(sc["EQ_DOWN_30"]["closeout"]["__portfolio__"]["PFE"]) / np.maximum(_rb, 1.0))[[i for i in _kk if days[i] < 60]]))
''' + a
s = s.replace(a, b, 1)
# the format string for that paragraph has 7 + 3 arguments; add 4 numeric ones in the right place: the new text has
# four extra placeholders before the three flight/stagflation/base placeholders
open("scripts/report_new2.py", "w", encoding="utf-8").write(s)

# ------------------------------------------------------------------ CVA walk-through: show selected dates spread over the life
s = open("scripts/report_new2.py", encoding="utf-8").read()
a = "        keep = [i for i in range(1, len(t)) if contrib[i - 1] > 0.02 * contrib.max()][:14]"
assert a in s
b = "        targets = [0.0, 0.04, 0.08, 0.16, 0.25, 0.33, 0.42, 0.5, 0.58, 0.67, 0.75, 1.0, 1.25, float(t[-1])]\n        keep = sorted({int(np.argmin(np.abs(t[1:] - x))) + 1 for x in targets})"
s = s.replace(a, b, 1)
s = s.replace("The rows with the largest contributions; the last row sums all intervals:", "Selected dates spread over the life of the book; the last row sums all intervals:")
open("scripts/report_new2.py", "w", encoding="utf-8").write(s)

# ------------------------------------------------------------------ report_greeks
edit("scripts/report_greeks.py", [
    ("12 are needed: parallel up and down, 8 buckets, three vega bumps", "13 are needed: parallel up and down, 8 buckets, three vega bumps"),
])
s = open("scripts/report_greeks.py", encoding="utf-8").read()
i = s.index('add(P("Timings were measured separately at N = %d')
j = s.index("\n    add(", i + 10)
s = s[:i] + 'add(P("The timings in the table were measured on an otherwise idle machine at N = %d, because the production run shared the machine with other jobs; costs scale about linearly with N once process start-up is amortised." % tc["n"]))' + s[j:]
open("scripts/report_greeks.py", "w", encoding="utf-8").write(s)

# ------------------------------------------------------------------ build_report
p = Patcher("scripts/build_report.py")
p.sub('"CPTY_B": "We owe them: zero exposure"', '"CPTY_B": "Small positive net"')
p.sub("trading roughly 20 points below par", "trading roughly 25 points below par")
p.sub("it changes the answer by roughly an order of magnitude for CPTY_C.", "it changes the answer several-fold for CPTY_C.")
p.sub('f"Same seed and method ({ncmp:,} scenarios) with the full Cholesky correlation versus a k-factor PCA model. Curves coincide closely from k=5."',
      'f"Uncollateralized level exposure, same seed and method ({ncmp:,} scenarios), with the full Cholesky correlation versus a k-factor PCA model. Curves coincide closely from k=5."')
p.sub('add(P("11.4 Sensitivity (stress) test", H2))', 'add(P("11.4 Stress and sensitivity tests", H2))')
p.replace('add(P("<b>EE, median PFE and PFE99.</b>', '''
_pk = {c: (per[c]["MED"].max(), per[c]["EE"].max()) for c in per}
add(P("<b>EE, median PFE and PFE99.</b> On the uncollateralized level exposure the peak median PFE is %.0f%%, %.0f%% and %.0f%% of the peak EE for CPTY_A, CPTY_B and CPTY_C. Where the two are close (CPTY_C) the exposure is a large mark-to-market that is positive in almost every scenario; where the median is well below EE (CPTY_B) the counterparty is out of the money in many scenarios and EE is pulled up by the right tail. The median PFE describes the typical outcome and PFE99 the adverse tail; reporting all three prevents any single statistic from misleading." % (_pk["CPTY_A"][0] / _pk["CPTY_A"][1] * 100, _pk["CPTY_B"][0] / _pk["CPTY_B"][1] * 100, _pk["CPTY_C"][0] / _pk["CPTY_C"][1] * 100)))
''')
p.replace('add(P("<b>Reading the table.</b> On the margined close-out exposure', '''
add(P("<b>Reading the table.</b> On the margined close-out exposure the total CVA is %s and DVA %s, so the net credit charge is %s; funding costs %s (FCA %s less FBA %s). On the close-out definition the positive and negative sides are nearly symmetric, because both are 10-day moves around a margined start, so CVA and DVA almost cancel and the funding terms are small. On the level exposure CVA is %s and DVA %s: the difference from the close-out figures is the whole mark-to-market that margin would otherwise cover, and the asymmetry comes from the book being mostly in our favour (CPTY_C's bond forward), which makes the positive exposure, and therefore CVA and FCA, much larger than the negative exposure that drives DVA and FBA." % (RN._k(_c["CVA"]), RN._k(_c["DVA"]), RN._k(_c["CVA"] - _c["DVA"]), RN._k(_c["FVA"]), RN._k(_c["FCA"]), RN._k(_c["FBA"]), RN._k(_l["CVA"]), RN._k(_l["DVA"]))))
''')
p.save()
print("13g done")
