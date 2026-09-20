"""Builds docs/Capitolis_CCR_Executive_Deck.pdf (landscape slides) from the
same data/figures as scripts/build_report.py. ASCII text only."""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, ROOT)
import build_report as R
from report_lib import A, NAVY, plt
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (BaseDocTemplate, Frame, Image, PageBreak, PageTemplate, Paragraph,
                                Spacer, Table, TableStyle)
from PIL import Image as PILImage

PG = (11 * inch, 6.2 * inch)
TITLE = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=24, leading=28, textColor=colors.HexColor(NAVY), spaceAfter=10)
TXT = ParagraphStyle("x", fontName="Helvetica", fontSize=12.5, leading=17, spaceAfter=6)
BUL = ParagraphStyle("b", parent=TXT, leftIndent=14, bulletIndent=2)
SM = ParagraphStyle("s", parent=TXT, fontSize=9.5, leading=12, textColor=colors.HexColor("#555555"))
TILEV = ParagraphStyle("tv", fontName="Helvetica-Bold", fontSize=24, leading=27, textColor=colors.HexColor(NAVY), alignment=1)
TILEL = ParagraphStyle("tl", fontName="Helvetica", fontSize=9.5, leading=12, textColor=colors.HexColor("#444444"), alignment=1)
CELL = ParagraphStyle("c", fontName="Helvetica", fontSize=10, leading=13)
CELLH = ParagraphStyle("ch", parent=CELL, fontName="Helvetica-Bold", textColor=colors.white)


def P(t, s=TXT):
    return Paragraph(A(t), s)


def bl(items):
    return [Paragraph(A(t), BUL, bulletText="-") for t in items]


def img(fig, tmp, n, w, h):
    path = os.path.join(tmp, "d%d.png" % n)
    fig.savefig(path, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    pw, ph = PILImage.open(path).size
    s = min(w / pw, h / ph)
    return Image(path, width=pw * s, height=ph * s)


def table(rows, widths):
    d = [[Paragraph(A(c), CELLH if i == 0 else CELL) for c in r] for i, r in enumerate(rows)]
    t = Table(d, colWidths=widths)
    st = [("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#C9CED6")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(NAVY))]
    for i in range(2, len(rows), 2):
        st.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F3F5F8")))
    t.setStyle(TableStyle(st))
    return t


def tiles(vals):
    cells = [[Paragraph(A(v), TILEV) for v, _ in vals], [Paragraph(A(l), TILEL) for _, l in vals]]
    t = Table(cells, colWidths=[9.6 * inch / len(vals)] * len(vals))
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#C9CED6")),
                           ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#C9CED6")),
                           ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EAF4F2")),
                           ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    return t


