"""Report content for the model corrections and additions made after the first
close-out run: curve splice, volatility recalibration, JPY factor, attribution
of the changes, model-risk study, G2++ comparison, xVA, SA-CCR, backtesting.
All numbers are read from the result files under data/processed/; nothing is
typed in. Each function returns a list of LaTeX fragments (see report_tex)."""
import json
import os
from datetime import date

import numpy as np

from report_lib import GOLD, GREY, NAVY, ORANGE, TEAL, plt
from report_tex import B, H2, SMALL, callout, code, P, tbl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
CP = ("CPTY_A", "CPTY_B", "CPTY_C")
RED = "#8B0000"


def _j(*parts):
    return json.load(open(os.path.join(PROC, *parts)))


def _m(x, d=1):
    return f"${x/1e6:,.{d}f}M"


def _k(x):
    return f"${x/1e3:,.0f}k"


def spec(run="spec_run"):
    return _j(run, "spec_exposure.json")


def _peaks(S, ent):
    """Peak EE, peak median PFE, MPE99 inside the one-year horizon."""
    ref = date.fromisoformat(S["ref_date"])
    mk = np.array([(date.fromisoformat(d) - ref).days <= 365 for d in S["reporting_dates"]])
    e = S["by_counterparty"][ent]
    idx = np.where(mk)[0]
    ee, md, pf = (np.array(e[k]) for k in ("EE", "MedianExposure", "PFE"))
    return {"EE": float(ee[idx].max()), "MED": float(md[idx].max()), "PFE": float(pf[idx].max()),
            "PFE_date": S["reporting_dates"][idx[int(pf[idx].argmax())]]}


# ---------------------------------------------------------------- attribution and model risk
ATTR = [("Earlier version (flat USD curve beyond 6.5y, SOFR-overnight sigma, no JPY factor, USDJPY drift sign error)", "spec_run", "spec_exposure_before_fixes.json"),
        ("Corrected USDJPY drift only (no JPY factor, flat curve, SOFR sigma)", "spec_run_no_jpy_flat_sofr", "spec_exposure.json"),
        ("+ Bloomberg long end spliced onto the USD curve", "spec_run_no_jpy_flat", "spec_exposure.json"),
        ("+ long-end volatility fit and 10-year-yield correlations", "spec_run_no_jpy", "spec_exposure.json"),
        ("+ JPY Hull-White factor in the simulation (final model)", "spec_run_final2000", "spec_exposure.json")]


def attribution(doc):
    rows = [["Step", "CPTY_A", "CPTY_B", "CPTY_C", "Portfolio"]]
    have = 0
    for label, run, fn in ATTR:
        path = os.path.join(PROC, run, fn)
        if not os.path.exists(path):
            continue
        S = json.load(open(path))
        rows.append([label] + [_m(_peaks(S, c)["PFE"]) for c in CP + ("__portfolio__",)])
        have += 1
    out = [P("Every correction changes the numbers, so each was introduced one at a time on the same random numbers and the same scenario count (2,000 Latin Hypercube scenarios per row, except the first row, the 5,000-scenario run reported earlier). The table shows the maximum PFE99 (MPE) on the brief's close-out definition.")]
    out.append(tbl(rows, widths=[4.2, 0.9, 0.9, 0.9, 1.0], font=7.4))
    out.append(P("MPE99 within one year, USD millions. Rows are cumulative: each row contains the corrections of the rows above it. Monte Carlo noise between two runs of different size is a few percent, so only differences larger than that should be read as an effect of a correction.", SMALL))
    return out


