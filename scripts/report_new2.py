"""Report content, part 2: stress testing, Greeks method and cost, PCA
explainability and speed, portfolio additivity, CVA walk-through, risky-bond
sample. Numbers are read from the result files under data/processed/."""
import json
import os
from datetime import date

import numpy as np

from report_lib import GOLD, GREY, NAVY, ORANGE, TEAL, plt
from report_new import CP, RED, _j, _k, _m, _peaks, spec
from report_tex import B, H2, SMALL, callout, code, P, tbl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
SHORT = {"EQ_DOWN_30": "Equities -30%", "EQ_UP_30": "Equities +30%", "JPY_STRONG_15": "Yen +15%", "JPY_WEAK_15": "Yen -15%",
         "RATES_UP_200": "Rates +200bp", "RATES_DOWN_200": "Rates -200bp", "FLIGHT_TO_QUALITY": "Flight to quality",
         "STAGFLATION": "Stagflation", "HIST_EQUITY_CRASH": "Hist. equity crash", "HIST_RATES_SPIKE": "Hist. rates spike",
         "HIST_YEN_SURGE": "Hist. yen surge"}


def _pct(v, b):
    return "%+.0f%%" % ((v / b - 1.0) * 100) if b > 1e3 else "n/a"


# ---------------------------------------------------------------- stress testing
def _shock_text(d):
    parts = []
    if d["equity_return_max"] != 0 or d["equity_return_min"] != 0:
        if abs(d["equity_return_max"] - d["equity_return_min"]) < 1e-12:
            parts.append("all equities %+.0f%%" % (d["equity_return_min"] * 100))
        else:
            parts.append("equities median %+.0f%% (range %+.0f%% to %+.0f%%)" % (d["equity_return_median"] * 100, d["equity_return_min"] * 100, d["equity_return_max"] * 100))
    if abs(d["fx_return"]) > 1e-12:
        parts.append("USDJPY %+.1f%%" % (d["fx_return"] * 100))
    if d["dy_bp"] is not None:
        t, bp = d["dy_tenors"], d["dy_bp"]
        if max(bp) - min(bp) < 1e-9:
            parts.append("USD curve %+.0fbp parallel" % bp[0])
        else:
            pick = [(x, y) for x, y in zip(t, bp) if x in (1, 2, 5, 10, 30)]
            parts.append("USD yields " + ", ".join("%gy %+.0fbp" % (x, y) for x, y in pick))
    return "; ".join(parts)


