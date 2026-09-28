"""Extra figures for the summary deck (docs/latex/deck.tex) not already produced
by build_report.py: the old-vs-new DV01 bucket comparison and the sampling-scheme
Greeks-noise comparison. Writes into docs/latex/figures/ alongside the report's
own fig01..fig44.pdf so the deck can reference them by the same relative path.
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
OUT = os.path.join(ROOT, "docs", "latex", "figures")

NAVY, TEAL, ORANGE, GOLD, GREY = "#1F3A5F", "#2A9D8F", "#E76F51", "#E9C46A", "#8D99AE"
plt.rcParams.update({"font.size": 9, "axes.titlesize": 10, "axes.labelsize": 9, "legend.fontsize": 8,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                     "grid.alpha": 0.25, "figure.dpi": 150})


def dv01_comparison():
    g = json.load(open(os.path.join(PROC, "greeks_results.json")))
    dj = json.load(open(os.path.join(PROC, "dv01_jacobian.json")))
    tenors = ["0.25", "0.5", "1", "2", "3", "5", "10", "30"]
    pk = int(np.argmax(np.array(g["base"]["__portfolio__"]["PFE"])))
    old = [g["rate_buckets"][str(float(t) if "." in t else int(t))]["__portfolio__"]["PFE"][pk] for t in tenors]
    new = [dj["par_bucket_dv01"][t]["__portfolio__"]["PFE"] for t in tenors]
    x = np.arange(len(tenors))
    fig, ax = plt.subplots(figsize=(6.6, 3.0))
    ax.bar(x - 0.18, old, width=0.36, color=GREY, label="Old: triangular zero-rate grid")
    ax.bar(x + 0.18, new, width=0.36, color=NAVY, label="New: par-instrument (Jacobian)")
    ax.set_xticks(x)
    ax.set_xticklabels([t + "y" for t in tenors])
    ax.set_ylabel("Portfolio PFE99 DV01, USD per +1bp")
    ax.axhline(0, color="k", lw=0.6)
    ax.legend(frameon=False)
    ax.set_title("DV01 by tenor bucket: same total risk, different shape")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_dv01_compare.pdf"))
    print("wrote fig_dv01_compare.pdf")


def sampling_scheme_bar():
    d = json.load(open(os.path.join(PROC, "greeks_sampling.json")))

    def sd(grp, c, m):
        return {k: float(np.std([r[grp][c][m] for r in rows], ddof=1)) for k, rows in d["methods"].items()}

    specs = [("Equity EE\n(CPTY_C)", "equity", "CPTY_C", "EE"),
             ("Equity PFE99\n(portfolio)", "equity", "__portfolio__", "PFE"),
             ("USDJPY median\n(portfolio)", "fx", "__portfolio__", "MED")]
    methods = ["pseudo_random", "antithetic", "moment_matched", "sobol", "latin_hypercube"]
    labels = ["Pseudo-\nrandom", "Anti-\nthetic", "Moment-\nmatched", "Sobol", "Latin\nHypercube"]
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.6))
    for ax, (title, grp, c, m) in zip(axes, specs):
        s = sd(grp, c, m)
        base = s["pseudo_random"]
        vals = [s[k] / base for k in methods]
        colors_ = [NAVY if k == "latin_hypercube" else GREY for k in methods]
        ax.bar(range(len(methods)), vals, color=colors_)
        ax.axhline(1.0, color="k", lw=0.6, ls="--")
        ax.set_xticks(range(len(methods)))
        ax.set_xticklabels(labels, fontsize=6.5)
        ax.set_title(title, fontsize=8)
        ax.set_ylabel("Noise / pseudo-random", fontsize=7.5)
    fig.suptitle("Sampling scheme vs Greeks noise: no consistent winner", fontsize=9.5)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_sampling_greeks.pdf"))
    print("wrote fig_sampling_greeks.pdf")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    dv01_comparison()
    sampling_scheme_bar()