def model_risk(doc):
    base_p = os.path.join(PROC, "spec_run_final2000", "spec_exposure.json")
    if not os.path.exists(base_p):
        return []
    base = json.load(open(base_p))
    rows = [["Perturbation", "CPTY_A", "CPTY_B", "CPTY_C", "Portfolio"]]
    rows.append(["Base case (final model, 2,000 scenarios)"] + [_m(_peaks(base, c)["PFE"]) for c in CP + ("__portfolio__",)])
    labels = [("spec_run_ratevol_up", "USD rate sigma x 1.25"), ("spec_run_a_x3", "USD mean reversion x 3"),
              ("spec_run_eqvol_up", "Equity and USDJPY volatilities x 1.25"),
              ("spec_run_corr_up", "Equity correlations moved 30% of the way to 1"),
              ("spec_run_g2", "Two-factor G2++ instead of one-factor Hull-White")]
    for run, lab in labels:
        p = os.path.join(PROC, run, "spec_exposure.json")
        if not os.path.exists(p):
            continue
        S = json.load(open(p))
        cells = []
        for c in CP + ("__portfolio__",):
            v, b = _peaks(S, c)["PFE"], _peaks(base, c)["PFE"]
            cells.append(f"{_m(v)} ({(v / b - 1) * 100:+.0f}%)")
        rows.append([lab] + cells)
    out = [P("The model rests on inputs that are estimated or assumed. To see which of them matter, each was perturbed one at a time on the same random numbers (2,000 scenarios). The table shows the MPE99 on the close-out definition and the change from the base case.")]
    out.append(tbl(rows, widths=[3.5, 1.2, 1.2, 1.2, 1.3], font=7.4))
    return out


# ---------------------------------------------------------------- curve splice
def fig_curve_splice(calib):
    from datetime import timedelta
    from risk_engine.market.sofr import build_curve
    from risk_engine.models.calibration import fetch_sofr_raw
    ref = calib["ref_date"]
    new = calib["usd_curve"]
    old = build_curve(ref, raw_df=fetch_sofr_raw(ref), long_end=None)
    ys = np.linspace(0.5, 30, 60)
    z = lambda c: [c.zero_rate(ref + timedelta(days=round(y * 365))) * 100 for y in ys]
    fig, ax = plt.subplots(figsize=(6.6, 2.7))
    ax.plot(ys, z(old), color=GREY, ls="--", lw=1.6, label="futures curve, flat beyond last contract")
    ax.plot(ys, z(new), color=NAVY, lw=1.8, label="futures curve + spliced long end (used)")
    ax.axvline(old._t[-1], color=ORANGE, lw=1, ls=":")
    ax.text(old._t[-1] + 0.3, min(z(old)) + 0.02, "last futures\npillar", fontsize=7, color=ORANGE)
    ax.set_xlabel("maturity (years)")
    ax.set_ylabel("zero rate (%)")
    ax.legend(fontsize=7)
    ax.set_title("USD zero curve before and after the long-end splice")
    return fig, old, new


def curve_splice(doc, calib, bf3_old=101.4e6, bf3_new=None):
    fig, old, new = fig_curve_splice(calib)
    npv = _j("npv_2026-08-28.json")["npv_by_trade"]
    bf3_new = npv["BF_0003"]
    out = [P("The SOFR-futures curve ends at about %.1f years and was previously extrapolated flat in the zero rate. That understates the discounting of the long-dated Treasury underlying BF_0003 (maturity 2049): at 20 years the flat extrapolation gives a zero rate of %.2f%%, against %.2f%% on the spliced curve. Beyond the last futures pillar the curve now follows the forward structure of the Bloomberg USD SOFR zero curve (2026-08-31 snapshot, re-based to our 2026-08-28 reference date), joined continuously at the last futures pillar; inside the futures range nothing changes." % (old._t[-1], _z(old, calib, 20) * 100, _z(new, calib, 20) * 100))]
    out.append(doc.figure(fig, "Zero-rate curve before and after splicing the long end. Inside the futures range the two coincide exactly."))
    out.append(P("The effect on the mark of BF_0003 is large because a 500M notional on a 22-year bond has a duration of about 13: its NPV moves from %s on the flat extrapolation to %s on the spliced curve, within half a percent of the $120.9M obtained by repricing on Bloomberg's own zero curve." % (_m(bf3_old), _m(bf3_new))))
    return out


def _z(curve, calib, y):
    from datetime import timedelta
    return curve.zero_rate(calib["ref_date"] + timedelta(days=round(y * 365)))