def stress_section(doc):
    R = _j("stress_results.json")
    base, sc, defs = R["base"], R["scenarios"], R["definitions"]
    names = list(sc)
    out = [P("Stress testing is designed here as a structured experiment rather than a discussion: a fixed set of scenarios with stated data and shocks, the same random numbers in every run, and outputs read at every reporting date, for every netting set and for every trade. It answers four questions: what data drove each scenario, what the inputs were, how far the outputs move along the path of time, and whether all products are sensitive.")]
    out.append(P("<b>Method.</b> Each scenario is an instantaneous shock to today's market state, applied to the equity spots, USDJPY and the USD curve; the full Monte Carlo of exposure is then run from the shocked state with the same %s Latin Hypercube scenarios and seed as the base case, so differences are due to the shock and not to sampling. Equity and FX shocks rescale the simulated GBM paths exactly and reprice only the trades holding those factors; a rate shift replaces the Hull-White curve and re-simulates. The scenario volatilities, correlations and mean reversion are those of the base calibration; how the results move when those parameters are stressed is in the model-risk study of Section 7.9. Outputs are the close-out exposure of the brief (EE, median PFE, PFE99 and MPE within one year) and, alongside, the uncollateralized level exposure max(V, 0), because the two respond very differently to the same shock." % format(R["n_scenarios"], ",")))
    rows = [["Scenario", "Family", "Shock applied to today's market state", "Data behind the shock", "Rates re-simulated"]]
    for n in names:
        d = defs[n]
        src = ("Round-number shock" if d["kind"] == "hypothetical" else "Actual moves over %s to %s: per-name closes (yfinance), USDJPY (yfinance), Treasury CMT yields (FRED)" % tuple(d["window"]))
        rows.append([SHORT.get(n, n), d["kind"], _shock_text(d), src, "yes" if d["dy_bp"] is not None else "no"])
    out.append(tbl(rows, widths=[1.3, 0.9, 2.6, 2.6, 0.7], font=7.0))
    out.append(P("Historical windows are chosen by rule, not by hand: the worst 10-business-day window of the median return across the 37 names in 2014-2026, the largest 10-day rise of the 10-year yield, and the largest 10-day fall of USDJPY. Each replay applies the actual return of every name (a name without price history in that window takes the median return) together with the yield changes at each tenor and the USDJPY move over the same dates.", SMALL))
    # table 1: close-out
    for key, title, cap in (("closeout", "Close-out exposure (the brief's definition): MPE99 within one year", "co"), ("level", "Uncollateralized level exposure: MPE99 within one year", "lv")):
        rows = [["Scenario", "CPTY_A", "CPTY_B", "CPTY_C", "Portfolio"]]
        rows.append(["Base case"] + [_m(base[key][e]["MPE"]) for e in CP + ("__portfolio__",)])
        for n in names:
            rows.append([SHORT.get(n, n)] + ["%s (%s)" % (_m(sc[n][key][e]["MPE"]), _pct(sc[n][key][e]["MPE"], base[key][e]["MPE"])) for e in CP + ("__portfolio__",)])
        out.append(P("<b>%s.</b>" % title))
        out.append(tbl(rows, widths=[1.7, 1.4, 1.4, 1.4, 1.4], font=7.2))
    # time path
    fig, ax = plt.subplots(1, 2, figsize=(7.4, 2.9))
    dts = [date.fromisoformat(d) for d in base["dates"]]
    ref = date.fromisoformat(R["ref_date"])
    days = np.array([(d - ref).days for d in dts])
    keep = days <= 365
    cols = plt.cm.tab20(np.linspace(0, 1, len(names)))
    for a_, key, ttl in ((ax[0], "closeout", "Close-out PFE99, portfolio"), (ax[1], "level", "Level PFE99, portfolio")):
        b = np.array(base[key]["__portfolio__"]["PFE"])
        for n, c in zip(names, cols):
            s_ = np.array(sc[n][key]["__portfolio__"]["PFE"])
            a_.plot(days[keep], (s_ / np.maximum(b, 1.0))[keep], color=c, lw=1.0, label=SHORT.get(n, n))
        a_.axhline(1.0, color="k", lw=0.8)
        a_.set_title(ttl + ": stressed / base", fontsize=8)
        a_.set_xlabel("days from valuation date")
        a_.set_ylim(0, 3.2 if key == "level" else 2.2)
    ax[1].legend(fontsize=5.5, ncol=2)
    out.append(doc.figure(fig, "Ratio of stressed to base portfolio PFE99 along the first year, close-out exposure (left) and level exposure (right). A ratio of one means no sensitivity at that date."))
    # ratios at horizons
    hz = [("1M", 30), ("3M", 91), ("6M", 182), ("12M", 365)]
    idx = [int(np.argmin(np.abs(days - d))) for _, d in hz]
    rows = [["Scenario"] + ["Close-out at " + h for h, _ in hz] + ["Level at " + h for h, _ in hz]]
    for n in names:
        r = [SHORT.get(n, n)]
        for key in ("closeout", "level"):
            b = np.array(base[key]["__portfolio__"]["PFE"])
            s_ = np.array(sc[n][key]["__portfolio__"]["PFE"])
            r += ["%.2f" % (s_[i] / b[i]) if b[i] > 1e3 else "n/a" for i in idx]
        rows.append(r)
    out.append(tbl(rows, widths=[1.5] + [0.75] * 8, font=6.8))
    out.append(P("Ratio of stressed to base portfolio PFE99 at four horizons (n/a where the base exposure is negligible because the trades have matured).", SMALL))
    # per-trade heat map
    tids = list(base["per_trade"])
    M = np.zeros((len(tids), len(names)))
    for j, n in enumerate(names):
        for i, t in enumerate(tids):
            b = base["per_trade"][t]["MPE"]
            M[i, j] = (sc[n]["per_trade"][t]["MPE"] / b - 1.0) * 100 if b > 1e4 else np.nan
    fig, ax = plt.subplots(figsize=(7.4, 4.2))
    im = ax.imshow(np.clip(M, -100, 100), cmap="RdBu_r", vmin=-100, vmax=100, aspect="auto")
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels([SHORT.get(n, n) for n in names], rotation=45, ha="right", fontsize=6.5)
    ax.set_yticks(range(len(tids)))
    ax.set_yticklabels(["%s (%s)" % (t, base["per_trade"][t]["counterparty"][-1]) for t in tids], fontsize=6.5)
    for i in range(len(tids)):
        for j in range(len(names)):
            if np.isfinite(M[i, j]):
                ax.text(j, i, "%+.0f" % M[i, j], ha="center", va="center", fontsize=5.5, color="black")
    fig.colorbar(im, ax=ax, fraction=0.03).set_label("change in trade MPE99 (%)", fontsize=7)
    ax.set_title("Close-out MPE99 by trade under each stress (% change from base; blank where the trade's base MPE is under $10k)", fontsize=7.5)
    out.append(doc.figure(fig, "Sensitivity by product: every trade against every scenario."))
    # product-type summary
    typ = {}
    for t in tids:
        typ[t] = "Equity TRS" if t.startswith("EQTRS") else ("Bond forward" if t.startswith("BF_") else "Bond TRS")
    rows = [["Product type", "Trades"] + [SHORT.get(n, n) for n in names]]
    for tp in ("Equity TRS", "Bond forward", "Bond TRS"):
        ii = [i for i, t in enumerate(tids) if typ[t] == tp]
        r = [tp, str(len(ii))]
        for j in range(len(names)):
            v = M[ii, j]
            v = v[np.isfinite(v)]
            r.append("%+.0f%%" % np.median(v) if len(v) else "n/a")
        rows.append(r)
    out.append(P("<b>Median change in close-out trade MPE99 by product type:</b>"))
    out.append(tbl(rows, widths=[1.2, 0.5] + [0.62] * len(names), font=6.4))
    # findings, computed
    port_co = {n: sc[n]["closeout"]["__portfolio__"]["MPE"] / base["closeout"]["__portfolio__"]["MPE"] - 1 for n in names}
    port_lv = {n: sc[n]["level"]["__portfolio__"]["MPE"] / base["level"]["__portfolio__"]["MPE"] - 1 for n in names}
    wco = max(port_co, key=lambda n: abs(port_co[n]))
    wlv = max(port_lv, key=lambda n: abs(port_lv[n]))
    n_trade_moves = {n: int(np.sum(np.abs(M[:, j][np.isfinite(M[:, j])]) > 10)) for j, n in enumerate(names)}
    n_valid = int(np.sum(np.isfinite(M[:, 0])))
    eq_only = [n for n in names if defs[n]["dy_bp"] is None and n.startswith("EQ")]
    out.append(P("<b>What the stress tests show.</b> (1) The close-out exposure is far less sensitive to instantaneous level shocks than the level exposure: the largest portfolio change is %+.0f%% (%s) for close-out MPE99, against %+.0f%% (%s) for level MPE99. This is structural: the close-out exposure measures the move over 10 days from a margined start, so a shock to today's levels changes it only through the size of the positions, whereas the uncollateralized exposure is the level itself. (2) Sensitivity is not uniform across products. The number of trades (of %d with a meaningful base MPE) whose close-out MPE99 moves by more than 10%% ranges from %d to %d across the scenarios; equity-driven trades respond to equity and FX shocks and hardly to rates, and the bond forwards and bond TRS respond to rate shocks and not to equities, as the trade structure implies (heat map above). (3) Along the path, the effect is strongest at the dates where the shocked positions are still alive and fades as trades mature; the ratio plot shows the dates at which each scenario bites. (4) Combined scenarios are not the sum of their parts: flight to quality and stagflation, which apply the same equity shock with opposite rate shocks, give portfolio close-out MPE99 of %s and %s against %s in the base, because the equity-heavy netting sets and the rate-heavy netting set react in opposite ways to the rate leg." % (port_co[wco] * 100, SHORT.get(wco, wco), port_lv[wlv] * 100, SHORT.get(wlv, wlv), n_valid, min(n_trade_moves.values()), max(n_trade_moves.values()), _m(sc["FLIGHT_TO_QUALITY"]["closeout"]["__portfolio__"]["MPE"]), _m(sc["STAGFLATION"]["closeout"]["__portfolio__"]["MPE"]), _m(base["closeout"]["__portfolio__"]["MPE"]))))
    return out, R