def main():
    D = R.exposures(R.load_all())
    tmp = tempfile.mkdtemp(prefix="deck_")
    ids = D["meta"]["trade_ids"]
    npv0 = D["npv"][:, 0, :].mean(axis=1)
    tot = R.prof(D["expo"]["__portfolio__"])
    j = int(tot["P99"].argmax())
    per = {c: R.prof(D["expo"][c]) for c in ("CPTY_A", "CPTY_B", "CPTY_C")}
    mpe = float(tot["P99"].max())
    share_c = per["CPTY_C"]["EE"][0] / max(tot["EE"][0], 1) * 100

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

    S += [Spacer(1, 1.2 * inch), P("Monte Carlo Counterparty Credit Risk Engine", ParagraphStyle("tt", parent=TITLE, fontSize=34, leading=40)),
          P("Executive summary: what the risk is, how we measure it, what we found", ParagraphStyle("st", parent=TXT, fontSize=17, leading=22)),
          Spacer(1, 12), P("ESF derivatives book | 16 trades | 3 counterparties | PFE at the 99th percentile | full detail in Capitolis_CCR_Complete_Report.pdf", SM), PageBreak()]

    S += [P("The answer in one page", TITLE),
          tiles([("$%.0fM" % (tot["EE"][0] / 1e6), "exposure if everyone defaulted today"),
                 ("$%.0fM" % (tot["EE"].max() / 1e6), "peak expected exposure (EE)"),
                 ("$%.0fM" % (mpe / 1e6), "peak PFE99 (MPE), %s" % D["rep_dates"][j]),
                 ("%.0f%%" % share_c, "of today's exposure is CPTY_C")]), Spacer(1, 14)]
    S += bl(["Uncollateralized book: our credit risk is short-dated. Most exposure disappears by December 2026 as trades mature.",
             "Concentrated: one $500M bond forward (BF_0003) with CPTY_C is almost all of it. A limit or margin on that trade moves the answer more than any model choice.",
             "The three measures together matter: at peak, median PFE %s, EE %s, PFE99 %s." % (R.m(tot["MED"].max()), R.m(tot["EE"].max()), R.m(mpe)),
             "If any trade is actually margined, exposure falls sharply (collateral slide). Confirming CSA terms is the most valuable open question."])
    S.append(PageBreak())

    S += [P("What we measure", TITLE), fig(R.fig_measures_illustration(D), 3.3 * inch),
          P("Exposure = max(net value, 0): only gains against us are at risk. EE is the average; the median PFE is the typical case; PFE99 is the level exceeded in only 1 of 100 scenarios; MPE is the peak PFE over time.", TXT), PageBreak()]

    S += [P("The book: 16 trades, short-dated", TITLE), fig(R.fig_book_timeline(D), 3.5 * inch),
          P("8 equity total return swaps (incl. JPY compo), 4 bond forwards, 4 bond TRS across three counterparties. All priced with the supplied, independently reviewed pricer library.", TXT), PageBreak()]

    rows = [["Step", "What we do", "Choice"],
            ["1 Calibrate", "SOFR curve from CME futures; realised vols; 39x39 correlation; mean reversion from swaptions", "Real market data throughout"],
            ["2 Simulate", "USD rate: Hull-White one-factor. Equities and USDJPY: correlated GBM driven by the rate", "Exact fit to today's curve; negative-rate capable"],
            ["3 Sample", "Latin-Hypercube scenarios (5,000 recommended for reporting; 3,000 used here); Cholesky for correlation (PCA factor model optional)", "Lowest measured error of 5 methods"],
            ["4 Dates", "Market pillar dates (O/N..10Y) plus every trade's own reset and maturity date", "Industry convention, exact cash-flow dates"],
            ["5 Reprice", "Every trade re-priced in every scenario and date with the standard pricers", "No new pricing logic"],
            ["6 Aggregate", "Net by counterparty, max(.,0), then EE, median PFE, PFE99, MPE", "Uncollateralized by default"]]
    S += [P("How the engine works", TITLE), table(rows, [1.2 * inch, 5.6 * inch, 3.0 * inch]), PageBreak()]

    S += [P("Exposure through time", TITLE), fig(R.fig_profiles(D), 3.9 * inch),
          P("Exposure peaks within about 2 months and collapses as trades mature; a small tail runs to January 2028.", TXT), PageBreak()]

    S += [P("Where the risk sits", TITLE), fig(R.fig_t0_npv(D, npv0), 3.4 * inch),
          P("CPTY_C's value is one trade (BF_0003, +$101M). CPTY_B nets negative so has zero exposure today. This is concentration risk, not diversified counterparty risk.", TXT), PageBreak()]

    fg, cmp_, cp, u, mp = R.fig_mpor(D)
    S += [P("What if margin were posted? (hypothetical)", TITLE), fig(fg, 3.0 * inch),
          P("Full variation margin with a 10-day margin period of risk: peak PFE99 falls " + ", ".join("%s %.0f%%" % (c, (1 - b / a) * 100) for c, a, b in zip(cp, u, mp)) + ". No CSA data exists for the real book, so this illustrates a built capability.", TXT), PageBreak()]

    import json
    vr = json.load(open(os.path.join(R.PROC, "variance_reduction_benchmark.json")))
    fg, c99, r99, boot, jdate = R.fig_conv(D, D["meta"])
    c_se = float(__import__("numpy").mean([b["se99"] * b["N"] ** 0.5 for b in boot[2:]]))
    S += [P("How precise, and how do we know it is right", TITLE), fig(fg, 2.4 * inch)]
    S += bl(["Decision: Latin Hypercube sampling (best of 5 methods tested: %.1fx lower PFE99 estimator noise than pseudo-random on the real engine, %.0fx lower error on the controlled test)." % (vr["real_engine_check"]["pseudo_random"]["std"] / vr["real_engine_check"]["latin_hypercube"]["std"], vr["option_study"]["results"]["pseudo_random"]["rmse"] / vr["option_study"]["results"]["latin_hypercube"]["rmse"]),
             "Decision: 5,000 paths for standard PFE99 reporting (error %.1f%% at the worst-case date, 0.29%% at 1 year); 1,000 for iteration; 10,000 for limit sign-off. This deck uses 3,000." % (c_se / 5000 ** 0.5),
             "Checks passed: t=0 self-consistency 0.0000%, martingale test (max 0.73 bp), parametric VaR ratio 1.08, stress-test directions, 58 automated tests.",
             "Model risk (mean reversion, volatility proxy) outweighs sampling noise beyond about 10,000 paths."])
    S.append(PageBreak())

    S += [P("Assumptions, limits, next steps", TITLE)]
    S += bl(["Volatility is a 3-year realised proxy (no single-name options data); one static correlation matrix; GBM understates fat tails.",
             "JPY: a real negative-rate-capable Hull-White factor is built (sigma from real Bank of Japan TONA; USD-JPY rate correlation calibrated near zero) but does not yet drive JPY equity drift; its mean reversion falls back to USD's because real JPY vol rises with tenor.",
             "No counterparty default probability or wrong-way risk: this is exposure, not expected loss.",
             "Ask: are any trades margined, and under what CSA terms?",
             "Next: wire JPY factor into the drift, PFE Greeks, two-factor rate model, model-risk study on mean reversion, vols and correlation."])
    doc.build(S)
    print("wrote", out)


if __name__ == "__main__":
    main()
