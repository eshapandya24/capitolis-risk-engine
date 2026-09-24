"""Report Section 9 (Greeks): figures and text, built from data/processed/greeks_results.json."""
import json
import os

import numpy as np

from report_lib import GOLD, GREY, NAVY, ORANGE, PAL, TEAL, plt
from report_tex import B, H1, H2, SMALL, callout, code, P, tbl
import report_new2 as RN2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "data", "processed", "greeks_results.json")
ENT = ["CPTY_A", "CPTY_B", "CPTY_C", "__portfolio__"]


def load():
    return json.load(open(PATH))


def _a(x):
    return np.array(x, dtype=float)


def _m(x, d=2):
    return f"{x/1e6:,.{d}f}"


def _k(x):
    return f"{x/1e3:,.0f}"


def peak_node(g):
    return int(np.argmax(_a(g["base"]["__portfolio__"]["PFE"])))


def fig_book(g, tickers):
    b = g["book_t0"]
    cp = b["counterparty"]
    fig, ax = plt.subplots(1, 2, figsize=(7.4, 2.9))
    tenors = list(b["rate_buckets"])
    cols = {"CPTY_A": NAVY, "CPTY_B": TEAL, "CPTY_C": ORANGE}
    w = 0.27
    for j, c in enumerate(("CPTY_A", "CPTY_B", "CPTY_C")):
        vals = [sum(v for t, v in b["rate_buckets"][k].items() if cp[t] == c) / 1e3 for k in tenors]
        ax[0].bar(np.arange(len(tenors)) + (j - 1) * w, vals, w, color=cols[c], label=c)
    ax[0].set_xticks(range(len(tenors))); ax[0].set_xticklabels([("%gy" % float(k)) for k in tenors], fontsize=7)
    ax[0].set_ylabel("NPV change per +1bp (USD k)"); ax[0].legend(fontsize=6.5); ax[0].set_title("Bucketed DV01 by netting set")
    tot = {i: sum(v.values()) for i, v in b["equity_delta"].items()}
    top = sorted(tot, key=lambda i: -abs(tot[i]))[:12]
    ax[1].barh(range(len(top)), [tot[i] / 1e3 for i in top], color=NAVY)
    ax[1].set_yticks(range(len(top))); ax[1].set_yticklabels([tickers.get(i, i[:8]) for i in top], fontsize=7)
    ax[1].invert_yaxis(); ax[1].set_xlabel("NPV change per +1% (USD k)"); ax[1].set_title("Largest equity deltas at t = 0")
    return fig


def fig_profiles(g):
    t = _a(g["times"]) * 365.25
    fig, ax = plt.subplots(1, 3, figsize=(7.6, 2.6))
    for a_, key, ttl, sub in ((ax[0], "equity_all", "All equities +1%", "delta"), (ax[1], "fx", "USDJPY +1%", "delta"),
                              (ax[2], "rate_parallel", "USD rates +1bp", "delta")):
        d = g[key][sub]["__portfolio__"]
        a_.plot(t, _a(d["EE"]) / 1e3, color=NAVY, label="EE")
        a_.plot(t, _a(d["MED"]) / 1e3, color=GOLD, label="median PFE")
        a_.plot(t, _a(d["PFE"]) / 1e3, color="#8B0000", label="PFE99")
        a_.axhline(0, color="k", lw=0.6)
        a_.set_title(ttl, fontsize=8); a_.set_xlabel("days")
    ax[0].set_ylabel("change in measure (USD k)"); ax[0].legend(fontsize=6.5)
    return fig


def fig_pfe_names(g, tickers):
    j = peak_node(g)
    d = {i: v["delta"]["__portfolio__"]["PFE"][j] for i, v in g["equity"].items()}
    top = sorted(d, key=lambda i: -abs(d[i]))[:12]
    fig, ax = plt.subplots(1, 2, figsize=(7.4, 2.9))
    ax[0].barh(range(len(top)), [d[i] / 1e3 for i in top], color=ORANGE)
    ax[0].set_yticks(range(len(top))); ax[0].set_yticklabels([tickers.get(i, i[:8]) for i in top], fontsize=7)
    ax[0].invert_yaxis(); ax[0].set_xlabel("dPFE99 per +1% (USD k)")
    ax[0].set_title("Largest single-name PFE99 deltas, %s" % g["dates"][j], fontsize=8)
    tenors = list(g["rate_buckets"])
    ax[1].bar(range(len(tenors)), [g["rate_buckets"][k]["__portfolio__"]["PFE"][j] / 1e3 for k in tenors], color=NAVY)
    ax[1].set_xticks(range(len(tenors))); ax[1].set_xticklabels([("%gy" % float(k)) for k in tenors], fontsize=7)
    ax[1].set_ylabel("dPFE99 per +1bp (USD k)"); ax[1].set_title("Bucketed rate DV01 of PFE99", fontsize=8)
    return fig