# ---------------------------------------------------------------- Greeks method and cost
def greeks_method_section(doc, g):
    tc = g["timing_clean"]
    tm = g["timing"]
    N = g["n_scenarios"]
    nb_fx = tc["n_bumps"]
    n_resim = 2 + len(g["rate_buckets"]) + 3
    naive_per = tc["base_run_s"]
    crn = g["crn_vs_independent"]
    ratio = crn["independent_std"] / max(crn["crn_std"], 1e-9)
    out = [P("<b>What was done, stated plainly.</b> Every sensitivity is a finite difference of a simulated exposure measure, computed as bump-and-reprice on the same random numbers. For each risk factor: (1) shift the factor (spot by +1% and -1%; the curve by +1bp and -1bp in parallel and by bucket; volatilities by +1% relative); (2) regenerate the paths from the shifted calibration with the same seed and Latin Hypercube draws; (3) reprice the trades on the shifted paths; (4) recompute EE, median PFE and PFE99 by netting set; (5) take the difference from the base run (central difference for delta and gamma, one-sided for vega and bucketed DV01). Because the random numbers are common, the difference is sensitivity and not sampling noise: the standard deviation of the EE delta estimate is %s against %s with independent draws (%.0fx lower, equivalent to about %.0fx more scenarios)." % (_k(crn["crn_std"]), _k(crn["independent_std"]), ratio, ratio ** 2))]
    out.append(P("<b>The efficiency choices.</b> Two structural facts avoid most of the cost. A spot bump rescales every GBM path exactly, so equity and FX Greeks need no re-simulation; and only the trades holding the bumped factor are repriced (an equity name appears in one to three of the sixteen trades). All %d equity and FX bumps are priced in one process pool. Curve and volatility bumps change the paths, so they need a re-simulation, but the random numbers are reused and the simulation is a small part of the cost: the repricing of every trade at every node dominates." % nb_fx))
    rows = [["Component", "Count", "Cost each", "Total", "Naive cost (full re-simulation and repricing each time)"],
            ["Base run (paths and full repricing)", "1", "%.0f s" % tc["base_run_s"], "%.0f s" % tc["base_run_s"], "-"],
            ["Equity and FX bumps (subset repricing)", str(nb_fx), "%.1f s" % (tc["subset_bumps_s"] / nb_fx), "%.0f s" % tc["subset_bumps_s"], "%s s" % format(nb_fx * naive_per, ",.0f")],
            ["Rate and volatility bumps (re-simulation)", str(n_resim), "%.0f s" % tc["one_resim_s"], "%s s" % format(n_resim * tc["one_resim_s"], ",.0f"), "%s s (same: nothing to save)" % format(n_resim * tc["one_resim_s"], ",.0f")],
            ["t = 0 book Greeks (deterministic)", "1", "%.1f s" % tm["book_greeks_s"], "%.1f s" % tm["book_greeks_s"], "-"]]
    tot = tc["base_run_s"] + tc["subset_bumps_s"] + n_resim * tc["one_resim_s"] + tm["book_greeks_s"]
    naive = tc["base_run_s"] + nb_fx * naive_per + n_resim * tc["one_resim_s"]
    out.append(tbl(rows, widths=[2.4, 0.6, 0.9, 1.0, 2.6], font=7.2))
    out.append(P("Timed at N = %d on the 8-core development machine, 16 trades, 102 grid nodes, Latin Hypercube; costs scale about linearly in N. The full Greeks set (about %d factor bumps in total) therefore costs about %s s at N = %d, against about %s s if every equity and FX bump were a re-simulation (%.1fx). At the production N = %s the whole set costs roughly %.1f hours; reporting exposures alone is one base run." % (tc["n"], nb_fx + n_resim, format(tot, ",.0f"), tc["n"], format(naive, ",.0f"), naive / tot, format(N, ","), tot * N / tc["n"] / 3600.0)))
    out.append(P("<b>Alternatives considered.</b>"))
    rows = [["Method", "How it works", "Assessment for this book"],
            ["Bump-and-reprice, independent random numbers", "Re-run with a fresh seed for each bump", "Unbiased but the noise swamps the difference (%.0fx larger standard deviation here): rejected." % ratio],
            ["Bump-and-reprice, common random numbers (used)", "Same draws in base and bumped runs", "Works on the pricers as a black box for every measure including quantiles; cost is one repricing per bump, cut by subset repricing."],
            ["Pathwise (infinitesimal perturbation)", "Differentiate the payoff along each path: for a linear-in-spot trade d NPV/d S0 = position x S(t)/S0", "Implemented for equity and FX deltas (greeks/pathwise.py): no repricing at all, exact for EE, noisy for quantiles; validated below. Not applicable to rates without differentiating the pricers."],
            ["Likelihood ratio", "Differentiate the density of the path instead of the payoff", "Suits vega-type parameters but has high variance over many time steps: not adopted."],
            ["Adjoint (algorithmic) differentiation", "Backward sweep through pricers and paths gives all Greeks for about 3-5x the cost of one valuation, independent of the number of factors", "The asymptotically fastest option (all 37 equity, FX, rate-bucket and vega Greeks in one sweep), but it needs the pricers re-implemented in a differentiable form; the supplied pure-Python pricers are a black box, so it was not possible. It is the recommended route if the pricers are ported."],
            ["Delta-gamma or regression proxies of the exposure", "Fit a cheap approximation of the netted value in the risk factors and differentiate it", "Cheap, but the proxy error is added to the Greek and the quantile Greeks are least accurate: reserved for the future, if a Longstaff-Schwartz style proxy is ever built for other purposes."]]
    out.append(tbl(rows, widths=[1.7, 2.6, 3.7], font=7.0))
    p = os.path.join(PROC, "pathwise_validation.json")
    if os.path.exists(p):
        V = _j("pathwise_validation.json")
        rows = [["Measure", "Names x netting sets compared", "Median max difference", "Worst max difference"]]
        for m_, lab in (("EE", "EE delta"), ("MED", "Median PFE delta"), ("PFE", "PFE99 delta")):
            s = V.get("equity_%s_summary" % m_)
            if s:
                rows.append([lab + " (equity)", str(s["n"]), "%.1f%% of peak" % (s["median_max_abs"] * 100), "%.1f%% of peak" % (s["worst_max_abs"] * 100)])
        s = V.get("fx_EE_summary")
        if s:
            rows.append(["EE delta (USDJPY)", str(s["n"]), "%.1f%% of peak" % (s["median_max_abs"] * 100), "%.1f%% of peak" % (s["worst_max_abs"] * 100)])
        out.append(P("<b>Is there a faster alternative? Yes, for equity and FX.</b> The pathwise estimator gives every equity and FX delta of every netting set at every reporting date in %.1f seconds from the paths and NPVs already in memory, against %.0f seconds for the %d bump-and-reprice runs. Against those bump results, on the same scenarios:" % (V["pathwise_seconds"], V["bump_seconds"]["equity_fx_bumps_s"] or tc["subset_bumps_s"], V["bump_seconds"]["n_equity_fx_bumps"] or nb_fx)))
        out.append(tbl(rows, widths=[2.2, 2.0, 1.6, 1.6], font=7.4))
        out.append(P("Differences are the maximum over reporting dates as a percentage of the peak absolute delta. EE matches (the estimators are algebraically the same up to the kink at zero); the median and PFE99 pathwise deltas are local averages over a few dozen scenarios and are therefore noisier, which is why the bump-and-reprice values remain the reported ones and pathwise is used as an independent check and as the fast path for equity and FX. The remaining cost is the rate and volatility bumps, which no pathwise formula covers here.", SMALL))
    return out


