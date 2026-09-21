import re
p = "scripts/build_report.py"
s = open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert a in s, "MISSING: " + a[:90]
    s = s.replace(a, b, 1)


# ---------------------------------------------------------------- helpers before main()
helpers = '''
def load_spec():
    return json.load(open(os.path.join(PROC, "spec_run", "spec_exposure.json")))


def spec_year_mask(S_):
    ref = date.fromisoformat(S_["ref_date"])
    return np.array([(date.fromisoformat(d) - ref).days <= 365 for d in S_["reporting_dates"]])


def spec_peaks(S_, entity):
    """Peak EE, peak median PFE, MPE99 (all within one year) and their dates."""
    mk = spec_year_mask(S_)
    e = S_["by_counterparty"][entity]
    ee, md, pf = np.array(e["EE"]), np.array(e["MedianExposure"]), np.array(e["PFE"])
    idx = np.where(mk)[0]
    return {"EE": ee[idx].max(), "EE_date": S_["reporting_dates"][idx[int(ee[idx].argmax())]],
            "MED": md[idx].max(), "PFE": pf[idx].max(), "PFE_date": S_["reporting_dates"][idx[int(pf[idx].argmax())]]}


def fig_spec_profiles(S_):
    ref = date.fromisoformat(S_["ref_date"])
    x = np.array([(date.fromisoformat(d) - ref).days for d in S_["reporting_dates"]])
    mk = x <= 365
    fig, axs = plt.subplots(2, 2, figsize=(7.2, 5.0))
    for ax, c in zip(axs.ravel(), ["CPTY_A", "CPTY_B", "CPTY_C", "__portfolio__"]):
        e = S_["by_counterparty"][c]
        ax.plot(x[mk], np.array(e["PFE"])[mk] / 1e6, color="#8B0000", lw=1.6, label="PFE99")
        ax.plot(x[mk], np.array(e["EE"])[mk] / 1e6, color=NAVY, lw=1.8, label="EE")
        ax.plot(x[mk], np.array(e["MedianExposure"])[mk] / 1e6, color=GOLD, lw=1.8, label="Median PFE")
        ax.set_title("Portfolio" if c == "__portfolio__" else c); ax.set_xlabel("days"); ax.set_ylabel("USD M")
    axs[0, 0].legend()
    fig.tight_layout()
    return fig


def fig_spec_compare(S_, D):
    from risk_engine.exposure.collateral import mpor_vs_uncollateralized_comparison
    meta_ = D["meta"]
    cmp_ = mpor_vs_uncollateralized_comparison(meta_["trade_ids"], meta_["trade_counterparty"], D["npv"], D["node_map"], D["rep_dates"], 0.0, CONF)
    cp = ["CPTY_A", "CPTY_B", "CPTY_C"]
    unc = [prof(D["expo"][c])["P99"].max() / 1e6 for c in cp]
    old = [cmp_["mpor_shifted"][c]["MPE"] / 1e6 for c in cp]
    new = [spec_peaks(S_, c)["PFE"] / 1e6 for c in cp]
    fig, ax = plt.subplots(figsize=(6.4, 2.7))
    w = 0.27
    ax.bar(np.arange(3) - w, unc, w, color=GREY, label="uncollateralized level, max(V,0)")
    ax.bar(np.arange(3), old, w, color=TEAL, label="earlier full-VM illustration (Section 7.6)")
    ax.bar(np.arange(3) + w, new, w, color=NAVY, label="brief's close-out exposure (headline)")
    ax.set_xticks(range(3)); ax.set_xticklabels(cp); ax.set_ylabel("MPE99 (USD M)"); ax.legend(fontsize=6.5)
    ax.set_title("Peak PFE99 under three exposure definitions")
    return fig, unc, old, new

'''
i = s.index("# ------------------------------------------------------------------ report\ndef main():")
s = s[:i] + helpers + "\n" + s[i:]

# ---------------------------------------------------------------- abstract
rep("and Maximum PFE (MPE) by counterparty and for the \"\n          \"portfolio",
    "and Maximum PFE (MPE) by counterparty and for the \"\n          \"portfolio")  if False else None
rep('"PFE, Potential Future Exposure at the 99th percentile (PFE99) and Maximum PFE (MPE) by counterparty and for the "\n          "portfolio,',
    '"PFE, Potential Future Exposure at the 99th percentile (PFE99) and Maximum PFE (MPE) by trade, by counterparty and for the "\n          "portfolio on the 10-day close-out definition specified in the project brief,')

# ---------------------------------------------------------------- summary table
rep('    Rc0 = load_sa_cva()\n', '    Rc0 = load_sa_cva()\n    S0_ = load_spec()\n    sp_ = spec_peaks(S0_, "__portfolio__")\n')
rep('    add(P("The table reports the portfolio results for the uncollateralized book (3,000 Latin Hypercube scenarios, PFE at the 99th percentile).", BODY))',
    '    add(P("The table reports portfolio results. Exposure follows the definition in the project brief (kickoff slides 8 and 9): the movement of the netted value from its prior-day level over a 10-business-day close-out, with variation margin equal to the prior-day value and no initial margin (5,000 Latin Hypercube scenarios, PFE at the 99th percentile, one-year horizon). The uncollateralized level exposure is kept as a secondary view (3,000 scenarios).", BODY))')
