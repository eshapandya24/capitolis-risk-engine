import re
p = "scripts/build_report.py"
s = open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert a in s, "MISSING: " + a[:80]
    s = s.replace(a, b, 1)


# ---- A. fig_jgb_vol -> two panels (JGB public, JPY OIS licensed: derived stats only)
i = s.index("def fig_jgb_vol():")
j = s.index("\ndef fig_hw_fit")
new = '''def fig_jgb_vol():
    from risk_engine.market.mof_jgb import fetch_jgb_yield_history, TENOR_COLUMNS
    from risk_engine.market import jpy_ois
    y = fetch_jgb_yield_history()
    ten = {"1Y": 1, "2Y": 2, "3Y": 3, "4Y": 4, "5Y": 5, "6Y": 6, "7Y": 7, "8Y": 8, "9Y": 9, "10Y": 10,
           "15Y": 15, "20Y": 20, "25Y": 25, "30Y": 30, "40Y": 40}
    fig, ax = plt.subplots(1, 2, figsize=(7.4, 2.7), sharey=True)
    end = y.index.max()
    for yrs, c in ((1, ORANGE), (3, NAVY), (10, TEAL)):
        w = y[(y.index > end - pd.DateOffset(years=yrs)) & (y.index <= end)]
        xs, vs = [], []
        for col in TENOR_COLUMNS:
            d = w[col].dropna().diff().dropna()
            if len(d) > 30:
                xs.append(ten[col]); vs.append(d.std() * np.sqrt(252) * 1e4)
        ax[0].plot(xs, vs, marker="o", ms=3, color=c, label="%dy window" % yrs)
        v = jpy_ois.realized_vol_by_tenor(date(2026, 8, 28), yrs)
        ax[1].plot(list(v), [x * 1e4 for x in v.values()], marker="o", ms=3, color=c, label="%dy window" % yrs)
    ax[0].set_title("JGB par yields (Ministry of Finance)"); ax[1].set_title("JPY OIS par rates (daily history)")
    for a_ in ax:
        a_.set_xlabel("tenor (years)")
    ax[0].set_ylabel("realised normal vol (bp/yr)"); ax[0].legend()
    return fig

'''
s = s[:i] + new + s[j:]

# ---- B. fig_hw_fit: add the OIS-history bar
rep(r'    labs = ["futures proxy\n(USD)", "swaption cube\n(USD)", "swaption cube\n(JPY)", "JGB yields\n(JPY)"]', r'    labs = ["futures\nUSD", "swaption\nUSD", "swaption\nJPY", "JGB\nJPY", "OIS hist.\nJPY"]')
rep("    vals = [h[\"a\"], sw[\"a\"], sj[\"a\"], jg[\"a\"]]\n    ax[1].bar(range(4), vals, color=[NAVY, TEAL, ORANGE, ORANGE])",
    "    from risk_engine.models.hw_calibration import calibrate_jpy_mean_reversion_from_ois\n    oi = calibrate_jpy_mean_reversion_from_ois(date(2026, 8, 28))\n    vals = [h[\"a\"], sw[\"a\"], sj[\"a\"], jg[\"a\"], oi[\"a\"]]\n    ax[1].bar(range(5), vals, color=[NAVY, TEAL, ORANGE, ORANGE, ORANGE])")
rep("    ax[1].set_xticks(range(4)); ax[1].set_xticklabels(labs, fontsize=6.5)", "    ax[1].set_xticks(range(5)); ax[1].set_xticklabels(labs, fontsize=6.5)")
rep("    return fig, h, sw, sj, jg", "    return fig, h, sw, sj, jg, oi")
rep("fg, h, sw, sj, jg = fig_hw_fit(calib)", "fg, h, sw, sj, jg, oi = fig_hw_fit(calib)")
rep('             ["JGB yield vol, JPY", "MOF daily 1Y-30Y yields, 3y window", "%.4f" % jg["a"], "%.2f" % jg["r_squared"], "invalid (vol rises with tenor)"]],',
    '             ["JGB yield vol, JPY", "MOF daily 1Y-30Y yields, 3y window", "%.4f" % jg["a"], "%.2f" % jg["r_squared"], "invalid (vol rises with tenor)"],\n             ["JPY OIS history, JPY (most complete)", "Daily OIS par rates, 35 tenors, 2011-2026, 1Y-30Y vols, 3y window", "%.4f" % oi["a"], "%.2f" % oi["r_squared"], "invalid (vol rises with tenor); lower bound a = 0.001 used"]],')
