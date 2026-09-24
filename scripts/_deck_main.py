def main():
    import json
    import numpy as np
    import report_greeks as RG
    import report_new as RN
    import report_new2 as RN2

    class Grab:
        """Stand-in for the LaTeX report object: returns the matplotlib figure itself."""
        def figure(self, fig, caption, **k):
            return fig

    def figs(parts):
        return [x for x in parts if not isinstance(x, str)]

    D = R.exposures(R.load_all())
    tmp = tempfile.mkdtemp(prefix="deck_")
    ids = D["meta"]["trade_ids"]
    npv0 = D["npv"][:, 0, :].mean(axis=1)
    S0 = R.load_spec()
    sp = R.spec_peaks(S0, "__portfolio__")
    Ad, Xv, Sa, Sx, Bt = (RN._j(f) for f in ("additivity.json", "xva_results.json", "sa_ccr_results.json", "stress_results.json", "backtest_results.json"))
    Rc = RN.override_cva_with_xva(R.load_sa_cva(), Xv)
    try:
        Rl = json.load(open(os.path.join(R.PROC, "sa_cva_results_level.json")))
    except Exception:
        Rl = None
    g_ = RG.load()
    jpk = RG.peak_node(g_)
    m = R.m
    CPS = ("CPTY_A", "CPTY_B", "CPTY_C")
    xc, xl = Xv["conventions"]["closeout"]["total"], Xv["conventions"]["level"]["total"]
    def _pkv(run):
        return RN._peaks(json.load(open(os.path.join(R.PROC, run, "spec_exposure.json"))), "__portfolio__")["PFE"]
    _b2000 = _pkv("spec_run_final2000")
    _rf = (_pkv("spec_run_rate_eq_flight") / _b2000 - 1) * 100
    _rt = (_pkv("spec_run_rate_eq_together") / _b2000 - 1) * 100

    def deco(c, d):
        c.saveState()
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor("#777777"))
        c.drawString(0.5 * inch, 0.3 * inch, "Capitolis x Berkeley MFE | Counterparty credit risk engine | valuation date 2026-08-28")
        c.drawRightString(PG[0] - 0.5 * inch, 0.3 * inch, str(d.page))
        c.restoreState()

    out = os.path.join(ROOT, "docs", "Capitolis_CCR_Executive_Deck.pdf")
    doc = BaseDocTemplate(out, pagesize=PG, leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                          topMargin=0.45 * inch, bottomMargin=0.5 * inch,
                          title="Counterparty Credit Risk Engine - Executive Deck")
    doc.addPageTemplates([PageTemplate(id="p", frames=[Frame(0.6 * inch, 0.5 * inch, PG[0] - 1.2 * inch, PG[1] - 0.95 * inch)], onPage=deco)])
    FW = PG[0] - 1.2 * inch
    S = []
    n = [0]

    def fig(f, h):
        n[0] += 1
        return img(f, tmp, n[0], FW, h)

    # ------------------------------------------------------------------ title
    S += [Spacer(1, 1.2 * inch), P("Monte Carlo Counterparty Credit Risk Engine", ParagraphStyle("tt", parent=TITLE, fontSize=34, leading=40)),
          P("Executive summary: what the risk is, how we measure it, what we found, and how far to trust it", ParagraphStyle("st", parent=TXT, fontSize=17, leading=22)),
          Spacer(1, 12), P("ESF derivatives book | 16 trades | 3 counterparties | exposure on the brief's 10-day close-out definition | full detail in Capitolis_CCR_Complete_Report.pdf", SM), PageBreak()]

    # ------------------------------------------------------------------ the answer
    mpe_sum = sum(Ad["mpe"].values())
    S += [P("The answer in one page", TITLE),
          tiles([(m(sp["PFE"], 0), "portfolio MPE99, close-out definition (%s)" % sp["PFE_date"]),
                 (m(sp["EE"]), "peak expected exposure (EE)"),
                 (m(sp["MED"]), "peak median PFE"),
                 ("%.0f%%" % (Ad["mpe_portfolio"] / mpe_sum * 100), "portfolio MPE as a share of the sum of the three counterparties")]), Spacer(1, 14)]
    S += bl(["Exposure follows the brief: the move of the netted value from its prior-day level over a 10-business-day close-out, no initial margin, per trade and per counterparty, one-year horizon.",
             "CPTY_A and CPTY_B are equity risk (pay-equity swaps: we gain when shares fall); CPTY_C is mostly interest-rate risk through one $500M short forward on a 2049 Treasury (DV01 %s per bp) with an equity book beside it." % RN._k(Ad["direction"]["dv01_per_bp"]["CPTY_C"]),
             "Counterparty MPE99: A %s, B %s, C %s. The portfolio figure %s is %.0f%% of their sum: netting does not cross counterparties and the books peak within about four weeks of each other." % (m(Ad["mpe"]["CPTY_A"]), m(Ad["mpe"]["CPTY_B"]), m(Ad["mpe"]["CPTY_C"]), m(Ad["mpe_portfolio"]), Ad["mpe_portfolio"] / mpe_sum * 100),
             "Credit: CVA %s on the margined close-out exposure and %s if no margin were ever called (BBB proxy); SA-CVA capital %s; SA-CCR exposure at default %s." % (RN._k(xc["CVA"]), RN._k(xl["CVA"]), ("$%.2fM" % (Rc["K_sa_cva"] / 1e6)), m(Sa["total"]["EAD"])),
             "Confirming CSA terms is the most valuable open question: it decides which of the two exposure definitions applies."])
    S.append(PageBreak())

    # ------------------------------------------------------------------ what we measure
    S += [P("What we measure", TITLE), fig(R.fig_spec_profiles(S0), 3.7 * inch),
          P("exposure(t) = max( V(t + 10bd) - V(t - 1bd), 0 ): variation margin is the prior-day value and stops at default, so only the 10-day move is at risk. EE is the average, the median PFE the typical case, PFE99 the level exceeded in 1 of 100 scenarios, MPE the peak of PFE.", TXT), PageBreak()]

    # ------------------------------------------------------------------ portfolio versus parts
    at = Ad["at_portfolio_mpe_date"]
    fig_a, ax = plt.subplots(figsize=(6.6, 2.7))
    lab = ["CPTY_A", "CPTY_B", "CPTY_C", "Sum of the three", "Portfolio"]
    val = [at["pfe99"]["CPTY_A"], at["pfe99"]["CPTY_B"], at["pfe99"]["CPTY_C"], at["sum"], at["portfolio"]]
    ax.bar(lab, [v / 1e6 for v in val], color=["#1F3A5F", "#2A9D8F", "#E76F51", "#9AA5B1", "#8B0000"])
    for i, v in enumerate(val):
        ax.text(i, v / 1e6 + 0.8, "%.1f" % (v / 1e6), ha="center", fontsize=8)
    ax.set_ylabel("PFE99 (USD M)")
    ax.set_title("PFE99 at the portfolio peak date, %s" % Ad["portfolio_mpe_date"])
    rc = Ad["rank_corr"]
    S += [P("Why the portfolio MPE is close to the sum of its parts", TITLE), fig(fig_a, 2.3 * inch)]
    S += bl(["The portfolio exposure is a sum of per-counterparty positive parts; nothing nets across counterparties. Its 99th percentile is below the sum of the standalone ones only where the tails do not coincide.",
             "Exposures are positively dependent (rank correlation A-B %+.2f, A-C %+.2f, B-C %+.2f): every netting set holds pay-equity swaps, so all gain when equities fall; CPTY_C is not a pure rate set." % (rc["CPTY_A-CPTY_B"], rc["CPTY_A-CPTY_C"], rc["CPTY_B-CPTY_C"]),
             "Bonds and equities: in the last three years yield changes and stock returns are essentially uncorrelated (mean %+.2f). The book is short both, so a flight to quality (yields fall with equities) makes the gains oppose each other and both falling together makes them coincide: portfolio MPE99 %+.0f%% and %+.0f%% against the base (report, Section 7.2)." % (Ad["rate_equity_corr"]["mean"], _rf, _rt)])
    S.append(PageBreak())

    S += [P("The book: 16 trades, short-dated", TITLE), fig(R.fig_book_timeline(D), 3.5 * inch),
          P("8 equity total return swaps (incl. JPY compo), 4 bond forwards, 4 bond TRS across three counterparties. All priced with the supplied, independently reviewed pricer library.", TXT), PageBreak()]

    rows = [["Step", "What we do", "Choice"],
            ["1 Calibrate", "SOFR curve from CME futures with the Bloomberg long end spliced on; realised vols; USD rate sigma fitted to Treasury yield vols; 40x40 correlation", "Real market data throughout"],
            ["2 Simulate", "USD rate: Hull-White one-factor (G2++ two-factor compared). JPY rate: second Hull-White factor. Equities and USDJPY: correlated GBM driven by the rates", "Exact fit to today's curve; negative-rate capable; drifts from the martingale condition"],
            ["3 Sample", "Latin-Hypercube scenarios (5,000 for reporting); Cholesky for correlation (PCA factor model optional)", "Lowest measured error of 5 methods"],
            ["4 Dates", "Market pillar dates plus every trade's event dates, with t - 1bd and t + 10bd nodes", "Exact cash-flow dates and the brief's close-out"],
            ["5 Reprice", "Every trade re-priced in every scenario and node with the standard pricers", "No new pricing logic"],
            ["6 Aggregate", "Close-out exposure, netted by counterparty and per trade: EE, median PFE, PFE99, MPE", "Uncollateralized level exposure alongside"]]
    S += [P("How the engine works", TITLE), table(rows, [1.2 * inch, 5.6 * inch, 3.0 * inch]), PageBreak()]

    # ------------------------------------------------------------------ what changed
    fg_, ax = plt.subplots(figsize=(7.0, 2.8))
    steps, vals = [], []
    for label, run, fn in RN.ATTR:
        pth = os.path.join(R.PROC, run, fn)
        if os.path.exists(pth):
            steps.append({0: "Earlier version", 1: "USDJPY drift fixed", 2: "+ long-end vol fit", 3: "+ Bloomberg long end", 4: "+ JPY factor (final)"}[len(steps)])
            vals.append(RN._peaks(json.load(open(pth)), "__portfolio__")["PFE"] / 1e6)
    ax.barh(range(len(vals))[::-1], vals, color="#1F3A5F")
    ax.set_yticks(range(len(vals))[::-1])
    ax.set_yticklabels(steps, fontsize=7)
    for i, v in zip(range(len(vals))[::-1], vals):
        ax.text(v + 0.5, i, "%.1f" % v, va="center", fontsize=8)
    ax.set_xlabel("portfolio MPE99 (USD M), cumulative corrections")
    S += [P("What changed since the earlier version, and why", TITLE), fig(fg_, 2.8 * inch)]
    S += bl(["Four corrections, each introduced on the same random numbers: USDJPY drift sign (found via a martingale test), volatility fitted to long-end yield moves (the largest effect, on CPTY_C), Bloomberg long end on the USD curve (BF_0003 $101M to $121M), JPY factor wired in.",
             "The long-dated bond forward drives the change: CPTY_C's MPE99 rises most. Details and per-counterparty numbers in the report, Section 7.3."])
    S.append(PageBreak())

    # ------------------------------------------------------------------ model risk
    base_p = os.path.join(R.PROC, "spec_run_final2000", "spec_exposure.json")
    if os.path.exists(base_p):
        base = json.load(open(base_p))
        runs = [("spec_run_ratevol_up", "USD rate sigma x1.25"), ("spec_run_a_x3", "Mean reversion x3"), ("spec_run_eqvol_up", "Equity/FX vols x1.25"),
                ("spec_run_eqvol_x2", "Equity/FX vols x2"), ("spec_run_corr_up", "Equity correlations up"), ("spec_run_rate_eq_flight", "Yields fall with equities"),
                ("spec_run_rate_eq_together", "Yields rise as equities fall"), ("spec_run_g2", "Two-factor G2++")]
        rows = [["Perturbation (one at a time)", "CPTY_A", "CPTY_B", "CPTY_C", "Portfolio"]]
        for run, lab_ in runs:
            pth = os.path.join(R.PROC, run, "spec_exposure.json")
            if os.path.exists(pth):
                s_ = json.load(open(pth))
                rows.append([lab_] + ["%+.0f%%" % ((RN._peaks(s_, c)["PFE"] / RN._peaks(base, c)["PFE"] - 1) * 100) for c in CPS + ("__portfolio__",)])
        S += [P("Model risk: which inputs matter (change in MPE99)", TITLE), table(rows, [3.6 * inch, 1.5 * inch, 1.5 * inch, 1.5 * inch, 1.6 * inch]),
              P("Same random numbers, 2,000 scenarios. Equity volatility and the rate-equity dependence move the portfolio number most; the choice of one or two rate factors matters least.", SM), PageBreak()]

    # ------------------------------------------------------------------ stress testing
    st_parts = RN2.stress_section(Grab())[0]
    sf = figs(st_parts)
    S += [P("Stress testing: %d scenarios, same random numbers, every trade, every date" % len(Sx["scenarios"]), TITLE)]
    if len(sf) >= 2:
        S += [fig(sf[1], 2.3 * inch)]
    wco = max(Sx["scenarios"], key=lambda k_: abs(Sx["scenarios"][k_]["closeout"]["__portfolio__"]["MPE"] / Sx["base"]["closeout"]["__portfolio__"]["MPE"] - 1))
    wlv = max(Sx["scenarios"], key=lambda k_: abs(Sx["scenarios"][k_]["level"]["__portfolio__"]["MPE"] / Sx["base"]["level"]["__portfolio__"]["MPE"] - 1))
    S += bl(["Data: 37 names, USDJPY, Treasury yields 2014-2026; 8 round-number shocks and 3 historical 10-day windows chosen by rule; instantaneous shocks, base-model volatilities.",
             "Close-out MPE99 moves at most %+.0f%% (%s); the uncollateralized level MPE99 %+.0f%% (%s): the margined measure is far less sensitive to level shocks." % ((Sx["scenarios"][wco]["closeout"]["__portfolio__"]["MPE"] / Sx["base"]["closeout"]["__portfolio__"]["MPE"] - 1) * 100, RN2.SHORT.get(wco, wco), (Sx["scenarios"][wlv]["level"]["__portfolio__"]["MPE"] / Sx["base"]["level"]["__portfolio__"]["MPE"] - 1) * 100, RN2.SHORT.get(wlv, wlv)),
             "Sensitivity is product specific (heat map): equity swaps react to equity and FX shocks, the bond forwards and bond TRS to rate shocks."])
    S.append(PageBreak())

    # ------------------------------------------------------------------ backtest
    rows = [["Netting set (equity and FX leg)", "99%: exceptions / expected", "Kupiec p-value", "95%: mean exception rate over 10 offsets"]]
    for c in CPS:
        r99, r95 = Bt["equity"][c]["confidences"]["0.99"], Bt["equity"][c]["confidences"]["0.95"]
        rows.append([c, "%d of %d / %.1f" % (r99["x"], r99["n"], r99["expected"]), "%.2f" % r99["p_value"], "%.1f%% (nominal 5%%)" % (r95["phases_mean_rate"] * 100)])
    S += [P("Backtest: realised 10-day moves against the model's quantiles", TITLE), table(rows, [3.0 * inch, 2.6 * inch, 1.6 * inch, 3.0 * inch])]
    _r = Bt["rates"]
    S += bl(["Out of sample: at every as-of date the model is calibrated on the previous 3 years only; non-overlapping 10-day windows; Kupiec proportion-of-failures test.",
             "Equity and FX leg: the 99% quantile is close to calibrated (CPTY_B slightly light-tailed, as GBM implies); the 95% quantile is conservative for A and C.",
             "Rates leg: the long-end fit of the USD rate volatility gives %.1f%% / %.1f%% exception rates at 95%% / 99%% (nominal 5%% / 1%%); the earlier overnight-SOFR calibration is regime dependent (%.0fbp now against %.0fbp for the fit)." % (np.mean([_r[t]["long_end_fit"]["0.95_up"]["phases_mean_rate"] for t in ("5", "10", "20")]) * 100, np.mean([_r[t]["long_end_fit"]["0.99_up"]["phases_mean_rate"] for t in ("5", "10", "20")]) * 100, Bt["rates_config"]["sigma_now_sofr"] * 1e4, Bt["rates_config"]["sigma_now_fit"] * 1e4)])
    S.append(PageBreak())

    # ------------------------------------------------------------------ CVA
    rows = [["", "CPTY_A", "CPTY_B", "CPTY_C", "Total"]]
    for k_, lab_ in (("closeout", "Close-out exposure"), ("level", "Uncollateralized level exposure")):
        cv = Xv["conventions"][k_]
        for term in ("CVA", "DVA", "FVA"):
            rows.append(["%s: %s" % (lab_, term)] + [RN._k(cv["by_cpty"][c][term]) for c in CPS] + [RN._k(cv["total"][term])])
    S += [P("CVA walk-through, DVA, FVA and capital", TITLE), table(rows, [3.8 * inch, 1.4 * inch, 1.4 * inch, 1.4 * inch, 1.6 * inch])]
    cap_txt = "SA-CVA capital: %s on the close-out exposure" % ("$%.2fM" % (Rc["K_sa_cva"] / 1e6)) + ((" and %s on the uncollateralized exposure" % ("$%.2fM" % (Rl["K_sa_cva"] / 1e6))) if Rl else "")
    S += bl(["CVA = LGD x sum of 0.5 (DEE(t-1) + DEE(t)) x default probability, where DEE is the expected discounted exposure and the default probability comes from a BBB bond-spread proxy (60% LGD). The margined close-out CVA is small; the level CVA is the price if no margin were ever called.",
             "DVA and FVA rest on assumed own credit (BBB) and funding spread; total that avoids double counting = CVA - DVA + FCA.",
             cap_txt + "; SA-CCR EAD %s (dominated by the replacement cost of BF_0003)." % m(Sa["total"]["EAD"]),
             "For the next session: which exposure definition prices CVA, real ratings or CDS, own credit, wrong-way risk, capital approach."])
    S.append(PageBreak())

    # ------------------------------------------------------------------ Greeks
    tc = g_["timing_clean"]
    nb = tc["n_bumps"]
    n_resim = 2 + len(g_["rate_buckets"]) + 3
    S += [P("Greeks: how they are generated and what they cost", TITLE), fig(RG.fig_profiles(g_), 2.2 * inch)]
    S += bl(["Method: bump-and-reprice with common random numbers (same draws in base and bumped runs); central differences for delta and gamma; equity and FX bumps rescale the paths exactly and reprice only the trades holding the factor; rate and volatility bumps re-simulate.",
             "Cost at N = %d: base run %.0f s, %d equity/FX bumps %.0f s (about %.0fx cheaper than re-simulating each), %d rate/vol re-simulations at %.0f s each." % (tc["n"], tc["base_run_s"], nb, tc["subset_bumps_s"], nb * tc["base_run_s"] / max(tc["subset_bumps_s"], 1), n_resim, tc["one_resim_s"]),
             "Faster alternative implemented: pathwise deltas for equity and FX need no repricing (seconds for every name, netting set and date); adjoint differentiation would cover rates and vol too but needs the black-box pricers ported.",
             "At peak PFE99 (%s): +1%% on all equities moves PFE99 by %s; +1bp on USD rates by %s." % (g_["dates"][jpk], RN._k(g_["equity_all"]["delta"]["__portfolio__"]["PFE"][jpk]), RN._k(g_["rate_parallel"]["delta"]["__portfolio__"]["PFE"][jpk]))])
    S.append(PageBreak())

    # ------------------------------------------------------------------ PCA
    Pc = RN._j("pca_study.json")
    sp_ = Pc["speed"]
    S += [P("The PCA factor model: explainable, but no speed-up", TITLE)]
    S += bl(["Factor 1 is the market (%.0f%% of variance); factor 2 separates the Tokyo listings from the US names; later factors pick out groups of names. Five factors explain %.0f%% of the variance, ten %.0f%%." % (Pc["factors"][0]["variance_share"] * 100, Pc["explained"]["5"] * 100, Pc["explained"]["10"] * 100),
             "Speed: none. The correlated-shock step is not faster (%.2f s full against %.2f s with 5 factors for 5,000 scenarios) and in any case the run is dominated by repricing (about %.0f s)." % (sp_["full"]["draws_s"], sp_["pca5"]["draws_s"], Pc["reprice_s_5000"] or 0),
             "Accuracy: netting-set volatilities under 5 factors differ from the full matrix by %s. Sampling error is not consistently lower, because the factor draws add dimensions." % ", ".join("%s %+.1f%%" % (c[-1], (v["5"] / v["full"] - 1) * 100) for c, v in Pc["position_vol"].items()),
             "Decision: keep the full-rank Cholesky as default; the factor model stays as a robustness option."])
    S.append(PageBreak())

    # ------------------------------------------------------------------ data and methods
    rows = [["Input", "Source", "Used for"],
            ["Trades, pricing library", "Capitolis (supplied)", "16 trades; all valuation"],
            ["USD SOFR futures; USD zero curve long end", "CME via Databento; Bloomberg snapshot (licensed)", "USD curve (our bootstrap plus spliced long end)"],
            ["Treasury CMT yields 3M-30Y", "FRED", "USD rate sigma, correlations, G2++, backtest, stress replays"],
            ["Equities, USDJPY, sectors", "yfinance", "Spots, vols, correlation, SA-CVA buckets, backtest"],
            ["SOFR history; credit spreads by rating", "FRED (SOFR, ICE BofA OAS)", "USD-JPY correlation; CVA credit proxy"],
            ["JPY OIS history (35 tenors, 2011-2026)", "Bloomberg file from the project team", "JPY curve, vol, correlations, mean-reversion test"],
            ["TONA; JGB yields", "Bank of Japan API; Japan MoF", "JPY rate cross-checks"],
            ["Swaption cubes, FX forwards", "Bloomberg snapshot (licensed)", "USD mean reversion, FX forwards"],
            ["SA-CVA rules; SA-CCR rules", "BIS Basel MAR50 (2020); CRE52", "Risk weights, correlations, aggregation, EAD"]]
    S += [P("Data sources", TITLE), table(rows, [3.0 * inch, 3.2 * inch, 3.6 * inch]), PageBreak()]

    # ------------------------------------------------------------------ remaining work
    S += [P("What remains, and what we need from Capitolis", TITLE)]
    S += bl(["Data: real counterparty ratings or CDS; credit support annex terms (threshold, minimum transfer amount, initial margin).",
             "Decisions: which exposure definition prices CVA; whether DVA is recognised; whether a wrong-way-risk model is wanted; SA-CVA versus BA-CVA as the capital reference.",
             "Longer term: adjoint differentiation (needs the pricers ported), two-factor rates as default (swaption calibration), hybrid sampling for the PCA option, stochastic volatility if option data is provided.",
             "Assumptions to keep in mind: volatility is a 3-year realised proxy; one static correlation matrix; GBM understates fat tails; own credit and funding spread are assumed; stress tests are instantaneous shocks.",
             "Ask: are any trades margined, and under what CSA terms?"])
    doc.build(S)
    print("wrote", out)


if __name__ == "__main__":
    main()