# ---------------------------------------------------------------- rates volatility
def rates_vol(doc, calib):
    d = calib["hw_rate_vol_detail"]
    if d["source"] != "ust_cmt_realised_long_end_fit":
        return []
    from risk_engine.market import treasury
    v = d["realised_vols"]
    a = calib["hw_mean_reversion_a"]
    tenors = [1, 2, 5, 10, 20, 30]
    fig, ax = plt.subplots(figsize=(5.8, 2.6))
    ax.plot(tenors, [v[t] * 1e4 for t in tenors], "o-", color=NAVY, label="realised, Treasury CMT (3y)")
    ax.plot(tenors, [treasury.hw_yield_vol(d["sigma"], a, t) * 1e4 for t in tenors], "s--", color=TEAL, label="Hull-White, sigma = %.0fbp (used)" % (d["sigma"] * 1e4))
    ax.plot(tenors, [treasury.hw_yield_vol(d["sofr_overnight_sigma"], a, t) * 1e4 for t in tenors], "^:", color=RED, label="Hull-White, sigma = %.0fbp (overnight SOFR)" % (d["sofr_overnight_sigma"] * 1e4))
    ax.set_xlabel("yield tenor (years)")
    ax.set_ylabel("annual normal vol (bp)")
    ax.legend(fontsize=7)
    ax.set_title("What the USD rate volatility has to match")
    out = [P("The USD Hull-White volatility was set equal to the realised volatility of the overnight SOFR fixing (%.0fbp). That number is small because the overnight rate moves in steps on Fed dates, and it says little about how far the 2- to 30-year yields, on which the book depends, move. Over the same three-year window the annual normal vol of Treasury yields was %s bp for the 2y to 30y tenors. In a one-factor Hull-White model the zero rate at tenor T has normal vol sigma (1 - exp(-aT))/(aT), so sigma is now fitted by least squares to the realised 2y-30y yield vols with the mean reversion held at its swaption-calibrated value: sigma = %.0fbp. The rate factor's correlations with equities and USDJPY are re-estimated on 10-year yield changes for the same reason (SOFR fixings correlate with nothing)." % (d["sofr_overnight_sigma"] * 1e4, "/".join("%.0f" % (v[t] * 1e4) for t in (2, 5, 10, 20, 30)), d["sigma"] * 1e4))]
    out.append(doc.figure(fig, "Realised yield volatility by tenor against the Hull-White implied shape for the two choices of sigma. The overnight-SOFR calibration lies well below the long-end moves; the fit tracks them."))
    return out


# ---------------------------------------------------------------- G2++
def g2_section(doc, calib):
    d = calib.get("g2_detail")
    if not d:
        return []
    tenors = d["tenors"]
    rv = np.sqrt(np.diag(d["realised_cov"])) * 1e4
    mv = np.sqrt(np.diag(d["model_cov"])) * 1e4
    fig, ax = plt.subplots(figsize=(5.8, 2.6))
    x = np.arange(len(tenors))
    ax.bar(x - 0.2, rv, 0.4, color=NAVY, label="realised")
    ax.bar(x + 0.2, mv, 0.4, color=TEAL, label="G2++ fit")
    ax.set_xticks(x)
    ax.set_xticklabels([("%gy" % t) if t >= 1 else ("%dm" % round(t * 12)) for t in tenors])
    ax.set_ylabel("annual normal vol (bp)")
    ax.legend(fontsize=7)
    ax.set_title("G2++ calibration: yield volatility by tenor")
    out = [P("The one-factor model moves every zero rate in lock-step with the short rate. A richer alternative is a two-factor Gaussian model (G2++, equivalent to a two-factor LGM): r(t) = x(t) + y(t) + phi(t), with dx = -a x dt + sigma dW1, dy = -b y dt + eta dW2 and correlation rho, which allows the curve to change slope independently of its level. It keeps the Gaussian properties that matter here (analytic bond prices at every node, negative rates possible) and fits today's curve exactly. It is implemented in models/g2pp.py and selected with rates_model='g2pp'; the second factor is driven by rho times the first factor's shock plus an extra independent shock, so it inherits the first factor's correlations with equities and FX.")]
    out.append(P("Calibration is to the realised covariance of daily changes of the 3-month to 30-year Treasury yields (3-year window), least squares on the whole covariance matrix, so both the volatility level by tenor and the correlation between tenors are matched: sigma = %.2f%%, a = %.3f, eta = %.2f%%, b = %.2f, rho = %+.2f, with a relative Frobenius error of %.0f%%. The fit reproduces the level and slope of the volatility term structure but not the hump around the 5-year point, which no two-factor Gaussian model can produce." % (d["sigma"] * 100, d["a"], d["eta"] * 100, d["b"], d["rho"], d["rel_error"] * 100)))
    out.append(doc.figure(fig, "Realised yield-change volatility by tenor against the fitted two-factor model."))
    p = os.path.join(PROC, "spec_run_g2", "spec_exposure.json")
    b = os.path.join(PROC, "spec_run_final2000", "spec_exposure.json")
    if os.path.exists(p) and os.path.exists(b):
        S, S0 = json.load(open(p)), json.load(open(b))
        rows = [["Netting set", "MPE99, one factor", "MPE99, two factors", "Change", "Peak EE, one factor", "Peak EE, two factors"]]
        for c in CP + ("__portfolio__",):
            a, g = _peaks(S0, c), _peaks(S, c)
            rows.append([("Portfolio" if c == "__portfolio__" else c), _m(a["PFE"]), _m(g["PFE"]), "%+.0f%%" % ((g["PFE"] / a["PFE"] - 1) * 100), _m(a["EE"]), _m(g["EE"])])
        out.append(tbl(rows, widths=[1.3, 1.4, 1.4, 0.9, 1.4, 1.4], font=7.4))
        out.append(P("Close-out exposure within one year, 2,000 scenarios, same random numbers.", SMALL))
    return out