# ---------------------------------------------------------------- PCA
def pca_section(doc):
    R = _j("pca_study.json")
    ev = R["explained"]
    out = [P("<b>What the factors are.</b> The factors are the eigenvectors of the 40x40 correlation matrix; each name's loading is its correlation with that factor. They are statistical, not economic, factors, but their loadings can be read off the data. The first factor is the market: every name loads positively and it alone explains %.0f%% of the variance. The later factors separate groups of names that move together."  % (R["factors"][0]["variance_share"] * 100))]
    rows = [["Factor", "Share of variance", "Highest loadings", "Lowest loadings", "Mean loading, US names / JPY names", "Reading"]]
    for f in R["factors"][:5]:
        us, jp = f["mean_loading_us_names"], f["mean_loading_jpy_names"]
        if f["index"] == 1:
            rd = "Market factor: all names, both regions"
        elif abs(us - jp) > 0.25:
            rd = "Japan versus US"
        else:
            rd = "A group of names (see the extremes)"
        rows.append([str(f["index"]), "%.1f%%" % (f["variance_share"] * 100), ", ".join("%s %+.2f" % (a, b) for a, b in f["top_positive"][:4]),
                     ", ".join("%s %+.2f" % (a, b) for a, b in f["top_negative"][:4]), "%+.2f / %+.2f" % (us, jp), rd])
    out.append(tbl(rows, widths=[0.5, 0.8, 2.2, 2.2, 1.0, 1.4], font=6.8))
    out.append(P("Tickers, signed loadings; the sign of a factor is arbitrary. Factors 2 to 5 mostly separate the Tokyo listings from the US names and single out a few high-volatility names, which is what one would expect from a book of 37 stocks in two markets; they explain little each, which is why more than five factors are needed to reproduce the matrix closely.", SMALL))
    rows = [["Factors k", "Cumulative variance explained"] + ["Portfolio vol, %s" % c for c in R["position_vol"]]]
    for k in ("3", "5", "10"):
        rows.append([k, "%.0f%%" % (ev[k] * 100)] + ["%s (%+.1f%%)" % (_m(v[k]), (v[k] / v["full"] - 1) * 100) for v in R["position_vol"].values()])
    rows.append(["Full matrix", "100%"] + [_m(v["full"]) + " (reference)" for v in R["position_vol"].values()])
    out.append(P("<b>What accuracy is given up, on the real book.</b> The one-year-horizon volatility of each netting set's equity position under the full correlation matrix and under the k-factor reconstruction (diagonal restored to one), in USD:"))
    out.append(tbl(rows, widths=[1.0, 1.7, 1.6, 1.6, 1.6], font=7.2))
    sp = R["speed"]
    dr = R.get("reprice_s_5000")
    full, p5 = sp["full"]["draws_s"], sp["pca5"]["draws_s"]
    rows = [["Corr. mode", "Random factors per step", "Correlated-shock step (5,000 scenarios)", "Share of the reporting run"]]
    for mode, lab in (("full", "Full Cholesky"), ("pca5", "PCA, 5 factors"), ("pca10", "PCA, 10 factors")):
        rows.append([lab, str(sp[mode]["n_factors"] + (0 if mode == "full" else int(mode[3:]))), "%.2f s" % sp[mode]["draws_s"],
                     "%.3f%%" % (sp[mode]["draws_s"] / dr * 100) if dr else "n/a"])
    out.append(P("<b>How much speed does it add?</b> Almost none, and it is worth saying why. The factor model replaces a 40x40 matrix product per step with a 40x5 one plus independent noise, which does make the correlated-shock step cheaper, but that step is a vanishing part of the run; the run is dominated by repricing every trade at every node (%s for 5,000 scenarios on the close-out grid):" % ("%.0f s" % dr if dr else "about 47 minutes")))
    out.append(tbl(rows, widths=[1.6, 1.6, 2.6, 1.6], font=7.4))
    out.append(P("The step costs %.2f s against %.2f s, a saving of %.2f s in a run of %s, so the end-to-end speed added is under 0.1%%." % (full, p5, full - p5, "%.0f s" % dr if dr else "roughly 47 minutes")))
    S = R["sampling"]
    ref = S["reference_pfe99_full_pseudo_10000"]
    rows = [["Corr. mode"] + ["Std of PFE99, %s (%% of reference)" % c for c in ref] + ["Bias, %s (%% of reference)" % c for c in ref]]
    for mode, lab in (("full", "Full Cholesky"), ("pca3", "PCA, 3 factors"), ("pca5", "PCA, 5 factors"), ("pca10", "PCA, 10 factors")):
        m_ = S["modes"][mode]
        rows.append([lab] + ["%.1f%%" % (m_[c]["std"] / abs(ref[c]) * 100) for c in ref] + ["%+.1f%%" % (m_[c]["bias_vs_reference"] / abs(ref[c]) * 100) for c in ref])
    out.append(P("<b>Does it help the sampling error?</b> The hope for a factor model with quasi-random numbers is a lower-dimensional space. Here the engine draws the five systematic and the 40 idiosyncratic shocks with the same Latin Hypercube generator, so the dimension per step rises from 40 to 45. Measured on the one-month PFE99 of each netting set's equity positions over %d seeds at N = %d, against a pseudo-random full-rank reference at N = 10,000:" % (S["seeds"], S["n"])))
    out.append(tbl(rows, widths=[1.6] + [1.0] * (2 * len(ref)), font=7.0))
    out.append(callout("Conclusion: the PCA factor model is explainable (a market factor, a Japan-versus-US factor and group factors) but it approximates the correlation matrix, it does not speed up the run, and it does not reduce sampling error in its present form. The full-rank Cholesky remains the default; the factor model is kept as a robustness option, and would become useful only if the systematic factors alone were drawn quasi-randomly and the idiosyncratic noise pseudo-randomly."))
    return out