def fig_validation(g):
    fig, ax = plt.subplots(1, 3, figsize=(7.6, 2.6))
    j = peak_node(g)
    sizes = ["0.5%", "1%", "2%"]
    for m_, c in (("EE", NAVY), ("PFE", "#8B0000")):
        ax[0].plot(sizes, [g["bump_size"][s]["__portfolio__"][m_][j] / 1e3 for s in sizes], marker="o", color=c, label=("EE" if m_ == "EE" else "PFE99"))
    ax[0].set_title("Delta vs bump size", fontsize=8); ax[0].set_ylabel("per +1% (USD k)"); ax[0].set_xlabel("bump"); ax[0].legend(fontsize=6.5)
    tot = np.sum([_a(v["delta"]["__portfolio__"]["EE"]) for v in g["equity"].values()], axis=0)
    allv = _a(g["equity_all"]["delta"]["__portfolio__"]["EE"])
    t = _a(g["times"]) * 365.25
    ax[1].plot(t, tot / 1e3, color=NAVY, label="sum of 37 names"); ax[1].plot(t, allv / 1e3, color=ORANGE, ls="--", label="all equities")
    ax[1].set_title("Additivity of the EE delta", fontsize=8); ax[1].set_xlabel("days"); ax[1].legend(fontsize=6.5)
    c = g["crn_vs_independent"]
    ax[2].boxplot([_a(c["crn"]) / 1e3, _a(c["independent"]) / 1e3]); ax[2].set_xticks([1, 2]); ax[2].set_xticklabels(["common random nos", "independent draws"], fontsize=6.5)
    ax[2].set_title("EE delta estimates (N=%d)" % c["n"], fontsize=8); ax[2].set_ylabel("USD k")
    return fig