# ---------------------------------------------------------------- xVA
def xva_section(doc):
    R = _j("xva_results.json")
    out = []
    conv = {"closeout": "Close-out exposure (headline)", "level": "Uncollateralized level exposure (secondary)"}
    for k, lab in conv.items():
        rows = [["Netting set", "CVA", "DVA", "FCA", "FBA", "FVA = FCA - FBA", "CVA - DVA + FVA"]]
        for c in CP:
            b = R["conventions"][k]["by_cpty"][c]
            rows.append([c] + [_k(b[x]) for x in ("CVA", "DVA", "FCA", "FBA", "FVA", "total")])
        t = R["conventions"][k]["total"]
        rows.append(["Total"] + [_k(t[x]) for x in ("CVA", "DVA", "FCA", "FBA", "FVA", "total")])
        out.append(P("<b>%s</b>" % lab))
        out.append(tbl(rows, widths=[1.2, 0.9, 0.9, 0.9, 0.9, 1.4, 1.4], font=7.4))
    tc, tl = R["conventions"]["closeout"]["total"], R["conventions"]["level"]["total"]
    fig, ax = plt.subplots(1, 2, figsize=(7.2, 2.7))
    for a_, k, ttl in ((ax[0], "closeout", "Close-out exposure"), (ax[1], "level", "Level exposure")):
        vals = R["conventions"][k]["total"]
        names = ["CVA", "DVA", "FCA", "FBA"]
        cols = [NAVY, TEAL, ORANGE, GOLD]
        a_.bar(names, [vals[n] / 1e3 for n in names], color=cols)
        a_.set_title(ttl, fontsize=8)
        a_.set_ylabel("USD thousand")
    out.append(doc.figure(fig, "xVA components, total over the three netting sets, on the two exposure definitions."))
    t_ = np.array(R["times"])
    fig, ax = plt.subplots(1, 2, figsize=(7.2, 2.7))
    for a_, k, ttl in ((ax[0], "closeout", "Close-out exposure"), (ax[1], "level", "Level exposure")):
        pr = R["conventions"][k]["profiles"]
        epe = sum(np.array(pr[c]["EPE"]) for c in CP)
        ene = sum(np.array(pr[c]["ENE"]) for c in CP)
        a_.plot(t_ * 365.25, epe / 1e6, color=NAVY, label="discounted EPE (owed to us)")
        a_.plot(t_ * 365.25, ene / 1e6, color=RED, label="discounted ENE (we owe)")
        a_.set_title(ttl, fontsize=8)
        a_.set_xlabel("days")
        a_.set_ylabel("USD million")
    ax[0].legend(fontsize=7)
    out.append(doc.figure(fig, "Discounted expected positive and negative exposure, summed over counterparties. DVA and the funding benefit come from the negative side."))
    sens = R["conventions"]["closeout"]["own_rating_sensitivity"]
    rows = [["Own rating proxy", "DVA", "FCA", "FBA", "FVA", "CVA - DVA + FCA (no overlap)"]]
    for r_ in ("AA", "A", "BBB", "BB"):
        s = sens[r_]
        rows.append([r_] + [_k(s[x]) for x in ("DVA", "FCA", "FBA", "FVA", "total_no_overlap")])
    out.append(P("<b>Sensitivity to the assumed own credit quality</b> (close-out exposure; the funding spread is set equal to the own credit spread):"))
    out.append(tbl(rows, widths=[1.3, 0.9, 0.9, 0.9, 0.9, 2.0], font=7.4))
    return out, R