# ---------------------------------------------------------------- additivity
def additivity_section(doc):
    A = _j("additivity.json")
    S = spec()
    fl, tg = "spec_run_rate_eq_flight", "spec_run_rate_eq_together"
    d = A["direction"]
    rows = [["Netting set", "Equity delta (USD per +1%)", "DV01 (USD per +1bp)", "FX delta (USD per +1%)", "What gains for us"]]
    txt = {}
    for c in CP:
        e, r = d["equity_delta_per_1pct"][c], d["dv01_per_bp"][c]
        parts = []
        if e < -1e4:
            parts.append("equities fall")
        if e > 1e4:
            parts.append("equities rise")
        if r > 1e3:
            parts.append("yields rise")
        if r < -1e3:
            parts.append("yields fall")
        txt[c] = " and ".join(parts) or "little"
        rows.append([c, format(e, ",.0f"), format(r, ",.0f"), format(d["fx_delta_per_1pct"][c], ",.0f"), txt[c]])
    out = [P("<b>Which netting set is driven by what.</b> The t = 0 sensitivities separate the netting sets clearly:")]
    out.append(tbl(rows, widths=[1.1, 1.7, 1.5, 1.5, 2.2], font=7.4))
    out.append(P("A negative equity delta means the netting set gains when equities fall (the swaps are pay-equity); a positive DV01 means it gains when yields rise (the bond forwards are short and the bond TRS are pay-total-return, both short the bond). CPTY_A and CPTY_B are equity risk with a small rate component; CPTY_C is interest-rate risk, through the 500M short forward on the 2049 Treasury BF_0003, with an equity book beside it.", SMALL))
    re_ = A["rate_equity_corr"]
    out.append(P("<b>Should bonds be inversely related to equities?</b> Economically the relation changes sign with the regime: in a growth scare (flight to quality) equities fall and bonds rally, so yields fall with equities; in an inflation shock (as in 2022) both fall together. The calibration reflects only the last three years, in which the correlation of daily 10-year-yield changes with the 37 stocks averages %+.2f (range %+.2f to %+.2f), i.e. essentially none. The book is short both equities (CPTY_A, CPTY_B) and the long bond (CPTY_C): it gains from falling equities and from rising yields. In a flight to quality the two gains oppose each other (equities fall, yields fall); when both fall together they coincide." % (re_["mean"], re_["min"], re_["max"])))
    at = A["at_portfolio_mpe_date"]
    ssum = at["sum"]
    out.append(P("<b>Why is the portfolio MPE close to the sum of the counterparty MPEs?</b> The portfolio exposure is the sum of the counterparties' exposures, because netting never crosses counterparties: it is sum over c of max(V_c, 0), not max of the sum. Its 99th percentile is below the sum of the counterparties' 99th percentiles only to the extent that the counterparties are not simultaneously in their tails. At the portfolio's peak date (%s) the three counterparties' PFE99 are %s, %s and %s, summing to %s, against a portfolio PFE99 of %s: %.0f%% of the sum, i.e. a diversification benefit of %.0f%%. The peak dates of the individual counterparties fall within days of each other (%s) because all three books are largest in the first weeks, before the equity swaps mature, so there is little timing diversification." % (A["portfolio_mpe_date"], _m(at["pfe99"]["CPTY_A"]), _m(at["pfe99"]["CPTY_B"]), _m(at["pfe99"]["CPTY_C"]), _m(ssum), _m(at["portfolio"]), at["portfolio"] / ssum * 100, (1 - at["portfolio"] / ssum) * 100, ", ".join("%s %s" % (c[-1], A["mpe_date"][c]) for c in CP))))
    rc = A["rank_corr"]
    tc = A["tail_coexceedance"]
    cont = A["contribution_at_p99"]
    rows = [["Statistic at the portfolio MPE date", "CPTY_A", "CPTY_B", "CPTY_C"],
            ["Standalone PFE99"] + [_m(at["pfe99"][c]) for c in CP],
            ["Average exposure over the scenarios at the portfolio's 99th percentile"] + [_m(cont[c]) for c in CP],
            ["Probability that the exposure is positive"] + ["%.0f%%" % (A["prob_positive"][c] * 100) for c in CP],
            ["Share of the portfolio's tail scenarios in which the counterparty has zero exposure"] + ["%.0f%%" % (A["share_zero_in_tail"][c] * 100) for c in CP]]
    out.append(tbl(rows, widths=[3.6, 1.1, 1.1, 1.1], font=7.4))
    out.append(P("Rank correlations of the counterparty exposures at that date: A-B %+.2f, A-C %+.2f, B-C %+.2f. Probability that one counterparty is above its own 99th percentile given another is: A given B %.0f%%, A given C %.0f%%, C given B %.0f%% (an independent pair would give 1%%). The two equity netting sets are strongly dependent, because they hold overlapping large-cap names and are driven by the same market factor, which is why their tails coincide and their PFEs nearly add; the interest-rate netting set is close to independent of them in the base calibration." % (rc["CPTY_A-CPTY_B"], rc["CPTY_A-CPTY_C"], rc["CPTY_B-CPTY_C"], tc["CPTY_A|CPTY_B"] * 100, tc["CPTY_A|CPTY_C"] * 100, tc["CPTY_C|CPTY_B"] * 100)))
    rows = [["Rate-equity dependence assumed", "CPTY_A", "CPTY_B", "CPTY_C", "Sum of MPEs", "Portfolio MPE", "Portfolio / sum"]]
    variants = [("Base case (calibrated, about zero)", "spec_run_final2000"), ("Flight to quality: yields fall with equities (corr +0.4 x market beta)", fl),
                ("Both fall together: yields rise as equities fall (corr -0.4 x market beta)", tg)]
    got = 0
    for lab, run in variants:
        p = os.path.join(PROC, run, "spec_exposure.json")
        if not os.path.exists(p):
            continue
        s = json.load(open(p))
        pk = {c: _peaks(s, c)["PFE"] for c in CP + ("__portfolio__",)}
        sm = sum(pk[c] for c in CP)
        rows.append([lab] + [_m(pk[c]) for c in CP] + [_m(sm), _m(pk["__portfolio__"]), "%.0f%%" % (pk["__portfolio__"] / sm * 100)])
        got += 1
    if got == 3:
        out.append(P("<b>How much does the assumed dependence between rates and equities matter?</b> Re-running the close-out exposure with the yield made positively or negatively correlated with the equity market (2,000 scenarios, same random numbers):"))
        out.append(tbl(rows, widths=[3.2, 0.8, 0.8, 0.8, 0.9, 1.0, 0.9], font=7.0))
    return out, A