rep('Route", "Data", "a", "R2", "Verdict"]', 'Route", "Data", "a", "R2", "Verdict"]') if False else None
rep("Left: USD SOFR-futures fit. Right: fitted a for each route. USD routes give sensible positive values; both JPY routes give a NEGATIVE a.",
    "Left: USD SOFR-futures fit. Right: fitted a for each route. USD routes give sensible positive values; all three JPY routes give a NEGATIVE a.")

# ---- C. Section 6.2 text
rep('add(doc.figure(fj, "Real realised JGB yield vol by tenor. At every window tried (1y, 3y, 10y) long tenors are MORE volatile than short ones, the reverse of the decay Hull-White assumes."))',
    'add(doc.figure(fj, "Realised volatility of JPY rates by tenor from two independent real datasets. At every window tried (1y, 3y, 10y) long tenors are MORE volatile than short ones, the reverse of the decay Hull-White assumes."))')
i = s.index('    add(P("This is not bad data; it is a structural finding confirmed by two independent real sources')
j = s.index('    add(P("<b>Practical impact:</b> small.')
new = '''    add(P("This is not bad data; it is a structural finding confirmed by three independent real sources: the daily JPY OIS curve history (35 tenors, 2011 to 2026, provided by the project team and the most complete of the three), 52 years of JGB yields, and a 2026 swaption cube. The fitted a is negative for the OIS history in every window tested (1, 3, 5, 10 and 15 years, and since the end of negative rates in March 2024). One factor, the level, explains about 84%% of daily changes in the curve, and long rates move more than short rates. The plausible reason is that for two decades the Bank of Japan pinned the SHORT end (zero and negative policy rates, yield-curve control), so short-tenor volatility was suppressed while longer tenors moved more freely. A single mean-reverting Gaussian factor implies volatility that DEcreases with tenor, so it cannot represent this shape, and a negative a would make the short rate diverge."))
    add(P("<b>Choice:</b> use the lowest admissible mean reversion, a = %.4f, the Ho-Lee limit in which volatility is flat across tenors. This is the closest a Gaussian factor can get to the data, and it replaces our earlier use of the USD value. A two-factor or regime-dependent model would be needed to match the shape, and is listed under future work." % meta["hw_jpy"]["a"]))
'''
s = s[:i] + new + s[j:]
rep('"Mean reversion: a = 0.0167 for USD from the swaption cube; JPY reuses the USD value because real JPY volatility rises with tenor (two independent sources).",',
    '"Mean reversion: a = 0.0167 for USD from the swaption cube; for JPY the lower bound a = 0.001, because real JPY volatility rises with tenor (three independent sources, including the full daily OIS history).",')

# ---- D. 4.5 table
rep('["Curve", "Real JPY OIS zero curve", "Bloomberg snapshot 2026-08-31"],', '["Curve", "JPY OIS zero curve, 2026-08-28", "Bootstrapped from the daily JPY OIS par history (project-team Bloomberg file); matches Bloomberg\'s own zero curve to within 1bp at all tenors"],')
rep('"REALISED TONA vol, 3y window: real Bank of Japan data (replaces an earlier swaption-implied 0.400%)"]', '"Realised vol of the overnight call rate, 3y window, from the same OIS file (Bank of Japan TONA gives 0.276%, consistent)"]')
rep('"Fallback to the USD value: both real JPY calibrations gave a negative a (Section 6.2)"]', '"Lower bound: all three real JPY calibrations gave a negative a (Section 6.2)"]')
rep('(%.2f%%, from real Bloomberg curves)"', '(%.2f%%, our USD curve minus the JPY OIS zero curve at one year)"')

open(p, "w", encoding="utf-8").write(s)
print("ok8")