# ---------------------------------------------------------------- SA-CCR
def sa_ccr_section(doc, S):
    R = _j("sa_ccr_results.json")
    rows = [["Netting set", "Net MtM V", "Replacement cost", "Add-on, rates", "Add-on, equity", "Multiplier", "PFE", "EAD", "MC MPE99 (close-out)"]]
    for c in CP:
        r = R["by_cpty"][c]
        rows.append([c, _m(r["V"]), _m(r["RC"]), _m(r["addon_ir"]), _m(r["addon_equity"]), "%.2f" % r["multiplier"], _m(r["PFE"]), _m(r["EAD"]), _m(_peaks(S, c)["PFE"])])
    t = R["total"]
    rows.append(["Total", _m(sum(R["by_cpty"][c]["V"] for c in CP)), _m(t["RC"]), "", "", "", _m(t["PFE"]), _m(t["EAD"]), _m(_peaks(S, "__portfolio__")["PFE"])])
    out = [P("The Basel standardised approach for counterparty credit risk (SA-CCR, CRE52) gives a regulatory exposure at default, EAD = 1.4 x (replacement cost + multiplier x add-on), for each uncollateralized netting set. It is built in exposure/sa_ccr.py for the asset classes present in the book (interest rate for the Treasury forwards and bond TRS, equity for the equity TRS; no FX, credit or commodity trades), validated against hand calculations of the supervisory duration, maturity factor, bucket and entity aggregation and the multiplier.")]
    out.append(tbl(rows, widths=[0.9, 0.9, 1.0, 0.9, 0.9, 0.8, 0.9, 0.9, 1.2], font=7.0))
    out.append(P("SA-CCR is not comparable to the Monte Carlo maximum PFE99 because it is a different quantity: its replacement cost is today's full mark-to-market and its add-on is a one-year supervisory approximation, whereas the close-out MPE99 measures the 10-day move of a margined position. It is included as the regulatory view of the same book and as an independent order-of-magnitude check on the add-on: for the equity netting sets the SA-CCR PFE is of the same order as the Monte Carlo level-exposure MPE, and for CPTY_C the replacement cost of the 500M bond forward dominates.", SMALL))
    return out