# ---------------------------------------------------------------- CVA walk-through
def cva_walkthrough(doc, calib_ref):
    from risk_engine.market.credit_spreads import rating_spread_curve
    from risk_engine.exposure.sa_cva import CCS_TENORS
    from risk_engine.models.credit import LGD, marginal_pd, spread_at
    R = _j("xva_results.json")
    t = np.array(R["times"])
    tn, sp = rating_spread_curve("BBB", calib_ref, CCS_TENORS)
    out = [P("This section walks through the CVA calculation step by step for one netting set, CPTY_C, on the close-out exposure, with the numbers behind each column, and closes with the questions to settle at the next session.")]
    out.append(P("<b>The formula.</b> Credit valuation adjustment is the expected loss from a counterparty default, priced under the risk-neutral measure (Basel MAR50.32):"))
    out.append(code("CVA = LGD * sum_i  0.5 * ( DEE(t_{i-1}) + DEE(t_i) ) * PD(t_{i-1}, t_i)\n"
                    "DEE(t)   = E[ D(t) * exposure(t) ]           expected discounted exposure, D = pathwise discount factor\n"
                    "PD(a,b)  = Q(a) - Q(b),  Q(t) = exp( -s(t) t / LGD )      default probability from the credit spread s"))
    out.append(P("Inputs, in the order they enter: (1) the exposure profile from the simulation (Section 7.1), discounted along each path with the simulated short rate; (2) the counterparty's credit spread curve, here a proxy (ICE BofA BBB option-adjusted spreads, %s bp at 1 year and %s bp at 5 years) because no CDS was available and the counterparties are anonymised; (3) a loss given default of %.0f%% (recovery %.0f%%); (4) the assumption that exposure and default are independent (no wrong-way risk)." % ("%.0f" % (spread_at(tn, sp, 1.0) * 1e4), "%.0f" % (spread_at(tn, sp, 5.0) * 1e4), LGD * 100, (1 - LGD) * 100)))
    for conv, lab in (("closeout", "close-out exposure (headline)"), ("level", "uncollateralized level exposure")):
        dee = np.array(R["conventions"][conv]["profiles"]["CPTY_C"]["EPE"])
        pd_ = marginal_pd(t, tn, sp, LGD)
        contrib = LGD * 0.5 * (dee[:-1] + dee[1:]) * pd_
        rows = [["Date (years)", "DEE", "Spread (bp)", "Survival Q(t)", "Interval PD", "Contribution to CVA"]]
        keep = [i for i in range(1, len(t)) if contrib[i - 1] > 0.02 * contrib.max()][:14]
        for i in keep:
            rows.append(["%.2f" % t[i], _k(dee[i]), "%.0f" % (spread_at(tn, sp, t[i]) * 1e4), "%.4f" % np.exp(-spread_at(tn, sp, t[i]) * t[i] / LGD), "%.3f%%" % (pd_[i - 1] * 100), _k(contrib[i - 1])])
        rows.append(["All %d intervals" % len(contrib), "", "", "", "%.2f%%" % (pd_.sum() * 100), _k(contrib.sum())])
        out.append(P("<b>CPTY_C, %s.</b> The rows with the largest contributions; the last row sums all intervals:" % lab))
        out.append(tbl(rows, widths=[0.9, 0.9, 0.9, 1.0, 1.0, 1.4], font=7.2))
    tc, tl = R["conventions"]["closeout"]["total"], R["conventions"]["level"]["total"]
    cco = R["conventions"]["closeout"]["by_cpty"]
    out.append(P("<b>Reading the numbers.</b> The CVA is small relative to the exposure because the default probability over a year or two is small (a BBB spread of about 100bp gives roughly 1.7%% a year at 60%% LGD) and because the exposure runs off quickly as trades mature. On the close-out definition the total CVA for the three netting sets is %s; on the uncollateralized level exposure it is %s, larger because the level exposure keeps the whole mark-to-market at risk (for CPTY_C the 500M bond forward: %s against %s). The close-out figure is what a margined counterparty would cost; the level figure is the price if no margin were ever called." % (_k(tc["CVA"]), _k(tl["CVA"]), _k(R["conventions"]["level"]["by_cpty"]["CPTY_C"]["CVA"]), _k(cco["CPTY_C"]["CVA"]))))
    out.append(P("<b>To settle at the next session.</b>"))
    out.append(B(["<b>Exposure definition for CVA.</b> Confirm that CVA should be on the brief's margined close-out exposure, with the uncollateralized figure as an upper bound, or whether Capitolis prices CVA on the level exposure.",
                  "<b>Counterparty credit.</b> Real ratings or CDS for CPTY_A, CPTY_B and CPTY_C (the BBB proxy drives everything; the sensitivity of the total to the rating is in the table of Section 8.1). Whether a sector or region adjustment is wanted.",
                  "<b>Capitolis' own credit and funding.</b> DVA and FVA are computed on assumptions (own credit BBB, funding spread equal to own spread); they need a Capitolis curve, and a decision on whether DVA is recognised at all (Basel CVA capital ignores it).",
                  "<b>Wrong-way risk.</b> The independence of exposure and default is assumed. Is a dependence model wanted, and for which counterparties (an equity swap counterparty that is itself an equity-sensitive institution)?",
                  "<b>Capital.</b> SA-CVA is computed with the m_CVA = 1 multiplier; agree whether the reduced basic approach (BA-CVA) or the standardised approach is the reference, and whether hedges should be included.",
                  "<b>Margin terms.</b> Threshold, minimum transfer amount and initial margin are not in the data; the CVA under those terms would sit between the two exposure definitions shown."]))
    return out