i = s.index('             ["Current exposure (portfolio)"')
j = s.index('             ["Concentration"')
new_rows = '''             ["Peak EE (close-out exposure)", f"{m(sp_['EE'])} at {sp_['EE_date']}", "Highest average 10-day close-out exposure within one year"],
             ["Peak median PFE (close-out)", m(sp_["MED"]), "Typical (50th percentile) close-out exposure at its highest date"],
             ["Maximum PFE99, MPE (close-out)", f"{m(sp_['PFE'])} at {sp_['PFE_date']}", "Highest 99th-percentile close-out exposure within one year"],
             ["Current exposure today (uncollateralized)", m(tot["EE"][0]), "Loss if every counterparty defaulted today with no margin, after netting"],
             ["MPE99, uncollateralized (secondary view)", f"{m(mpe99)} at {D['rep_dates'][j_mpe]}", "Highest 99th-percentile level exposure over the life of the book"],
'''
s = s[:i] + new_rows + s[j:]

# ---------------------------------------------------------------- 1.3 definition row
rep('             ["EE (Expected Exposure)",', '             ["Close-out exposure (headline)", "max( V(t + 10bd) - V(t - 1bd), 0 ), netted by counterparty", "The brief\'s definition (slides 8 and 9): variation margin is the prior-day NPV, no initial margin, 10-business-day close-out. EE, median PFE, PFE99 and MPE are computed on it unless labelled uncollateralized"],\n             ["EE (Expected Exposure)",')

# ---------------------------------------------------------------- Section 7.1 block
block = '''    S_ = load_spec()
    add(P("7.1 Exposure on the brief's definition (headline)", H2))
    add(P("The project brief defines exposure for a defaulting counterparty as the movement of the position from its prior-day value over a close-out period (kickoff slide 9): variation margin collected or posted on a date is the NPV of the trade on the prior day on the path, variation margin stops at default, there is no initial margin, and close-out takes 10 business days. For each scenario and reporting date t, on the netted value V of a netting set:"))
    add(code("exposure(t) = max( V(t + 10bd) - V(t - 1bd), 0 )        V(t - 1bd) = variation margin, signed"))
    add(P("EE is the mean of this across scenarios, PFE its 99th percentile, MPE the peak of PFE, all over the one-year horizon of slide 8; the median PFE is added. Netting is applied to the value before the positive part. A trade that settles inside a close-out window is excluded from both legs of that window, since its scheduled value drop to zero is a cash settlement and not a market move. The results are produced per trade and per counterparty, as slide 8 requires. The simulation grid carries three nodes around every reporting date, at t minus 1 business day, t and t plus 10 business days, all on the same simulated path (%d reporting dates); %s Latin Hypercube scenarios, the number recommended in Section 5.5." % (len(S_["reporting_dates"]), format(S_["n_scenarios"], ","))))
    rows = [["Netting set", "Peak EE", "Peak median PFE", "MPE (peak PFE99)", "MPE date"]]
    for c in ("CPTY_A", "CPTY_B", "CPTY_C", "__portfolio__"):
        q_ = spec_peaks(S_, c)
        rows.append([("Portfolio" if c == "__portfolio__" else c), m(q_["EE"]), m(q_["MED"]), m(q_["PFE"]), q_["PFE_date"]])
    add(tbl(rows, widths=[1.5, 1.2, 1.5, 1.6, 1.3]))
    add(P("Values in USD, maximum over the reporting dates within one year of the valuation date. The portfolio is the sum of the counterparty exposures (netting does not cross counterparties).", SMALL))
    add(doc.figure(fig_spec_profiles(S_), "Close-out exposure through the first year: EE, median PFE and PFE99 by counterparty and for the portfolio."))
    rows = [["Trade", "Counterparty", "NPV today", "Peak EE", "MPE (peak PFE99)"]]
    for tid_, v_ in S_["per_trade"].items():
        rows.append([tid_, v_["counterparty"], format(v_["mtm_t0"], ",.0f"), format(v_["EE_max"], ",.0f"), format(v_["MPE"], ",.0f")])
    add(tbl(rows, widths=[1.3, 1.3, 1.5, 1.4, 1.5], font=7.4))
    add(P("Per-trade close-out exposure (each trade on its own, so no netting) in USD. The per-trade figures do not add up to the counterparty figures: netting and the tail of a sum differ from the sum of tails.", SMALL))
    fgc, unc_, old_, new_ = fig_spec_compare(S_, D)
    add(doc.figure(fgc, "Peak PFE99 by counterparty under three definitions of exposure. The level exposure (grey) treats the whole mark-to-market as at risk; the brief's definition (navy) recognises that variation margin covers the prior-day value and leaves only the 10-day move."))
    add(P("<b>Reading the results.</b> The close-out MPE99 is far below the level exposure because the prior-day value is margined: CPTY_C's bond forward BF_0003 is worth $101M today but its 10-day move at the 99th percentile is $18.4M, so its counterparty peaks at $%.1fM against $%.1fM of level exposure. CPTY_A and CPTY_B are driven by the equity swap baskets, whose 10-day equity moves set the tail. Close-out exposure is a measure of market risk over the close-out window, not of the accumulated value, which is why the peak occurs in the first weeks, when the largest baskets are alive, and falls as trades mature. Earlier versions of this report headlined the level exposure; that view is retained below as a secondary measure (Sections 7.2 to 7.4), and the earlier full-variation-margin illustration (Section 7.6) used a same-day, zero-floored margin formula that differs slightly from the brief's. CVA, SA-CVA and the Greeks in Sections 8 and 9 are still computed on the level exposure and are scheduled to be re-run on this definition (Section 15, item 4)." % (new_[2], unc_[2])))
'''
rep('    add(P("7.1 Exposure today (t = 0)", H2))', block + '    add(P("7.2 Exposure today (t = 0)", H2))')
rep('    add(P("7.2 Exposure profiles through time", H2))', '    add(P("7.3 Uncollateralized exposure profiles through time (secondary view)", H2))')
rep('    add(P("7.3 Where does the risk come from?", H2))', '    add(P("7.4 Where does the risk come from?", H2))')
rep('    add(P("7.4 What if the counterparty posts margin? (MPOR-shifted exposure)", H2))', '    add(P("7.5 Earlier illustration: full variation margin with an MPOR shift", H2))')
rep('    add(P("7.5 Full-rank correlation versus PCA factor model", H2))', '    add(P("7.6 Full-rank correlation versus PCA factor model", H2))')