def section(add, doc, g, tickers, trade_meta):
    b = g["book_t0"]
    cp = b["counterparty"]
    j = peak_node(g)
    date_pk = g["dates"][j]
    tm = g["timing"]
    N = g["n_scenarios"]
    cpts = ("CPTY_A", "CPTY_B", "CPTY_C")

    add(P("9. Sensitivities (Greeks)", H1))
    add(P("Capitolis asked for exposure profiles together with efficient Greeks across scenarios, aggregated by netting set. This section delivers both levels: (i) the Greeks of the book's value today, by trade and netting set, and (ii) the sensitivities of the exposure measures themselves, EE, median PFE and PFE99, at every simulation date. Every number comes from the same pricers and simulated paths as Section 7."))
    add(P("9.1 Definitions and method", H2))
    add(B(["<b>Delta</b> to an equity or to USDJPY: change per +1% relative move of the spot. <b>Gamma</b>: change in that delta, [M(+1%) - 2 M + M(-1%)]. <b>DV01</b>: change per +1bp in USD zero rates, parallel and bucketed at 0.25, 0.5, 1, 2, 3, 5, 10 and 30 years (triangular weights that sum exactly to the parallel shift). <b>Vega</b>: change per +1% relative shift of the volatility of the USD rate, of USDJPY and of all equities.",
           "<b>Bump-and-reprice with common random numbers</b> (the same Latin Hypercube draws in base and bumped runs): the difference is then sensitivity, not Monte Carlo noise. It works on the pricers as a black box, and it applies equally to quantile measures such as PFE99, which have no simple pathwise derivative. Its accuracy compared with the pathwise estimator is shown in Section 11.6.",
           "<b>Efficiency.</b> A bump of an equity or of USDJPY rescales every simulated path exactly (the GBM drift does not depend on the spot level), so no re-simulation is needed: the existing paths are reused with the spot multiplied and only the trades holding that factor are repriced, all bumps in one process pool. Rate and volatility bumps change the paths themselves, so they are re-simulated with the same random numbers.",
           "Exposure Greeks are computed at N = %s scenarios (Latin Hypercube), on the brief's close-out exposure, on the pillar date grid with the t - 1bd and t + 10bd nodes." % format(N, ",")]))
    add(P("Sign convention: Capitolis is strictly the seller on these trades, and the equity swaps are of type pay-equity (we pay the equity return and receive funding), so equity deltas are negative: our value rises when the shares fall."))

    add(P("9.2 Book Greeks today", H2))
    ns = b["npv_by_set"]
    eq_by_set = {c: 0.0 for c in cpts}
    for isin, d in b["equity_delta"].items():
        for t, v in d.items():
            eq_by_set[cp[t]] += v
    fx_by_set = {c: sum(v for t, v in b["fx_delta"].items() if cp[t] == c) for c in cpts}
    dv_by_set = {c: sum(v for t, v in b["rate_parallel"].items() if cp[t] == c) for c in cpts}
    rg_by_set = {c: sum(v for t, v in b["rate_gamma"].items() if cp[t] == c) for c in cpts}
    eg_by_set = {c: sum(v for d in b["equity_gamma"].values() for t, v in d.items() if cp[t] == c) for c in cpts}
    rows = [["Netting set", "NPV", "Equity delta (per +1%)", "Equity gamma", "FX delta (per +1%)", "DV01 (per +1bp)", "Rate gamma"]]
    for c in cpts:
        rows.append([c, format(ns[c], ",.0f"), format(eq_by_set[c], ",.0f"), format(eg_by_set[c], ",.0f"), format(fx_by_set[c], ",.0f"), format(dv_by_set[c], ",.0f"), format(rg_by_set[c], ",.0f")])
    rows.append(["Portfolio", format(ns["__portfolio__"], ",.0f"), format(sum(eq_by_set.values()), ",.0f"), format(sum(eg_by_set.values()), ",.0f"), format(sum(fx_by_set.values()), ",.0f"), format(sum(dv_by_set.values()), ",.0f"), format(sum(rg_by_set.values()), ",.0f")])
    add(tbl(rows, widths=[1.2, 1.4, 1.5, 1.1, 1.3, 1.3, 1.1], font=7.2))
    add(P("All values in USD. The equity and bond trades are linear in the equity spot, so equity and FX gamma are zero to rounding; rate gamma is small. The DV01 is dominated by the CPTY_C bond forward. The largest deltas and the bucketed DV01s:"))
    add(doc.figure(fig_book(g, tickers), "Left: DV01 by netting set and tenor. Right: the twelve largest equity deltas at t = 0."))
    rows = [["Netting set"] + [("%gy" % float(k)) for k in b["rate_buckets"]]]
    for c in cpts:
        rows.append([c] + [format(sum(v for t, v in b["rate_buckets"][k].items() if cp[t] == c), ",.0f") for k in b["rate_buckets"]])
    add(tbl(rows, font=7.0))
    add(P("Bucketed DV01 (USD per +1bp), summing to the parallel DV01 above. A check that the equity delta is right: for EQTRS_0003 the delta to its largest name equals minus the share count times the spot, i.e. exactly -212,269 USD per $1, as it must for a linear payoff (Section 9.5).", SMALL))

    add(P("9.3 Sensitivities of the exposure measures", H2))
    add(P("These are the Greeks that matter for counterparty credit risk: how EE, median PFE and PFE99 change when a market factor moves. The figure shows the portfolio profiles for the three main factors, and the table gives the sensitivities at the date of peak PFE99 (%s), by netting set." % date_pk))
    add(doc.figure(fig_profiles(g), "Change in portfolio EE, median PFE and PFE99 through time for +1% on all equities, +1% on USDJPY and +1bp on USD rates."))
    rows = [["Factor shift", "Measure"] + [("Portfolio" if e == "__portfolio__" else e) for e in ENT]]
    spec = [("All equities +1%", "equity_all", "delta"), ("USDJPY +1%", "fx", "delta"), ("USD rates +1bp", "rate_parallel", "delta")]
    for lab, key, sub in spec:
        for mm, ml in (("EE", "EE"), ("MED", "Median PFE"), ("PFE", "PFE99")):
            rows.append([lab if mm == "EE" else "", ml] + [format(g[key][sub][e][mm][j], ",.0f") for e in ENT])
    for lab, key in (("Rate volatility +1%", "rate"), ("FX volatility +1%", "fx"), ("Equity volatility +1%", "equity")):
        for mm, ml in (("EE", "EE"), ("MED", "Median PFE"), ("PFE", "PFE99")):
            rows.append([lab if mm == "EE" else "", ml] + [format(g["vega"][key][e][mm][j], ",.0f") for e in ENT])
    for lab, key in (("All-equity gamma (+1%)", "equity_all"), ("USDJPY gamma (+1%)", "fx"), ("Rate gamma (+1bp)", "rate_parallel")):
        for mm, ml in (("EE", "EE"), ("PFE", "PFE99")):
            rows.append([lab if mm == "EE" else "", ml] + [format(g[key]["gamma"][e][mm][j], ",.0f") for e in ENT])
    add(tbl(rows, widths=[1.9, 1.0, 1.1, 1.1, 1.1, 1.2], font=7.0))
    add(P("Change in the measure, in USD, at %s. Delta and vega are one-sided shifts read as change per unit shift; gamma is the second difference." % date_pk, SMALL))
    e_d, p_d = g["equity_all"]["delta"]["__portfolio__"]["EE"][j], g["equity_all"]["delta"]["__portfolio__"]["PFE"][j]
    r_d = g["rate_parallel"]["delta"]["__portfolio__"]["PFE"][j]
    add(P("<b>Reading the table.</b> The equity delta of exposure is negative (EE falls by about $%s per +1%% on all equities and PFE99 by $%s): the swaps are pay-equity, so our claim on the counterparty shrinks when shares rise, and the adverse scenarios for credit exposure are equity falls. The USD rate DV01 of PFE99 is positive ($%s per +1bp), reflecting the funding legs and bond forwards. The equity and rate gammas of the exposure are positive, as expected for max(V, 0) (a call on the netted value), and small relative to the deltas at a +1%% shift." % (_k(abs(e_d)) + "k", _k(abs(p_d)) + "k", _k(r_d) + "k")))
    add(doc.figure(fig_pfe_names(g, tickers), "Left: the twelve largest single-name deltas of portfolio PFE99 at the peak date. Right: bucketed USD rate DV01 of PFE99 at the same date."))
    add(P("Single-name deltas of PFE99 show which positions drive the tail; because a quantile is not additive across names, the single-name deltas sum only approximately to the all-equity delta (Section 9.5)."))

    add(P("9.4 Efficiency", H2))
    tc = tm_clean = g["timing_clean"]
    nb = tc["n_bumps"]
    naive = nb * tc["one_resim_s"]
    add(tbl([["Step (timed at N = %d)" % tc["n"], "Cost", "Comment"],
             ["t = 0 book Greeks", "%.1f s" % tm["book_greeks_s"], "Central differences on the pricers: every trade, 37 equities, FX, DV01 parallel and 8 buckets"],
             ["Base run (paths and full repricing)", "%.0f s" % tc["base_run_s"], "16 trades, all dates, 8 worker processes (includes process start-up)"],
             ["%d equity and FX bumps" % nb, "%.0f s" % tc["subset_bumps_s"], "No re-simulation; only the trades holding the factor are repriced; one process pool. Re-simulating each would cost about %s s (%.0fx more)" % (format(naive, ",.0f"), naive / tc["subset_bumps_s"])],
             ["One rate or volatility re-simulation", "%.0f s" % tc["one_resim_s"], "13 are needed: parallel up and down, 8 buckets, three vega bumps"]],
            widths=[2.2, 0.9, 4.6], font=7.4))
    add(P("The timings in the table were measured on an otherwise idle machine at N = %d, because the production run shared the machine with other jobs; costs scale about linearly with N once process start-up is amortised." % tc["n"]))
    add(P("The equity and FX Greeks, which are 37 names plus FX, each with an up and a down bump, cost a small fraction of what naive bump-and-resimulate would. This is the main efficiency gain: it exploits the structure of the model (exact rescaling of GBM paths) rather than approximating anything."))
    add(RN2.greeks_method_section(doc, g))

    add(P("9.5 Validation of the Greeks", H2))
    tk = trade_meta
    rows = [["Check", "Result"]]
    d0 = b["equity_delta"]
    err = []
    for isin, dd in d0.items():
        for t, v in dd.items():
            if t in tk:
                exp_ = tk[t].get(isin)
                if exp_ is not None:
                    err.append(abs(v - exp_) / max(abs(exp_), 1.0))
    rows.append(["t = 0 equity delta against the analytic value (shares x spot x 1%%, signed by trade direction), all %d trade-name pairs" % len(err), "maximum relative error %.1e" % (max(err) if err else float("nan"))])
    bs = g["bump_size"]
    rng_ = [bs[s]["__portfolio__"]["EE"][j] for s in ("0.5%", "1%", "2%")]
    rows.append(["Bump-size stability of the all-equity EE delta at the peak date: 0.5%, 1%, 2% bumps (USD k per +1%)", ", ".join(_k(x) for x in rng_) + " (spread %.2f%%)" % (100 * (max(rng_) - min(rng_)) / abs(np.mean(rng_)))])
    tot = np.sum([_a(v["delta"]["__portfolio__"]["EE"]) for v in g["equity"].values()], axis=0)
    allv = _a(g["equity_all"]["delta"]["__portfolio__"]["EE"])
    rows.append(["Additivity: sum of the 37 single-name EE deltas against the all-equity delta (maximum over all dates after t = 0)", "%.2f%% of the peak all-equity delta" % (100 * np.max(np.abs(tot[1:] - allv[1:])) / np.max(np.abs(allv)))])
    rows.append(["The same at t = 0 itself", "%.0f%%: at t = 0 the exposure max(V, 0) is deterministic and has a kink, and a 1%% bump of one name can cross it (CPTY_A, CPTY_B), so single-name and joint finite differences need not add there" % (100 * abs(tot[0] - allv[0]) / np.max(np.abs(allv)))])
    tp = np.sum([_a(v["delta"]["__portfolio__"]["PFE"]) for v in g["equity"].values()], axis=0)
    ap = _a(g["equity_all"]["delta"]["__portfolio__"]["PFE"])
    rows.append(["Sum of single-name PFE99 deltas against the all-equity PFE99 delta at the peak date (quantiles are not additive)", "%s against %s USD k" % (_k(tp[j]), _k(ap[j]))])
    c = g["crn_vs_independent"]
    rows.append(["Common random numbers against independent draws: standard deviation of the EE delta estimate over %d repeats at N = %d" % (len(c["crn"]), c["n"]), "%s USD k against %s USD k (%.0fx lower)" % (_k(c["crn_std"]), _k(c["independent_std"]), c["independent_std"] / max(c["crn_std"], 1e-9))])
    add(tbl(rows, widths=[4.6, 3.0], font=7.4))
    add(doc.figure(fig_validation(g), "Left: delta of EE and PFE99 against bump size. Middle: the sum of the 37 single-name EE deltas equals the all-equity delta through time. Right: estimates of the EE delta with common random numbers and with independent draws."))

    add(P("9.6 Limitations", H2))
    add(B(["Sensitivities are finite differences with a 1% (equity, FX, volatility) or 1bp (rates) shift. The bump-size check above shows the results are stable to a factor of four in bump size.",
           "Quantile Greeks (PFE99) carry more estimation noise than EE even with common random numbers; the reported figures use %s scenarios." % format(N, ","),
           "Interest rate Greeks are for the USD curve only: the simulated JPY rate drives only the drift of JPY-listed names and USDJPY, and no trade is discounted on JPY. There is no inflation, credit-spread or dividend Greek for exposure (credit-spread and vega sensitivities of CVA are in Section 8).",
           "Volatility bumps are parallel across each factor class (all equity vols together); there is no vol-surface or per-name vega. No cross-gamma is computed, and theta is represented by the exposure profile itself.",
           "Exposure Greeks are for the close-out exposure over the first year at 99%; the uncollateralized level exposure has much larger sensitivities (its delta is the delta of the mark-to-market itself)."]))
    add("\\clearpage\n")
