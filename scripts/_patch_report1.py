import re
p = "scripts/build_report.py"
s = open(p, encoding="utf-8").read()


def rep(a, b, count=1):
    global s
    assert a in s, "MISSING: " + a[:90]
    s = s.replace(a, b, count)


# ---- imports
s = re.sub(r"from report_lib import \(.*?\)\nfrom reportlab.lib.units import inch\n",
           "from report_lib import GOLD, GREY, NAVY, ORANGE, PAL, TEAL, plt\n"
           "from report_tex import (A, B, BODY, CAP, H1, H2, H3, SMALL, TOCH, PageBreak, Report, Spacer, callout,\n"
           "                        code, make_toc, P, tbl, titlepage)\n"
           "inch = 72\n", s, flags=re.S)

# ---- prof: drop 95
rep(', "P95": np.quantile(a, 0.95, axis=1),', ',')

# ---- measures illustration
rep('(np.median(x), "Median", GOLD),\n                        (np.quantile(x, 0.95), "PFE95", ORANGE), (np.quantile(x, CONF), "PFE99", "#8B0000")):',
    '(np.median(x), "Median PFE", GOLD),\n                        (np.quantile(x, CONF), "PFE99", "#8B0000")):')

# ---- fan-chart bands (distribution bands, not PFE): use 10-90 / 1-99
rep('q = np.quantile(r, [0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99], axis=0)', 'q = np.quantile(r, [0.01, 0.10, 0.25, 0.5, 0.75, 0.90, 0.99], axis=0)')
rep('label="5-95%")', 'label="10-90%")')
rep('q = np.quantile(arr, [0.05, 0.25, 0.5, 0.75, 0.95], axis=0)', 'q = np.quantile(arr, [0.01, 0.25, 0.5, 0.75, 0.99], axis=0)')
rep('q = np.quantile(r, [0.05, 0.5, 0.95], axis=0)', 'q = np.quantile(r, [0.01, 0.5, 0.99], axis=0)')
rep('with 5-95 and 25-75 percent bands', 'with 1-99 and 25-75 percent bands')

# ---- profiles figure
rep('        ax.plot(x, p["P95"] / 1e6, color=ORANGE, lw=1.2, label="PFE95")\n', '')
rep('color=GOLD, lw=1.8, label="Median")', 'color=GOLD, lw=1.8, label="Median PFE")')
rep('label="MPOR median")', 'label="MPOR median PFE")')

# ---- convergence figure (replace whole function)
new_conv = '''def fig_conv(D, meta):
    c99 = json.load(open(os.path.join(PROC, "convergence_study_tail_pfe99.json")))
    r99 = [r for r in c99["results"] if r["N"] != c99["N_pool"]]
    a = D["expo"]["__portfolio__"]
    jp = int(np.argmax(np.quantile(a, CONF, axis=1)))
    x = a[jp]
    M = len(x)
    rng = np.random.default_rng(5)
    Ns = [100, 250, 500, 1000, 1500, 2000]
    boot = []
    for N in Ns:
        q99, q50 = [], []
        for _ in range(400):
            sub = x[rng.choice(M, N, replace=False)]
            q99.append(np.quantile(sub, CONF)); q50.append(np.quantile(sub, 0.5))
        fpc = np.sqrt(1 - N / M)  # sampling without replacement from a finite pool understates the SE
        boot.append({"N": N, "se99": np.std(q99) / fpc / np.mean(q99) * 100, "se50": np.std(q50) / fpc / np.mean(q50) * 100})
    fig, ax = plt.subplots(1, 3, figsize=(7.6, 2.7))
    ax[0].loglog(Ns, [b["se99"] for b in boot], marker="o", ms=3, color=ORANGE, label="PFE99")
    ax[0].loglog(Ns, [b["se50"] for b in boot], marker="s", ms=3, color=TEAL, label="median PFE")
    ax[0].loglog(Ns, boot[0]["se99"] * np.sqrt(Ns[0] / np.array(Ns)), ls="--", color=GREY, label="1/sqrt(N)")
    ax[0].set_title("Relative SE at the peak-PFE date", fontsize=8); ax[0].set_xlabel("scenarios N"); ax[0].set_ylabel("% relative SE"); ax[0].legend()
    n2 = [r["N"] for r in r99]
    ax[1].loglog(n2, [r["relative_se_pct"] for r in r99], marker="o", ms=3, color=ORANGE)
    ax[1].set_title("PFE99 at 1y, 30,000-path pool", fontsize=8); ax[1].set_xlabel("scenarios N")
    g = [r["marginal_se_improvement_pct"] for r in r99]
    ax[2].bar(range(1, len(n2)), g[1:], color=ORANGE)
    ax[2].set_xticks(range(1, len(n2))); ax[2].set_xticklabels([("%dk" % (v // 1000)) if v >= 1000 else str(v) for v in n2[1:]], fontsize=6.5)
    ax[2].set_title("Marginal SE gain per step", fontsize=8); ax[2].set_xlabel("N reached")
    return fig, c99, r99, boot, D["rep_dates"][jp]


'''
s = re.sub(r"def fig_conv\(\):.*?(?=def fig_profiles)", lambda m_: new_conv, s, flags=re.S)
open(p, "w", encoding="utf-8").write(s)
print("ok1")