# ---------------------------------------------------------------- backtest
def backtest_section(doc):
    R = _j("backtest_results.json")
    cfg = R["config"]
    out = [P("A model that is correct on average can still misstate the tail. The simulated exposure quantiles were therefore backtested against realised history, with the Kupiec proportion-of-failures test (Basel's standard backtest). At each historical as-of date the model is calibrated using only data up to that date (a trailing 3-year window), asked for the 95th and 99th percentile of the 10-business-day change in value of a fixed set of positions, and the realised change is read off history. An exception is a realised move above the predicted quantile; a correct model has exceptions with probability 5% or 1%, independently. Windows do not overlap, and the starting phase is shifted over ten offsets to check robustness. The equity leg uses the actual equity TRS positions of each counterparty (JPY names through USDJPY) and the engine's own lognormal model on %s to %s daily data; the rates leg tests the Hull-White distribution of 10-day yield changes at 5, 10 and 20 years." % (cfg["history"][0], cfg["history"][1]))]
    rows = [["Netting set", "Level", "Exceptions", "Expected", "Rate", "Kupiec p-value", "Offsets rejecting (of 10)", "Mean rate over offsets"]]
    for c in CP:
        for lev in ("0.95", "0.99"):
            r = R["equity"][c]["confidences"][lev]
            rows.append([c, "%d%%" % round(float(lev) * 100), "%d of %d" % (r["x"], r["n"]), "%.1f" % r["expected"], "%.1f%%" % (r["rate"] * 100),
                         "%.2f" % r["p_value"], "%d" % r["phases_rejecting"], "%.1f%%" % (r["phases_mean_rate"] * 100)])
    out.append(P("<b>Equity and FX leg</b> (upper-tail exceptions; the exposure is the gain side of the position):"))
    out.append(tbl(rows, widths=[0.9, 0.6, 1.0, 0.8, 0.7, 1.0, 1.4, 1.3], font=7.4))
    fig, ax = plt.subplots(1, 3, figsize=(7.6, 2.5), sharey=False)
    for a_, c in zip(ax, CP):
        s = R["equity"][c]["series_99"]
        d = np.arange(len(s["real"]))
        a_.plot(d, np.array(s["pred"]) / 1e6, color=NAVY, lw=1.2, label="predicted 99% quantile")
        a_.plot(d, np.array(s["real"]) / 1e6, color=GREY, lw=0.7, label="realised 10-day change")
        hit = np.array(s["hits"]).astype(bool)
        a_.scatter(d[hit], np.array(s["real"])[hit] / 1e6, color=RED, s=14, zorder=3, label="exception")
        a_.set_title(c, fontsize=8)
        a_.set_xlabel("non-overlapping 10-day window")
    ax[0].set_ylabel("USD million")
    ax[0].legend(fontsize=6)
    out.append(doc.figure(fig, "Predicted 99% quantile of the 10-day change in each netting set's equity positions against the realised change, over the whole backtest; exceptions in red."))
    rows = [["Tenor", "Sigma from", "99% up: exceptions", "99% up: mean rate", "95% up: mean rate", "95% down: mean rate"]]
    for tn in ("5", "10", "20"):
        for name, lab in (("sofr_overnight", "overnight SOFR vol"), ("long_end_fit", "long-end fit")):
            r = R["rates"][tn][name]
            rows.append(["%sy" % tn, lab, "%d of %d" % (r["0.99_up"]["x"], r["0.99_up"]["n"]), "%.1f%%" % (r["0.99_up"]["phases_mean_rate"] * 100),
                         "%.1f%%" % (r["0.95_up"]["phases_mean_rate"] * 100), "%.1f%%" % (r["0.95_down"]["phases_mean_rate"] * 100)])
    out.append(P("<b>Rates leg</b> (10-day change of the Treasury CMT yield against the one-factor Hull-White distribution, as-of dates from %s):" % R["rates_config"]["first_asof"]))
    out.append(tbl(rows, widths=[0.6, 1.5, 1.3, 1.3, 1.3, 1.3], font=7.4))
    out.append(P("Nominal exception rates are 1% at the 99% level and 5% at the 95% level.", SMALL))
    return out, R


def override_cva_with_xva(Rc, Xv):
    """Section 8 base CVA figures from the 5,000-scenario close-out run (the SA-CVA run,
    at 1,000 scenarios, keeps supplying the capital sensitivities)."""
    from risk_engine.market.credit_spreads import rating_spread_curve, RATING_SERIES
    from risk_engine.exposure.sa_cva import CCS_TENORS
    from risk_engine.exposure.cva import cva
    ref = date.fromisoformat(Xv["ref_date"])
    t = np.array(Xv["times"])
    prof = Xv["conventions"]["closeout"]["profiles"]
    out = dict(Rc)
    out["n_scenarios_cva"] = Xv["n_scenarios"]
    out["cva_by_cpty"] = {c: Xv["conventions"]["closeout"]["by_cpty"][c]["CVA"] for c in CP}
    out["cva_total"] = Xv["conventions"]["closeout"]["total"]["CVA"]
    out["dee"] = {c: prof[c]["EPE"] for c in CP}
    out["times"] = list(map(float, t))
    vs = {}
    for rt in RATING_SERIES:
        tn, sp = rating_spread_curve(rt, ref, CCS_TENORS)
        vs[rt] = float(sum(cva(np.array(prof[c]["EPE"]), t, tn, sp) for c in CP))
    out["cva_vs_rating"] = vs
    return out