# ---------------------------------------------------------------- risky bond
def risky_bond_section(doc):
    p = os.path.join(PROC, "risky_bond_sample.json")
    if not os.path.exists(p):
        return []
    R = _j("risky_bond_sample.json")
    e = R["exposure"]
    out = [P("<b>Extra credit: risky bonds.</b> The brief invites risky bonds and CDS data for new sample trades. No CDS quotes were obtainable, so the issuer credit curve is a proxy built the same way as the counterparty spreads: ICE BofA BBB option-adjusted spreads (%s) with the pricing library's credit-triangle survival curve (recovery %.0f%%). A sample long forward on a 5%% BBB corporate bond (25M notional, forward date %s; trade_data/samples/, not part of the ESF book) is priced with and without issuer credit, and simulated with the issuer curve re-anchored at every node with the same term structure (deterministic spreads)." % (", ".join("%sy %.0fbp" % (k, v) for k, v in R["bbb_spreads_bp"].items()), R["recovery"] * 100, R["forward_date"]))]
    rows = [["Quantity", "Risk-free bond", "Risky bond (issuer credit)"],
            ["t = 0 NPV of the forward", format(R["npv_risk_free"], ",.0f"), format(R["npv_risky"], ",.0f")],
            ["Forward clean price", "%.4f" % R["forward_clean_risk_free"], "%.4f" % R["forward_clean_risky"]],
            ["Issuer credit charge at t = 0", "-", format(R["credit_charge"], ",.0f")],
            ["CS01 (NPV change per +1bp of issuer spread)", "-", format(R["cs01"], ",.0f")],
            ["Close-out MPE99 (counterparty exposure)", _m(e["risk_free"]["MPE99_closeout"]), _m(e["risky"]["MPE99_closeout"])],
            ["Peak level PFE99 (uncollateralized)", _m(max(e["risk_free"]["level_PFE99"])), _m(max(e["risky"]["level_PFE99"]))]]
    out.append(tbl(rows, widths=[3.0, 1.6, 2.0], font=7.4))
    out.append(P("Two things are distinct and should not be confused: the issuer credit charge, which is the credit risk of the bond's issuer and lowers the value of the forward, and the counterparty CVA on the trade, which is the credit risk of the other party and is computed as in Section 8. What is still missing is issuer credit as a stochastic factor (spreads are deterministic here) and CDS instruments themselves, for which the pricing library has no pricer.", SMALL))
    return out