# ---------------------------------------------------------------- cross-references
rep("Section 7.5 compares its exposure profiles", "Section 7.6 compares its exposure profiles") if "Section 7.5 compares its exposure profiles" in s else None
s = s.replace("(Section 7.4)", "(Section 7.5)")
s = s.replace("margined view in Section 7.4", "margined view in Section 7.5")
s = s.replace("Section 7.4 numbers", "Section 7.5 numbers")
s = s.replace("(MPE99 of about $24.9M, $9.2M and $26.7M", "(MPE99 of about $24.9M, $9.2M and $26.7M")
s = s.replace("earlier full-VM illustration (Section 7.6)", "earlier full-VM illustration (Section 7.5)")
s = s.replace("full-variation-margin illustration (Section 7.6)", "full-variation-margin illustration (Section 7.5)")

# ---------------------------------------------------------------- conclusions bullet
rep('f"The uncollateralized book has peak portfolio PFE99', 'f"On the exposure definition in the brief (10-day close-out from the prior-day value), the portfolio MPE99 is {m(sp_[\'PFE\'])} at {sp_[\'PFE_date\']}, with peak EE of {m(sp_[\'EE\'])} and peak median PFE of {m(sp_[\'MED\'])} (Section 7.1).",\n           f"The uncollateralized level exposure, kept as a secondary view, has peak portfolio PFE99')

# ---------------------------------------------------------------- Section 15 updates
rep("The numbers in Sections 7 to 9 should be read with the first two known issues in mind until Priority 1 is done.", "Item 1 is done (Section 7.1); the CVA, SA-CVA and Greeks results in Sections 8 and 9 should be read with the remaining known issues in mind until Priority 1 is complete.")
rep('"Gap: headline exposure is uncollateralized max(V, 0); the margined view uses a different formula and is a side calculation", "Item 1"]', '"Done (Section 7.1): three-node grid, signed prior-day variation margin, netting before the positive part, settlement excluded", "Item 1 done"]')
rep('"Partial: measures exist but on the uncollateralized definition and to January 2028", "Item 1"]', '"Done (Section 7.1): PFE99, MPE, EE and median PFE within the first year", "Item 1 done"]')
rep('"Partial: counterparty and portfolio only are reported", "Item 1"]', '"Done (Section 7.1): 16 trades and 3 counterparties", "Item 1 done"]')
rep('"Done (Section 9)", "Re-run after Priority 1"]', '"Done (Section 9) on the level exposure", "Re-run on the close-out definition (item 4)"]')
i = s.index('    add(B(["<b>Exposure definition.</b> The headline exposure numbers (Section 7)')
j = s.index('           "<b>USD curve beyond seven years.</b>')
s = s[:i] + '    add(B(["<b>Exposure definition (resolved for the exposure measures).</b> The headline exposure now follows the brief (Section 7.1). CVA, SA-CVA and the Greeks in Sections 8 and 9 were computed earlier on the uncollateralized level exposure and are scheduled to be re-run on the close-out definition (item 4); until then they are conservative for a margined counterparty and, for CVA, are not yet on the brief\'s definition.",\n' + s[j:]
rep('["1", "Implement the exposure of slides 8 and 9:', '["1", "Done (Section 7.1). Implement the exposure of slides 8 and 9:')
open(p, "w", encoding="utf-8").write(s)
print("ok12")
