"""Build the final Capitolis CCR presentation as a native .pptx using python-pptx
(no Node/pptxgenjs available on this machine). Navy/teal theme matching the
project's existing report/deck styling.

Regenerates the PNG figures it needs (rasterized from the report's own PDF
figure library, docs/latex/figures/) into data/processed/deck_pngs/ on every
run, so the script is self-contained and reproducible from a clean checkout.
"""
import os
import fitz
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.oxml.ns import qn

NAVY = RGBColor(0x1F, 0x3A, 0x5F)
TEAL = RGBColor(0x2A, 0x9D, 0x8F)
ORANGE = RGBColor(0xE7, 0x6F, 0x51)
GOLD = RGBColor(0xE9, 0xC4, 0x6A)
GREY = RGBColor(0x8D, 0x99, 0xAE)
DARKGREY = RGBColor(0x44, 0x44, 0x44)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LIGHTBG = RGBColor(0xF5, 0xF7, 0xFA)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PNG = os.path.join(ROOT, "data", "processed", "deck_pngs")
OUT = os.path.join(ROOT, "docs", "Capitolis_CCR_Final_Presentation.pptx")

os.makedirs(PNG, exist_ok=True)
_FIGS = ["fig04", "fig11", "fig12", "fig13", "fig14", "fig16", "fig19", "fig25", "fig26", "fig28", "fig30",
         "fig31", "fig33", "fig34", "fig36", "fig37", "fig_dv01_compare", "fig_sampling_greeks",
         "fig_greeks_cost", "fig_hist_scenarios", "fig_kva_compare"]
for _f in _FIGS:
    _src = os.path.join(ROOT, "docs", "latex", "figures", _f + ".pdf")
    _dst = os.path.join(PNG, _f + ".png")
    if os.path.exists(_src) and not os.path.exists(_dst):
        _doc = fitz.open(_src)
        _doc[0].get_pixmap(matrix=fitz.Matrix(3, 3)).save(_dst)
        _doc.close()

SW, SH = Inches(13.333), Inches(7.5)

prs = Presentation()
prs.slide_width = SW
prs.slide_height = SH
BLANK = prs.slide_layouts[6]


def add_slide():
    return prs.slides.add_slide(BLANK)


def set_bg(slide, color=WHITE):
    bg = slide.background
    bg.fill.solid()
    bg.fill.fore_color.rgb = color


def add_rect(slide, x, y, w, h, color, line=False):
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    shp.fill.solid()
    shp.fill.fore_color.rgb = color
    if line:
        shp.line.color.rgb = color
        shp.line.width = Pt(0.25)
    else:
        shp.line.fill.background()
    shp.shadow.inherit = False
    return shp


def add_text(slide, x, y, w, h, text, size=14, bold=False, color=DARKGREY, align=PP_ALIGN.LEFT,
             font="Calibri", italic=False, anchor=MSO_ANCHOR.TOP, line_spacing=1.1, wrap=True):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = wrap
    tf.vertical_anchor = anchor
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = line_spacing
        r = p.add_run()
        r.text = ln
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.italic = italic
        r.font.color.rgb = color
        r.font.name = font
    return tb


def add_bullets(slide, x, y, w, h, items, size=13, color=DARKGREY, font="Calibri",
                 space_after=6, bullet_color=TEAL, line_spacing=1.08):
    """items: list of (text, bold_lead_or_None, level)"""
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    for i, item in enumerate(items):
        if isinstance(item, tuple):
            txt, lead, level = item
        else:
            txt, lead, level = item, None, 0
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.level = level
        p.space_after = Pt(space_after)
        p.line_spacing = line_spacing
        # bullet char via XML
        pPr = p._pPr
        if pPr is None:
            pPr = p._p.get_or_add_pPr()
        buChar = pPr.makeelement(qn('a:buChar'), {'char': '\u2022' if level == 0 else '\u2013'})
        buFont = pPr.makeelement(qn('a:buFont'), {'typeface': 'Arial'})
        buClr = pPr.makeelement(qn('a:buClr'), {})
        srgb = pPr.makeelement(qn('a:srgbClr'), {'val': '%02X%02X%02X' % (bullet_color[0], bullet_color[1], bullet_color[2])})
        buClr.append(srgb)
        pPr.append(buClr)
        pPr.append(buFont)
        pPr.append(buChar)
        pPr.set('marL', str(Inches(0.22 + 0.22 * level)))
        pPr.set('indent', str(-Inches(0.22)))
        if lead:
            r1 = p.add_run()
            r1.text = lead + " "
            r1.font.bold = True
            r1.font.size = Pt(size)
            r1.font.color.rgb = NAVY
            r2 = p.add_run()
            r2.text = txt
            r2.font.size = Pt(size)
            r2.font.color.rgb = color
            r2.font.name = font
            r1.font.name = font
        else:
            r = p.add_run()
            r.text = txt
            r.font.size = Pt(size)
            r.font.color.rgb = color
            r.font.name = font
    return tb


def header(slide, title, subtitle=None):
    add_rect(slide, 0, 0, SW, Inches(1.0), NAVY)
    add_text(slide, Inches(0.5), Inches(0.14), Inches(12.3), Inches(0.6), title,
              size=24, bold=True, color=WHITE, anchor=MSO_ANCHOR.MIDDLE)
    if subtitle:
        add_text(slide, Inches(0.5), Inches(0.62), Inches(12.3), Inches(0.3), subtitle,
                  size=11, bold=False, color=RGBColor(0xC9, 0xD6, 0xE6), anchor=MSO_ANCHOR.MIDDLE)
    pg = slide.shapes.add_textbox(Inches(12.6), Inches(7.12), Inches(0.6), Inches(0.3))
    return slide


def footer_page(slide, n):
    add_text(slide, Inches(12.5), Inches(7.1), Inches(0.7), Inches(0.3), str(n),
              size=9, color=GREY, align=PP_ALIGN.RIGHT)


def content_slide(title, subtitle=None):
    s = add_slide()
    set_bg(s)
    header(s, title, subtitle)
    return s


def part_divider(part_no, title):
    s = add_slide()
    set_bg(s, NAVY)
    add_text(s, Inches(1.0), Inches(2.9), Inches(6), Inches(0.5), f"PART {part_no}",
              size=18, bold=True, color=GOLD, font="Calibri")
    add_text(s, Inches(1.0), Inches(3.35), Inches(10.5), Inches(1.2), title,
              size=34, bold=True, color=WHITE, font="Calibri")
    add_rect(s, Inches(1.0), Inches(3.25), Inches(0.9), Pt(3), GOLD)
    return s


def img_slide(title, img, caption=None, subtitle=None, img_w=10.5):
    s = content_slide(title, subtitle)
    path = f"{PNG}/{img}.png"
    pic = s.shapes.add_picture(path, Inches(0), Inches(0), height=Inches(5.3))
    # center horizontally
    pic_w = pic.width
    max_w = Inches(img_w)
    if pic_w > max_w:
        ratio = max_w / pic_w
        pic.width = max_w
        pic.height = int(pic.height * ratio)
    pic.left = int((SW - pic.width) / 2)
    pic.top = Inches(1.25)
    if caption:
        add_text(s, Inches(0.6), Inches(6.75), Inches(12.1), Inches(0.5), caption,
                  size=12, italic=True, color=DARKGREY, align=PP_ALIGN.CENTER)
    return s


def simple_table(slide, x, y, w, h, rows, col_widths=None, header_row=True, font_size=11,
                  header_size=11.5, align_cols=None):
    nrows, ncols = len(rows), len(rows[0])
    tbl_shape = slide.shapes.add_table(nrows, ncols, x, y, w, h)
    tbl = tbl_shape.table
    if col_widths:
        total = sum(col_widths)
        for i, cw in enumerate(col_widths):
            tbl.columns[i].width = int(w * cw / total)
    for r in range(nrows):
        for c in range(ncols):
            cell = tbl.cell(r, c)
            cell.margin_left = Pt(4)
            cell.margin_right = Pt(4)
            cell.margin_top = Pt(2)
            cell.margin_bottom = Pt(2)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.alignment = (align_cols[c] if align_cols else PP_ALIGN.LEFT)
            run = p.add_run()
            run.text = str(rows[r][c])
            run.font.size = Pt(header_size if (r == 0 and header_row) else font_size)
            run.font.name = "Calibri"
            run.font.bold = (r == 0 and header_row)
            run.font.color.rgb = WHITE if (r == 0 and header_row) else DARKGREY
            cell.fill.solid()
            if r == 0 and header_row:
                cell.fill.fore_color.rgb = NAVY
            else:
                cell.fill.fore_color.rgb = LIGHTBG if r % 2 == 0 else WHITE
    return tbl_shape


def stat_card(slide, x, y, w, h, value, label, color=TEAL):
    add_rect(slide, x, y, w, h, LIGHTBG)
    add_text(slide, x + Inches(0.1), y + Inches(0.12), w - Inches(0.2), Inches(0.65), value,
              size=30, bold=True, color=color, align=PP_ALIGN.CENTER)
    add_text(slide, x + Inches(0.1), y + h - Inches(0.55), w - Inches(0.2), Inches(0.5), label,
              size=10.5, color=DARKGREY, align=PP_ALIGN.CENTER)


print("helpers ready")

# ============================================================ TITLE
s = add_slide(); set_bg(s, NAVY)
add_rect(s, 0, Inches(4.55), SW, Pt(2.5), GOLD)
add_text(s, Inches(1.0), Inches(2.5), Inches(11.3), Inches(1.3),
         "Counterparty Credit Risk Engine for the Capitolis Book",
         size=36, bold=True, color=WHITE)
add_text(s, Inches(1.0), Inches(3.75), Inches(11.3), Inches(0.6),
         "Data, Models, Trade-offs, and Results", size=18, color=GOLD)
add_text(s, Inches(1.0), Inches(4.75), Inches(11.3), Inches(0.4),
         "Berkeley MFE Industry Project  |  Valuation date 2026-08-28", size=13, color=RGBColor(0xC9,0xD6,0xE6))

# ============================================================ AGENDA
s = content_slide("Agenda")
agenda = ["Part I -- What Capitolis Gave Us", "Part II -- Risks, Variables, and Data",
          "Part III -- Models Considered, and Why the Final Model", "Part IV -- Efficient Simulation",
          "Part V -- What the Engine Does, and What It Finds", "Part VI -- Sensitivities, Stress, and Validation",
          "Part VII -- Credit and Capital", "Part VIII -- Decisions, Limitations, and Conclusions"]
add_bullets(s, Inches(0.8), Inches(1.4), Inches(11), Inches(5.5),
            [(a, None, 0) for a in agenda], size=18, space_after=16)

print("title+agenda done")

# ============================================================ PART I
part_divider("I", "What Capitolis Gave Us")

s = content_slide("The book: 16 trades, three netting sets")
rows = [["Trade", "Type", "Cpty", "Underlying", "Ends", "Notional", "NPV t=0"],
        ["EQTRS_0001-3", "Eq. TRS", "A", "3 USD names each", "Oct'26", "50-99M", "-5.55 / -1.08 / +9.92M"],
        ["EQTRS_0004", "Eq. TRS", "B", "16 USD names", "Nov'26", "49.2M", "-0.87M"],
        ["EQTRS_0005/6", "Eq. TRS", "B", "3 JPY names each", "Oct'26", "12-31M", "+0.15 / +1.63M"],
        ["EQTRS_0007/8", "Eq. TRS", "C", "7 / 3 USD names", "Oct'26/Jul'27", "95M / 30M", "-0.37 / +2.22M"],
        ["BF_0001/2", "Bond fwd", "A", "UST 3.88%'28 / 4.63%'35", "Oct/Nov'26", "100M / 20M", "+0.51 / -0.36M"],
        ["BF_0003", "Bond fwd", "C", "UST 2.88% 5/15/2049", "Dec'26", "500M", "+121.26M"],
        ["BF_0004", "Bond fwd", "C", "UST 1.13%'28", "Oct'26", "50M", "+1.97M"],
        ["BTRS_0001-4", "Bond TRS", "A/B/B/C", "UST 4.12/2.88/4.63/4.12%", "'27-'28", "5-40M", "+0.12/+0.21/+0.03/+0.04M"]]
simple_table(s, Inches(0.5), Inches(1.25), Inches(12.3), Inches(4.3), rows,
             col_widths=[1.3, 0.8, 0.5, 1.9, 1.0, 0.9, 1.9], font_size=10.5, header_size=11)
add_text(s, Inches(0.5), Inches(5.75), Inches(12.3), Inches(0.5),
         "Net MtM by netting set:  CPTY_A +$3.57M    CPTY_B +$1.15M    CPTY_C +$125.12M    Book +$129.84M",
         size=13, bold=True, color=NAVY)

s = content_slide("The exposure we must measure (Capitolis kickoff definition)")
add_text(s, Inches(0.6), Inches(1.3), Inches(11), Inches(0.6),
         "Exposure = max( V(t+10bd) - V(t-1bd), 0 )", size=20, bold=True, color=NAVY)
add_bullets(s, Inches(0.8), Inches(2.2), Inches(7.6), Inches(3.5), [
    ("Variation margin: netted value one business day before t, two-way, no threshold", "", 0),
    ("Margin period of risk (MPoR): close-out 10 business days after t", "", 0),
    ("Netting: within a counterparty only -- book = sum over netting sets; never netted across counterparties", "", 0),
    ("Trades settling inside the window are excluded from both legs", "", 0),
], size=14, space_after=14)
s.shapes.add_picture(f"{PNG}/fig26.png", Inches(8.7), Inches(1.5), width=Inches(4.1))

print("Part I done")

# ============================================================ PART II
part_divider("II", "Risks, Variables, and Data")

s = content_slide("Risk factors: what can move the book")
rows = [["Risk factor", "Trades affected", "Model", "Calibrated from"],
        ["37 equity prices", "All 8 equity TRS", "Correlated geometric\nBrownian motion", "3y realised vol,\nYahoo Finance dividend"],
        ["USDJPY", "Equity TRS on JPY\nnames (2)", "GBM, quanto-adjusted\ndrift", "3y realised FX vol"],
        ["USD short rate\n(whole curve)", "Bond forwards, bond\nTRS, funding, discounting", "Hull-White one-factor\n(= 1-factor LGM)", "Real swaption cube (a)\n+ realised Treasury vol"],
        ["JPY short rate", "Drift of JPY-listed\nnames and USDJPY", "2nd, independent\nHull-White one-factor", "Real JPY OIS curve,\nJPY rate history"],
        ["Counterparty credit", "CVA/DVA/FVA/KVA\nonly", "Deterministic hazard-\nrate survival curve", "ICE BofA rating-index\nOAS proxy; no CDS"]]
simple_table(s, Inches(0.5), Inches(1.25), Inches(12.3), Inches(4.5), rows,
             col_widths=[1.6, 2.0, 2.0, 2.1], font_size=11.5, header_size=12)
add_text(s, Inches(0.5), Inches(6.1), Inches(12.3), Inches(0.8),
         "39 correlated stochastic factors, one joint simulation: 37 equities, USDJPY, USD short rate, JPY short "
         "rate -- correlated by a single Cholesky factor of the real historical matrix at every time step.",
         size=13, italic=True, color=DARKGREY)

s = content_slide("Data philosophy")
add_bullets(s, Inches(1.0), Inches(1.8), Inches(11), Inches(3), [
    ("Every number in this project traces to a disclosed, real source -- no synthetic placeholders for calibration inputs", "", 0),
    ("Benefit: results are reproducible, auditable, and defensible in front of a risk committee; every assumption is a named simplification, not a silent one", "", 0),
    ("Two tiers: public (Yahoo Finance, FRED, Databento) and licensed (Bloomberg, used and cross-checked but never redistributed as raw series)", "", 0),
], size=16, space_after=18)

def data_source_slide(title, rows):
    s = content_slide(title)
    simple_table(s, Inches(0.5), Inches(1.3), Inches(12.3), Inches(5.3), rows,
                 col_widths=[2.6, 4.8, 4.9], font_size=12, header_size=13)
    return s

data_source_slide("Data source 1: USD discount curve (Databento SOFR futures)", [
    ["Item", "Detail", "Benefit of using real data"],
    ["Source", "Real Databento CME SOFR futures (SR3) settlement prices, bootstrapped ourselves", "A genuine market-implied curve, not an assumed flat extrapolation"],
    ["Used for", "Every USD discount factor; the base for the Hull-White short-rate model", "Splicing the real Bloomberg long end moved portfolio MPE99 from $52.7M to $52.1M (-1.1%)"],
    ["Extension", "Bloomberg long-end quotes spliced in beyond futures coverage (out to 50y)", "A modest, disclosed, measured effect -- not a silent assumption"]])

data_source_slide("Data source 2: Treasury yields (FRED) and swaption vols (Bloomberg)", [
    ["Source", "Used for", "Benefit of using it"],
    ["FRED Treasury CMT yields (3mo-30y, public, since 1981)", "Realised long-end yield vol -> Hull-White sigma (0.96%); Kupiec backtest", "Directly measures the volatility of the yields this book's bonds depend on"],
    ["Bloomberg ATM normal swaption vol cube", "Mean-reversion a (0.0167, R2=0.84), via vol decay with tenor", "Textbook calibration route; genuinely implied, forward-looking"]])

data_source_slide("Data source 3 & 4: equities, FX, JPY curve, and credit spreads", [
    ["Source", "Used for", "Benefit of using it"],
    ["Yahoo Finance: 37 equities + USDJPY, 3y history", "Spots, dividends, realised vol, the 39x39 correlation matrix", "Public, free, long enough history (2007-today) for reliable statistics"],
    ["Real JPY OIS curve", "JPY Hull-White factor's base curve", "Lets JPY rates move independently and go negative, matching real BOJ history"],
    ["ICE BofA bond-index OAS by rating (FRED)", "Counterparty/issuer credit spread proxy (CVA, DVA, risky bond)", "Basel MAR50.32(3)-sanctioned fallback; real market spreads by credit quality"],
    ["Bloomberg (licensed): long-end curve, swaption cubes, FX vol surface", "Curve splice, mean-reversion fit, model-risk cross-checks", "Only source for genuine long-dated data beyond public; derived numbers only, per license"]])

print("Part II done")

# ============================================================ PART III
part_divider("III", "Models Considered, and Why the Final Model")

s = content_slide("Rate models considered")
rows = [["Model", "Advantages", "Disadvantages", "Final use"],
        ["Hull-White 1F\n(= 1-factor LGM)", "Exact step, closed-form P(t,T);\n2 parameters; stable calibration", "One factor -- curve moves close\nto parallel; can't twist", "SELECTED\nProduction"],
        ["G2++ (2-factor\nGaussian, = LGM2F)", "Level and slope move\nseparately; fits covariance", "5 parameters; b hits its bound;\n16.1% relative fit error", "Challenger,\ntested"],
        ["2-factor +\nstochastic vol", "Vol clustering, fatter tails", "Not implemented; more\nparameters, no closed form here", "Not built"]]
simple_table(s, Inches(0.5), Inches(1.25), Inches(12.3), Inches(3.3), rows,
             col_widths=[1.7, 3.2, 3.2, 1.4], font_size=12, header_size=12.5)
add_text(s, Inches(0.5), Inches(4.85), Inches(12.3), Inches(0.8),
         "The question is empirical, not a matter of preference: does the second factor materially change "
         "this book's exposure? Tested head to head on the following slides.", size=14, italic=True, color=DARKGREY)

s = content_slide("Equity, FX and credit models considered")
rows = [["Model", "Advantages", "Disadvantages", "Final use"],
        ["Equities: GBM", "Exact log-Euler step, fast", "No vol smile or clustering", "SELECTED"],
        ["Equities: stochastic vol (Heston)", "Vol clustering, skew", "Not implemented; needs option surfaces per name", "Not built"],
        ["FX: GBM, quanto/rate-diff. drift", "Consistent with both simulated curves", "No smile", "SELECTED"],
        ["Credit: deterministic hazard-rate proxy", "Transparent, Basel MAR50.32-compliant", "No wrong-way risk, no spread vol", "SELECTED"],
        ["Credit: stochastic intensity", "Spread risk, wrong-way risk", "No counterparty CDS data available", "Not available"]]
simple_table(s, Inches(0.5), Inches(1.25), Inches(12.3), Inches(4.2), rows,
             col_widths=[2.6, 3.2, 3.4, 1.4], font_size=11.5, header_size=12)
add_text(s, Inches(0.5), Inches(5.7), Inches(12.3), Inches(0.8),
         "Simple models where the book is linear and short-dated: exposure windows are 10 business days on "
         "largely linear TRS/forward payoffs; the stress-testing programme tests a volatility regime shift directly.",
         size=13, italic=True, color=DARKGREY)

s = content_slide("Correlation: full Cholesky matrix vs. PCA factor model")
pic = s.shapes.add_picture(f"{PNG}/fig14.png", Inches(0.3), Inches(1.3), width=Inches(8.3))
rows = [["", "Full", "PCA k=5", "PCA k=10"],
        ["Step time (5,000 scen.)", "1.91s", "2.08s", "2.29s"],
        ["Variance explained", "100%", "47%", "62%"],
        ["Netting-set vol vs. full (B)", "-", "+1.7%", "+1.5%"]]
simple_table(s, Inches(8.9), Inches(1.3), Inches(4.0), Inches(1.8), rows,
             col_widths=[1.5,0.9,0.9,0.9], font_size=10, header_size=10)
add_text(s, Inches(8.9), Inches(3.3), Inches(4.0), Inches(3.5),
         "SELECTED full matrix: PCA is slower, not faster, at n=39. Loss of using PCA instead: no speed gain, "
         "and up to 1.7% extra sampling error. Kept only as an explainability tool: factor 1 (20%) is a broad "
         "market mode, factor 2 (8.9%) is Japan vs. US.", size=11.5, color=DARKGREY)

print("Part III (1/3) done")

s = content_slide("USD rates: calibrating mean reversion and volatility")
rows = [["Route", "Data", "a", "R2", "Verdict"],
        ["Swaption cube (preferred)", "Bloomberg ATM normal vol, 1M expiry", "0.0167", "0.845", "SELECTED"],
        ["SOFR-futures vol decay", "~2y Databento history, 8 contracts", "0.0458", "0.820", "cross-check only"]]
simple_table(s, Inches(0.5), Inches(1.25), Inches(12.3), Inches(1.5), rows,
             col_widths=[2.6,3.6,1.1,1.0,1.6], font_size=12, header_size=12.5)
add_bullets(s, Inches(0.6), Inches(3.1), Inches(12), Inches(1.3), [
    ("Original volatility source (overnight SOFR fixing, 0.63%) understates how far the long-dated yields this "
     "book depends on actually move (realised 10-day 20y-yield move ~15bp vs. ~11bp implied)", "", 0),
    ("SELECTED: realised volatility of 2y-30y Treasury yield changes directly, 0.96% -- validated by Kupiec backtest", "", 0),
], size=13, space_after=10)
rows2 = [["Tenor", "Overnight-SOFR sigma exc.", "Long-end sigma exc.", "Expected", "Both pass?"],
         ["5y", "1 / 1", "4 / 3", "1.6", "yes (p>0.05)"],
         ["10y", "1 / 0", "3 / 2", "1.6", "yes"],
         ["20y", "1 / 1", "3 / 1", "1.6", "yes"]]
simple_table(s, Inches(0.5), Inches(4.65), Inches(12.3), Inches(1.9), rows2,
             col_widths=[1.2,2.6,2.2,1.3,1.6], font_size=11.5, header_size=11.5)

s = content_slide("But this book's rate risk sits in one place: 20-30 years")
pic = s.shapes.add_picture(f"{PNG}/fig_dv01_compare.png", Inches(0.4), Inches(1.3), width=Inches(6.6))
add_bullets(s, Inches(7.4), Inches(1.5), Inches(5.4), Inches(4.5), [
    ("Par-instrument DV01 (real curve-building pillars): 82% of portfolio DV01 sits in the 30y bucket, vs. "
     "11% at 10y", "", 0),
    ("BF_0003, the $500M forward on the 2049 Treasury, dominates -- one position, one tenor region", "", 0),
    ("This is why a 2-factor model's main selling point (independent curve twist across many maturities) "
     "buys little here: there is effectively one maturity that matters", "", 0),
], size=13.5, space_after=14)

s = content_slide("HW1F vs. G2++ on the book: same data, draws, grid and trades")
pic = s.shapes.add_picture(f"{PNG}/fig19.png", Inches(0.3), Inches(1.3), width=Inches(6.6))
rows = [["", "HW1F", "G2++"],
        ["Fit to realised yield covariance", "-", "16.1% rel. error"],
        ["Mean reversion", "a=0.0167", "a=0.039, b=1.5 (at bound)"],
        ["Portfolio MPE99 (N=2,000, CRN)", "baseline $51.5M", "$50.0M (-3.0%)"],
        ["By counterparty", "-", "A -1%, B -3%, C -0%"]]
simple_table(s, Inches(7.1), Inches(1.3), Inches(5.7), Inches(2.4), rows,
             col_widths=[2.6,1.5,2.0], font_size=11, header_size=11.5)
add_text(s, Inches(7.1), Inches(4.0), Inches(5.7), Inches(3.0),
         "Benefit of 2-factor: lets the curve twist, not just shift. Cost: a parameter pinned at its bound, "
         "16% fit error, and a 3% move that doesn't justify the complexity here. Same random draws used in "
         "both runs (common random numbers), so the -3.0% gap is a real model difference, not sampling noise.",
         size=12.5, color=DARKGREY)

s = content_slide("JPY rates: a dedicated Hull-White factor vs. a constant differential")
pic = s.shapes.add_picture(f"{PNG}/fig16.png", Inches(0.3), Inches(1.3), width=Inches(5.8))
add_bullets(s, Inches(6.4), Inches(1.3), Inches(6.3), Inches(2.2), [
    ("Alternative REJECTED: JPY names/USDJPY drift off one constant USD-JPY rate differential -- cheap, but "
     "cannot represent JPY rates moving independently, or negative", "", 0),
    ("SELECTED: a second, real, simulated Hull-White one-factor model from the JPY OIS curve. TONA has been "
     "negative or near-zero for most of 25 years", "", 0),
], size=12.5, space_after=10)
rows = [["Route", "Fitted a"], ["JPY OIS history", "-0.0261"], ["Swaption cube", "-0.0374"], ["JGB yield history", "-0.0203"]]
simple_table(s, Inches(6.4), Inches(3.7), Inches(3.2), Inches(1.7), rows,
             col_widths=[2,1], font_size=11, header_size=11.5)
add_text(s, Inches(6.4), Inches(5.6), Inches(6.3), Inches(1.5),
         "All 3 real routes invalid (negative a): JPY vol genuinely rises with tenor. Used a=0.001 (Ho-Lee "
         "limit). Result: moved portfolio MPE99 attribution $52.1M -> $51.5M -- real, disclosed, not noise.",
         size=12, color=DARKGREY)

s = content_slide("Decision register: rate model")
rows = [["Decision", "Final choice", "Evidence", "Trade-off"],
        ["USD rate model", "Hull-White 1F (1-factor LGM)", "G2++ CRN gap only -3.0% at 16.1% fit error, parameter at bound; book DV01 82% at 30y", "No independent curve twist"],
        ["JPY rate model", "Hull-White 1F, dedicated factor", "All 3 real a-routes invalid; attribution $52.1M->$51.5M", "One extra simulated factor"],
        ["Rate volatility source", "Realised 2y-30y Treasury", "Matches actual 10bd long-yield move (15bp vs. 11bp implied); both pass Kupiec", "More model-risk sensitivity to window"]]
simple_table(s, Inches(0.5), Inches(1.4), Inches(12.3), Inches(4.5), rows,
             col_widths=[1.8,2.4,4.8,2.9], font_size=11.5, header_size=12)

print("Part III done")

# ============================================================ PART IV
part_divider("IV", "Efficient Simulation")

s = content_slide("Sampling scheme: five methods, exact benchmark numbers")
add_text(s, Inches(0.5), Inches(1.2), Inches(10), Inches(0.35),
         "Controlled test (European call, known Black-Scholes truth = 41.077):", size=13, bold=True, color=NAVY)
rows = [["Method", "RMSE", "vs. pseudo-random", "ms/trial"],
        ["Pseudo-random", "1.456", "1.0x (baseline)", "0.30"],
        ["Antithetic", "1.079", "1.3x better", "0.31"],
        ["Moment-matched", "0.232", "6.3x better", "0.55"],
        ["Sobol", "0.051", "28.8x better", "1.65"],
        ["Latin Hypercube", "0.029", "50.6x better", "0.98"]]
simple_table(s, Inches(0.5), Inches(1.6), Inches(7.3), Inches(2.4), rows,
             col_widths=[2.2,1.2,2.0,1.2], font_size=12, header_size=12.5)
add_text(s, Inches(8.1), Inches(1.6), Inches(4.7), Inches(3.0),
         "Real 663-dim engine check: no method wins both -- Sobol has the lowest PFE std (2.72M vs. 4.29M "
         "pseudo-random), moment-matched has the lowest median std (0.40M vs. 0.76M). Latin Hypercube is "
         "competitive on both (3.73M / 0.48M) without being worst on either.", size=12.5, color=DARKGREY)
add_text(s, Inches(0.5), Inches(4.3), Inches(12.3), Inches(0.9),
         "SELECTED Latin Hypercube: best on the controlled test, competitive (never worst) on both real-engine "
         "statistics, negligible extra cost.", size=14, bold=True, color=TEAL)

s = content_slide("Latin Hypercube: what it does and does not do")
add_bullets(s, Inches(0.8), Inches(1.5), Inches(11), Inches(3.5), [
    ("Does stratify every one-dimensional marginal: each risk factor's random draws are forced to cover "
     "equal-probability bins, so tails are always visited", "", 0),
    ("Does not stratify the joint distribution across all 39 factors and ~17 time steps (~663 effective "
     "dimensions) -- interaction noise between factors remains", "", 0),
    ("Unbiased: each draw is still marginally uniform, mapped through the inverse normal CDF", "", 0),
    ("Cost: draw generation grows with N x dimension -- negligible next to repricing here", "", 0),
], size=15, space_after=16)
add_text(s, Inches(0.8), Inches(5.6), Inches(11.5), Inches(1.2),
         "This is exactly why Latin Hypercube helps a smooth average (EE) more reliably than a 99th-percentile "
         "tail (PFE99): the tail is set by interactions between a handful of extreme scenarios.",
         size=13, italic=True, color=DARKGREY)

s = content_slide("Scenario count: exact convergence results")
add_text(s, Inches(0.5), Inches(1.15), Inches(11), Inches(0.3),
         "Close-out MPE99, relative standard error by bootstrap (peak date 2026-09-20):", size=12.5, bold=True, color=NAVY)
rows = [["Netting set", "N=250", "N=500", "N=1,000", "N=2,000", "N=3,000"],
        ["CPTY_A", "6.3%", "5.1%", "3.2%", "2.6%", "2.5%"],
        ["CPTY_B", "5.1%", "4.7%", "3.8%", "3.5%", "3.5%"],
        ["CPTY_C", "5.9%", "4.8%", "3.8%", "3.1%", "3.1%"],
        ["Portfolio", "7.1%", "4.9%", "3.3%", "2.2%", "2.2%"]]
simple_table(s, Inches(0.5), Inches(1.5), Inches(8.0), Inches(2.0), rows,
             col_widths=[1.5,1,1,1,1,1], font_size=11, header_size=11)
add_text(s, Inches(0.5), Inches(3.7), Inches(12.3), Inches(0.5),
         "Independent 30,000-scenario pool study (1y-node PFE99, level exposure):", size=12.5, bold=True, color=NAVY)
rows2 = [["N", "1,000", "5,000", "10,000", "20,000", "30,000 (pool)"],
         ["Rel. SE", "0.66%", "0.29%", "0.21%", "0.09%", "0 (reference)"],
         ["Est. time (8 cores)", "119s", "479s", "929s", "1,829s", "2,729s"]]
simple_table(s, Inches(0.5), Inches(4.2), Inches(10.5), Inches(1.5), rows2,
             col_widths=[1.6,1,1,1,1,1.6], font_size=11, header_size=11)
add_text(s, Inches(0.5), Inches(6.0), Inches(12.3), Inches(1.1),
         "SELECTED: N=5,000 for standard reporting (~8 min); N=10,000 for sign-off (~15 min); beyond ~20,000, "
         "marginal SE improvement per extra 5,000-scenario batch falls below 30% while cost scales linearly.",
         size=13.5, bold=True, color=TEAL)

s = content_slide("Decision register: sampling and path count")
rows = [["Decision", "Final choice", "Evidence", "Trade-off"],
        ["Sampling scheme", "Latin Hypercube", "50.6x lower RMSE vs. pseudo-random on controlled test; competitive on real-engine stats", "No consistent Greeks-noise edge on PFE99"],
        ["Scenario count", "N=5,000 standard / 10,000 sign-off", "Rel. SE 2.2% at N=2,000, extrapolates to ~1.4% at 5,000", "~1.4% residual sampling noise remains"]]
simple_table(s, Inches(0.5), Inches(1.6), Inches(12.3), Inches(2.6), rows,
             col_widths=[1.8,2.6,5.0,2.9], font_size=12.5, header_size=13)

print("Part IV done")

# ============================================================ PART V
part_divider("V", "What the Engine Does, and What It Finds")

s = content_slide("The simulation pipeline")
steps = [("1. Calibrate", "Pull real data -> fit every model parameter (Part II)"),
         ("2. Draw", "Latin Hypercube random numbers -> correlated shocks (Cholesky of the real 39x39 matrix)"),
         ("3. Simulate", "Step every risk factor jointly across the full time grid"),
         ("4. Reprice", "Feed simulated market states into the provided pricers -- every trade, date, scenario"),
         ("5. Aggregate", "Net by counterparty -> EE / median PFE / PFE99 / MPE, both exposure conventions"),
         ("6. Downstream", "Greeks, stress, CVA/DVA/FVA/KVA, SA-CVA, SA-CCR -- all reusing the same paths")]
add_bullets(s, Inches(0.8), Inches(1.4), Inches(11.5), Inches(5.3),
            [(d, t, 0) for t, d in steps], size=16, space_after=18)

s = content_slide("Key equations, exactly as implemented")
eqs = [
    ("Rates (models/rates.py) -- Hull-White one-factor, shifted Ornstein-Uhlenbeck:",
     "dr(t) = [theta(t) - a r(t)] dt + sigma dW(t),     r(t) = x(t) + alpha(t)"),
    ("Equities and FX (models/equity_fx.py) -- log-Euler GBM:",
     "d ln S = (r_USD - q - 0.5 sigma^2) dt + sigma dW   (USD name)"),
    ("Correlated shocks (simulation/engine.py):",
     "Z = L * Z_indep   (Cholesky factor of the real 39x39 historical matrix)"),
    ("Exposure (exposure/spec_exposure.py):",
     "Exposure_c(t) = max( V_c(t+10bd) - V_c(t-1bd), 0 ),   book = sum_c Exposure_c"),
    ("CVA (exposure/cva.py), Basel MAR50.32 discretisation:",
     "CVA = LGD * sum_i DEE(t_i) * PD(t_i-1, t_i)"),
]
y = Inches(1.3)
for lead, eq in eqs:
    add_text(s, Inches(0.6), y, Inches(12), Inches(0.35), lead, size=13.5, bold=True, color=NAVY)
    add_text(s, Inches(0.9), y + Inches(0.38), Inches(11.5), Inches(0.4), eq, size=14, color=DARKGREY, font="Courier New")
    y += Inches(0.95)

s = content_slide("What the simulated paths actually look like")
s.shapes.add_picture(f"{PNG}/fig11.png", Inches(0.3), Inches(1.3), width=Inches(6.1))
s.shapes.add_picture(f"{PNG}/fig12.png", Inches(6.6), Inches(1.3), width=Inches(6.4))
add_text(s, Inches(0.5), Inches(6.7), Inches(12.3), Inches(0.6),
         "Left: simulated USD short rate (median tracks today's forward curve). Right: simulated USDJPY and "
         "two equities with 1-99% and 25-75% percentile bands.", size=12, italic=True, color=DARKGREY, align=PP_ALIGN.CENTER)

s = content_slide("Headline results (5,000 scenarios, close-out exposure)")
rows = [["", "MPE99", "Peak EE"], ["CPTY_A", "$25.9M", "$4.7M"], ["CPTY_B", "$9.6M", "$1.8M"],
        ["CPTY_C", "$29.6M", "$5.2M"], ["Portfolio", "$51.0M", "$11.6M"]]
simple_table(s, Inches(0.5), Inches(1.3), Inches(3.6), Inches(2.3), rows,
             col_widths=[1.3,1.1,1.1], font_size=13, header_size=13.5)
add_bullets(s, Inches(0.5), Inches(3.9), Inches(3.6), Inches(2.5), [
    ("CVA $11.7k close-out / $247k level", "", 0),
    ("SA-CVA capital $0.10M / $2.23M", "", 0),
    ("SA-CCR EAD $260M", "", 0),
    ("KVA (10% CoC) $22.4k / $470k", "", 0),
    ("Level exposure MPE99: $201.9M", "", 0),
], size=13, space_after=10)
s.shapes.add_picture(f"{PNG}/fig25.png", Inches(4.4), Inches(1.3), width=Inches(8.4))

print("Part V (1/2) done")

s = content_slide("What drives each counterparty, and book-level Greeks")
rows = [["", "Equity delta/+1%", "FX delta/+1%", "DV01/+1bp"],
        ["CPTY_A", "-$2.25M", "$0", "$31k"],
        ["CPTY_B", "-$0.96M", "+$0.42M", "-$4k"],
        ["CPTY_C", "-$1.24M", "$0", "$594k"],
        ["Book", "-$4.46M", "+$0.42M", "$622k"]]
simple_table(s, Inches(0.5), Inches(1.3), Inches(7.0), Inches(2.3), rows,
             col_widths=[1.3,1.9,1.9,1.9], font_size=12.5, header_size=13)
add_text(s, Inches(0.5), Inches(3.8), Inches(7.0), Inches(0.5),
         "Rank correlation of exposures: A-B 0.34, A-C 0.33, B-C 0.12", size=12.5, italic=True, color=DARKGREY)
add_bullets(s, Inches(7.9), Inches(1.3), Inches(4.9), Inches(4.5), [
    ("A is most equity-driven; C is the rate netting set (one $500M short forward on a 2049 Treasury)", "", 0),
    ("B is the only netting set with material FX delta (holds the 2 JPY-compo swaps)", "", 0),
    ("Yield-equity correlation is approx. 0.00 in our data -- no reliable offset", "", 0),
], size=13, space_after=14)

s = content_slide("Why the portfolio is close to additive across counterparties")
s.shapes.add_picture(f"{PNG}/fig28.png", Inches(0.3), Inches(1.3), width=Inches(6.2))
add_bullets(s, Inches(6.9), Inches(1.4), Inches(6.0), Inches(4.5), [
    ("Nothing nets across counterparties by construction -- portfolio MPE99 is a sum of three separate netting sets", "", 0),
    ("All three counterparties reach their own peak exposure in the same few weeks -- no timing diversification", "", 0),
    ("Positive rank correlation (0.12-0.34), since every book holds pay-equity swaps", "", 0),
    ("Result: Portfolio MPE99 ($51.0M) is approx. A+C ($54.4M), 78% of the sum of all three ($65.1M)", "", 0),
], size=13, space_after=14)

s = content_slide("Additional exposure diagnostics")
s.shapes.add_picture(f"{PNG}/fig30.png", Inches(0.3), Inches(1.3), width=Inches(6.2))
s.shapes.add_picture(f"{PNG}/fig31.png", Inches(6.7), Inches(1.3), width=Inches(6.2))
add_text(s, Inches(0.5), Inches(6.7), Inches(12.3), Inches(0.6),
         "Left: expected NPV by trade -- BF_0003 dominates, disappears at its Dec 2026 settlement. Right: "
         "peak PFE99 under a hypothetical full-VM CSA, for comparison against the brief's own definition.",
         size=12, italic=True, color=DARKGREY, align=PP_ALIGN.CENTER)

print("Part V done")

# ============================================================ PART VI
part_divider("VI", "Sensitivities, Stress, and Validation")

s = content_slide("Method: common random numbers, and what they buy")
add_bullets(s, Inches(0.6), Inches(1.3), Inches(12), Inches(2.0), [
    ("Bumping a risk factor and repricing with independent random draws: estimator std. dev. $245k -- too noisy to use", "", 0),
    ("Reusing the identical draws in the base and bumped run (common random numbers, CRN): std. dev. $1k", "", 0),
    ("282x noise reduction -- this, not the sampling scheme, is what actually controls Greeks precision", "", 0),
], size=14.5, space_after=10)
s.shapes.add_picture(f"{PNG}/fig_greeks_cost.png", Inches(2.5), Inches(3.3), width=Inches(5.0))
add_text(s, Inches(0.6), Inches(6.7), Inches(12), Inches(0.5),
         "Equity/FX spot bumps rescale simulated GBM paths exactly (no resimulation): 78 bumps at N=300 cost "
         "88s actual vs. ~8,166s naive -- 93x cheaper.", size=12.5, italic=True, color=DARKGREY, align=PP_ALIGN.CENTER)

s = content_slide("Method comparison: bump-and-reprice vs. pathwise vs. adjoint")
rows = [["Method", "Cost", "Verdict"],
        ["Bump, independent draws", "baseline, $245k noise", "REJECTED: noise swamps the signal"],
        ["Bump, CRN (used for all reported Greeks)", "~260s (equity EE, N=300)", "SELECTED: works on black-box pricers, works for quantiles"],
        ["Pathwise (closed form, equity/FX only)", "0.2-0.4s", "SELECTED as fast cross-check: ~1000x faster, agrees to 0.02-0.4%"],
        ["Adjoint differentiation", "would price all Greeks for ~3-5 valuations", "REJECTED: needs pricers rewritten -- future work"]]
simple_table(s, Inches(0.5), Inches(1.3), Inches(12.3), Inches(3.4), rows,
             col_widths=[3.0,2.6,4.8], font_size=12, header_size=12.5)
add_text(s, Inches(0.5), Inches(5.0), Inches(12.3), Inches(0.9),
         "Rate/vol Greeks (13 needed: parallel up/down, 8 buckets, 3 vega) still require a genuine "
         "resimulation at ~109s each (N=300) -- unless the exact analytic method below applies.",
         size=13, italic=True, color=DARKGREY)

s = content_slide("Rate DV01: zero-grid bump vs. par-instrument Jacobian -- full breakdown")
rows = [["Tenor bucket", "Old (zero-grid), USD", "New (par-instrument), USD"],
        ["0.25y", "-2,182", "-2,892"], ["0.5y", "-46", "-1"], ["1y", "-44", "-14"], ["2y", "-131", "-205"],
        ["3y", "-96", "-105"], ["5y", "-770", "-713"], ["10y", "-18,324 (39%)", "-6,592 (11%)"],
        ["30y", "-24,988 (54%)", "-47,191 (82%)"], ["Sum of buckets", "-46,580", "-57,713"],
        ["Independent parallel bump", "-46,605", "-57,705"]]
simple_table(s, Inches(2.0), Inches(1.25), Inches(9.3), Inches(5.2), rows,
             col_widths=[3,3,3], font_size=12.5, header_size=13)

s = content_slide("Rate DV01: why the new method, and what changed")
s.shapes.add_picture(f"{PNG}/fig_dv01_compare.png", Inches(0.4), Inches(1.3), width=Inches(6.2))
add_bullets(s, Inches(6.9), Inches(1.4), Inches(6.0), Inches(5.0), [
    ("Old: bump the fitted zero curve at 8 hand-picked tenors, triangular interpolation -- disconnected from "
     "how the curve was actually built", "", 0),
    ("SELECTED New: bump the curve's own ~45 native construction pillars (real SOFR-futures + Bloomberg "
     "long-end points), grouped into the same 8 buckets -- the genuine par-instrument (Jacobian) sensitivity", "", 0),
    ("Result: 82% of portfolio DV01 correctly in the 30y bucket, not 54%. Both methods sum to the same total "
     "(within 0.05%) -- total risk was always right, attribution across tenor was wrong", "", 0),
], size=13, space_after=14)

print("Part VI (1/2) done")

s = content_slide("An exact rate Greek, reusing the same simulated draws")
add_text(s, Inches(0.6), Inches(1.25), Inches(12), Inches(0.9),
         "In Hull-White 1F, r(t) = x(t) + alpha(t): x(t) is the simulated random factor (depends only on random "
         "draws, a, sigma); alpha(t) is deterministic (depends only on the curve). A curve bump that leaves "
         "a, sigma fixed -- every DV01 bump here -- leaves x(t) IDENTICAL to the base run.", size=14, color=DARKGREY)
add_bullets(s, Inches(0.8), Inches(2.3), Inches(11.5), Inches(1.8), [
    ("The whole bump effect is one closed-form number per date, added to the base run's own paths", "", 0),
    ("No resimulation. No new random draws.", "", 0),
    ("Validated against a true independent resimulation: agreement to 1e-15 relative precision -- not an "
     "approximation, the same calculation", "", 0),
], size=14, space_after=10)
add_text(s, Inches(0.8), Inches(4.3), Inches(11.5), Inches(0.4),
         "Separately: does Latin Hypercube itself reduce Greeks noise? Tested directly -- mixed result:",
         size=13.5, bold=True, color=NAVY)
s.shapes.add_picture(f"{PNG}/fig_sampling_greeks.png", Inches(3.2), Inches(4.75), width=Inches(6.9))

s = content_slide("Stress design: 13 fixed scenarios, same random draws as base")
rows = [["Family", "Scenarios", "Shock"],
        ["Hypothetical (8)", "EQ_DOWN/UP_30, JPY_STRONG/WEAK_15,\nRATES_UP/DOWN_200, FLIGHT_TO_QUALITY, STAGFLATION", "Round-number shocks to\nequities, USDJPY, USD curve"],
        ["Historical (5)", "HIST_EQUITY_CRASH, HIST_RATES_SPIKE, HIST_YEN_SURGE,\nHIST_GFC_2008, HIST_CHINA_DEVAL_2015", "Actual moves over a real 10-day\nwindow, worst-window rule"]]
simple_table(s, Inches(0.5), Inches(1.3), Inches(12.3), Inches(2.0), rows,
             col_widths=[1.5,6.3,4.5], font_size=11.5, header_size=12)
s.shapes.add_picture(f"{PNG}/fig33.png", Inches(2.8), Inches(3.5), width=Inches(7.7))

s = content_slide("Stress results: how far each scenario moves the headline number")
rows = [["Scenario", "Close-out MPE99", "Level MPE99"],
        ["EQ_DOWN_30", "-15.3%", "+62.3%"], ["RATES_DOWN_200", "+22.0%", "-69.0%"],
        ["STAGFLATION", "-24.1%", "+89.1% (largest)"], ["FLIGHT_TO_QUALITY", "-2.0%", "+19.6%"],
        ["HIST_EQUITY_CRASH (2020)", "-15.4%", "+54.8%"], ["HIST_GFC_2008", "-12.7%", "+55.6%"],
        ["HIST_CHINA_DEVAL_2015", "-4.9%", "+15.6%"]]
simple_table(s, Inches(2.2), Inches(1.3), Inches(8.9), Inches(3.6), rows,
             col_widths=[3,2,2], font_size=13, header_size=13.5)
add_text(s, Inches(0.5), Inches(5.3), Inches(12.3), Inches(1.0),
         "Close-out exposure is far less sensitive to instantaneous level shocks than level exposure (margin "
         "is why). Equity-driven trades react only to equity/FX shocks; bond trades react only to rate shocks.",
         size=13, italic=True, color=DARKGREY, align=PP_ALIGN.CENTER)

s = content_slide("Extending the history: 2008 and 2015, and why it matters")
s.shapes.add_picture(f"{PNG}/fig_hist_scenarios.png", Inches(0.3), Inches(1.3), width=Inches(6.4))
add_bullets(s, Inches(7.0), Inches(1.4), Inches(5.8), Inches(4.0), [
    ("Extended public price history back to 2007 (28 of 37 names covered)", "", 0),
    ("2008 GFC: Sep 29 - Oct 10, 2008; -23% median / -44% worst single-name return", "", 0),
    ("2015 China deval.: Aug 2015, -6.8% median", "", 0),
    ("Result: both land inside the range the existing scenarios already covered -- a validation finding, not "
     "just more coverage", "", 0),
], size=13.5, space_after=14)

print("Part VI (2/2) done")

s = content_slide("Per-trade sensitivity: does every product react as expected")
s.shapes.add_picture(f"{PNG}/fig34.png", Inches(1.5), Inches(1.2), width=Inches(10.3))

s = content_slide("Validation summary: every check has a pass rule")
rows = [["Check", "Method / metric", "Result"],
        ["Martingale test", "Discounted paths average to today's price", "Pass"],
        ["Parametric VaR benchmark", "Delta-normal vs. full MC P&L, 99%", "$11.4M vs. $11.7M -- ratio 0.98"],
        ["Kupiec backtest, equity", "99%, 242 ten-day windows, 5,000-scen. prediction", "A:4/2.4 B:6/2.4 C:2/2.4 -- all pass"],
        ["Kupiec backtest, rates", "99%, 161 windows, 3 tenors, both vol sources", "0-4 exc. vs. 1.6 expected -- all pass"],
        ["Excel parametric checks", "Independent spreadsheet formulas, public data", "0.1-7% agreement across 4 checks"],
        ["DV01 additivity (old / new)", "Bucket sum / independent parallel bump", "0.9995 / 1.0001 -- pass"],
        ["Exact rate-shift Greek", "Analytic shift vs. true resimulation", "1e-15 relative precision -- pass"],
        ["No cross-cpty netting", "Enforced by construction", "168 automated regression tests"]]
simple_table(s, Inches(0.5), Inches(1.25), Inches(12.3), Inches(5.3), rows,
             col_widths=[2.6,4.8,4.9], font_size=11.5, header_size=12)

s = content_slide("Model risk: every input perturbed, one at a time")
rows = [["Perturbation (base portfolio MPE99 = $51.5M, N=2,000)", "Change"],
        ["Equity/FX vol x2", "+71.3%"], ["Equity correlations, 30% toward 1", "+21.8%"],
        ["Equity/FX vol x1.25", "+19.3%"], ["Rate-equity dependence, both fall together", "+18.2%"],
        ["Rate volatility x1.25", "+9.4%"], ["Rate-equity dependence, offsetting", "-15.3%"],
        ["Mean reversion a x3", "-4.8%"], ["Two-factor rate model (G2++) instead of one-factor", "-3.0%"]]
simple_table(s, Inches(1.6), Inches(1.25), Inches(10.1), Inches(4.0), rows,
             col_widths=[7,1.5], font_size=13, header_size=13)
add_text(s, Inches(0.5), Inches(5.6), Inches(12.3), Inches(1.2),
         "Conclusion: equity volatility, correlation, and the data-unresolvable rate-equity dependence "
         "dominate model risk. The rate-model choice explored at length is one of the smallest levers here.",
         size=13.5, bold=True, color=TEAL, align=PP_ALIGN.CENTER)

s = content_slide("Attribution: every correction, one at a time")
rows = [["Step", "Portfolio MPE99"],
        ["Earlier version (flat curve beyond 6.5y, SOFR-overnight sigma, no JPY factor, USDJPY sign error)", "$45.7M"],
        ["+ Corrected USDJPY drift sign", "$47.8M"],
        ["+ Long-end volatility fit and 10y-yield correlations", "$52.7M"],
        ["+ Bloomberg long end spliced onto the USD curve", "$52.1M"],
        ["+ JPY Hull-White factor (final model)", "$51.5M"]]
simple_table(s, Inches(0.8), Inches(1.4), Inches(11.7), Inches(3.0), rows,
             col_widths=[9,2], font_size=13, header_size=13.5)
add_text(s, Inches(0.8), Inches(4.7), Inches(11.7), Inches(0.9),
         "No single correction dominates; each is individually disclosed and traceable -- the model-risk "
         "study, not any one fix, is the right lens for how much the headline number could still move.",
         size=13, italic=True, color=DARKGREY)

print("Part VI done")

# ============================================================ PART VII
part_divider("VII", "Credit and Capital")

s = content_slide("CVA: methodology and results")
s.shapes.add_picture(f"{PNG}/fig36.png", Inches(0.3), Inches(1.3), width=Inches(6.4))
add_bullets(s, Inches(7.0), Inches(1.4), Inches(5.8), Inches(3.5), [
    ("No CDS available -> ICE BofA bond-index OAS proxy by rating (Basel MAR50.32(3)-compliant); all 3 "
     "counterparties proxied at BBB", "", 0),
    ("Credit-triangle hazard-rate survival model: hazard ~ spread / (1 - recovery), LGD 60%", "", 0),
    ("CPTY_C close-out CVA $7.9k; A $2.4k; B $1.4k; total $11.7k", "", 0),
    ("Rating sensitivity: AAA $5.0k, AA $7.0k, A $8.0k, BBB $11.7k, BB $18.1k, B $32.8k", "", 0),
], size=13, space_after=12)
add_text(s, Inches(7.0), Inches(5.2), Inches(5.8), Inches(1.3),
         "Value delivered: the sensitivity chain (CVA01, rating table, SA-CVA weighted sensitivities) matters "
         "more than the point-in-time number, which is small by construction here.", size=12.5, italic=True, color=DARKGREY)

s = content_slide("DVA, FVA, and KVA (extra credit)")
rows = [["", "Close-out", "Level"], ["CVA", "$11.7k", "$247k"], ["DVA", "$11.2k", "$7.5k"],
        ["FVA", "$0.5k", "$240.0k"], ["KVA (10% CoC)", "$22.4k", "$470k"]]
simple_table(s, Inches(0.5), Inches(1.4), Inches(4.8), Inches(2.5), rows,
             col_widths=[2,1.5,1.5], font_size=13, header_size=13.5)
s.shapes.add_picture(f"{PNG}/fig_kva_compare.png", Inches(5.8), Inches(1.3), width=Inches(6.9))
add_text(s, Inches(0.5), Inches(4.3), Inches(4.8), Inches(2.5),
         "On close-out, positive/negative exposure are nearly symmetric so CVA/DVA nearly cancel; on level, "
         "the book is net in Capitolis' favour, so CVA/FCA dominate.\n\n"
         "KVA: K(t) = 8% x RW x alpha x EPE(t), CoC swept 8/10/12% (none given). Exceeds CVA because it "
         "scales the whole EPE profile, not a small IG default probability.", size=12, color=DARKGREY)

s = content_slide("Regulatory capital: SA-CVA and SA-CCR")
s.shapes.add_picture(f"{PNG}/fig37.png", Inches(0.3), Inches(1.3), width=Inches(7.4))
add_bullets(s, Inches(8.0), Inches(1.6), Inches(4.8), Inches(3.5), [
    ("SA-CVA capital: $0.10M close-out / $2.23M level (RWA $1.2M / $27.8M)", "", 0),
    ("Dominated by counterparty credit-spread risk on both conventions", "", 0),
    ("SA-CCR exposure at default: $260M, dominated by the replacement cost of BF_0003", "", 0),
], size=13.5, space_after=14)

s = content_slide("Extra credit: a risky-bond sample trade")
add_text(s, Inches(0.8), Inches(1.4), Inches(11), Inches(0.6),
         'The kickoff brief flagged "Risk bonds + CDS data for new sample trades." Delivered:',
         size=15, italic=True, color=NAVY)
add_bullets(s, Inches(1.0), Inches(2.3), Inches(10.8), Inches(2.3), [
    ("A sample risky-bond forward (25M notional, 5% BBB corporate; not part of the ESF book)", "", 0),
    ("Priced and simulated with a real issuer credit curve, re-anchored at every simulated node", "", 0),
    ("Same hazard-rate survival model and bond-index proxy construction as the counterparty CVA", "", 0),
], size=15, space_after=14)
add_text(s, Inches(1.0), Inches(4.8), Inches(10.8), Inches(1.2),
         "Limitation, disclosed: no real CDS quotes were obtainable for a hypothetical issuer, so the issuer "
         "curve is a bond-index proxy, not actual CDS -- delivered in spirit, not the full ask.",
         size=13.5, italic=True, color=DARKGREY)

print("Part VII done")


# ============================================================ PART VIII
part_divider("VIII", "Decisions, Limitations, and Conclusions")

s = content_slide("Full decision register")
rows = [["Decision", "Final choice", "Evidence", "Trade-off"],
        ["USD rate model", "Hull-White 1F (1-factor LGM)", "G2++ CRN gap only -3.0% at 16.1% fit error", "No independent curve twist"],
        ["JPY rate model", "Hull-White 1F, dedicated", "All 3 real a-routes invalid; $52.1M->$51.5M", "One extra simulated factor"],
        ["Rate vol source", "Realised 2y-30y Treasury", "Matches actual move; both pass Kupiec", "More window sensitivity"],
        ["Correlation", "Full 39x39 Cholesky", "PCA slower, up to 1.7% extra error", "Estimation noise, 741 pairs"],
        ["Sampling scheme", "Latin Hypercube", "50.6x lower RMSE vs. pseudo-random", "No edge on PFE99 Greeks"],
        ["Path count", "N=5,000 / 10,000 sign-off", "Rel. SE ~1.4% at 5,000", "~1.4% residual noise"],
        ["Exposure convention", "Close-out primary, level secondary", "Brief's own definition", "Real CSA terms unknown"],
        ["Greeks method", "Bump-reprice + CRN, pathwise check", "282x noise reduction; pathwise 1000x faster", "Rate Greeks need resim"],
        ["Rate DV01 attribution", "Par-instrument Jacobian", "82% vs. 54% correctly placed at 30y", "More bookkeeping"],
        ["Credit spread source", "ICE BofA rating-index OAS", "Basel-sanctioned fallback", "No sector/region, no WWR"],
        ["KVA", "Parametric, CoC grid", "Completes xVA extra-credit ask", "Not a real capital methodology"]]
simple_table(s, Inches(0.3), Inches(1.15), Inches(12.7), Inches(6.0), rows,
             col_widths=[1.7,2.3,4.7,2.8], font_size=10, header_size=10.5)

s = content_slide("Why this engine")
add_text(s, Inches(0.6), Inches(1.25), Inches(5.9), Inches(0.35), "Accurate", size=15, bold=True, color=NAVY)
add_bullets(s, Inches(0.7), Inches(1.65), Inches(5.9), Inches(1.5), [
    ("Parametric VaR vs. MC: ratio 0.98", "", 0),
    ("Kupiec backtest: all pass (equity and rates)", "", 0),
    ("DV01 additivity: 0.9995 / 1.0001", "", 0)], size=12.5, space_after=6)
add_text(s, Inches(0.6), Inches(3.1), Inches(5.9), Inches(0.35), "Fast", size=15, bold=True, color=NAVY)
add_bullets(s, Inches(0.7), Inches(3.5), Inches(5.9), Inches(1.5), [
    ("Equity/FX bumps: 93x cheaper than naive resimulation", "", 0),
    ("Pathwise delta: ~1000x faster than bump-and-reprice", "", 0),
    ("Exact rate-shift Greek: no resimulation at all", "", 0)], size=12.5, space_after=6)
add_text(s, Inches(0.6), Inches(4.95), Inches(5.9), Inches(0.35), "Explainable", size=15, bold=True, color=NAVY)
add_bullets(s, Inches(0.7), Inches(5.35), Inches(5.9), Inches(1.2), [
    ("Every parameter traced to a named, dated data source", "", 0),
    ("Every model choice backed by a quantified trade-off", "", 0)], size=12.5, space_after=6)
add_text(s, Inches(6.9), Inches(1.25), Inches(5.9), Inches(0.35), "Stable", size=15, bold=True, color=NAVY)
add_bullets(s, Inches(7.0), Inches(1.65), Inches(5.9), Inches(1.5), [
    ("CRN cuts Greeks noise 282x ($245k -> $1k)", "", 0),
    ("Exact rate-shift Greek agrees to 1e-15", "", 0),
    ("G2++ challenger within 3% of production on MPE99", "", 0)], size=12.5, space_after=6)
add_text(s, Inches(6.9), Inches(3.1), Inches(5.9), Inches(0.35), "Reproducible", size=15, bold=True, color=NAVY)
add_bullets(s, Inches(7.0), Inches(3.5), Inches(5.9), Inches(1.5), [
    ("Same seed -> identical paths and NPVs", "", 0),
    ("168 automated regression tests", "", 0),
    ("Every number in this deck traces to a committed result file", "", 0)], size=12.5, space_after=6)
add_text(s, Inches(0.6), Inches(6.6), Inches(12.1), Inches(0.5),
         "Accurate + fast + explainable + stable + reproducible -- each claim backed by a number in this deck.",
         size=14, bold=True, color=TEAL, align=PP_ALIGN.CENTER)

s = content_slide("Limitations and model risk")
rows = [["Area", "Limitation", "Effect", "Mitigation / next step"],
        ["Volatility", "Realised (3y), constant; no smile/clustering", "Vol x2 moves MPE99 +71%", "Implied vols; stress overlay"],
        ["Credit", "BBB proxy, flat term, independence assumed", "No wrong-way risk", "Real ratings/CDS; sector proxy"],
        ["Rates", "One factor in production", "Curve-twist risk not captured", "G2++ kept, re-tested"],
        ["Capital", "KVA uses an assumed CoC grid", "KVA is illustrative only", "Real methodology from Capitolis"],
        ["Validation", "One valuation date, no rolling backtest", "Model error over time unmeasured", "Rolling backtest"],
        ["Monte Carlo", "MPE99 converges slowly", "~1.4-2.2% spread at N=5,000", "Sign-off at N=10,000"]]
simple_table(s, Inches(0.3), Inches(1.2), Inches(12.7), Inches(5.6), rows,
             col_widths=[1.5,3.3,3.0,2.9], font_size=11, header_size=11.5)

s = content_slide("Decision made: production configuration")
add_text(s, Inches(0.6), Inches(1.25), Inches(11.8), Inches(0.35), "Production configuration", size=15, bold=True, color=NAVY)
add_bullets(s, Inches(0.7), Inches(1.65), Inches(11.8), Inches(2.1), [
    ("Hull-White 1F, a=0.0167, sigma=0.96%; JPY Hull-White 1F, a=0.001; G2++ kept as challenger", "Rates:", 0),
    ("correlated GBM, full 39-factor Cholesky, quanto drift for JPY names", "Equities / FX:", 0),
    ("Latin Hypercube, N=5,000 (sign-off 10,000), common random numbers for every Greek", "Simulation:", 0),
    ("close-out 10bd with t-1bd VM, per netting set: MPE99 $51.0M, peak EE $11.6M, CVA $11.7k", "Exposure:", 0),
], size=13.5, space_after=10)
add_text(s, Inches(0.6), Inches(4.4), Inches(5.9), Inches(0.35), "Monitor", size=15, bold=True, color=NAVY)
add_bullets(s, Inches(0.7), Inches(4.8), Inches(5.9), Inches(1.8), [
    ("Book slope exposure (would trigger a G2++ re-test)", "", 0),
    ("Volatility regime (implied vs. realised)", "", 0),
    ("Credit proxy vs. any real counterparty CDS", "", 0)], size=13, space_after=8)
add_text(s, Inches(6.9), Inches(4.4), Inches(5.9), Inches(0.35), "Next", size=15, bold=True, color=NAVY)
add_bullets(s, Inches(7.0), Inches(4.8), Inches(5.9), Inches(1.8), [
    ("Real ratings/CDS, own credit and funding spread", "", 0),
    ("Real capital methodology and CoC for KVA", "", 0),
    ("Sector-specific credit-spread proxy; rolling exposure backtest", "", 0)], size=13, space_after=8)

s = content_slide("Feedback tracker: both rounds, all 11 items")
earlier = ["Robust stress testing", "Sensitivities: method, cost, faster alt.", "PCA explainability and speed",
           "Final results explanation", "CVA walkthrough and set-up"]
later = ["2008 and more testing periods", "LHS to calculate sensitivities", "KVA addition", "CVA is for sensitivities",
         "DV01 via a Jacobian", "Excel parametric vol-bump test"]
add_text(s, Inches(0.6), Inches(1.2), Inches(5.9), Inches(0.35), "Earlier meeting", size=14, bold=True, color=NAVY)
add_text(s, Inches(6.9), Inches(1.2), Inches(5.9), Inches(0.35), "This meeting", size=14, bold=True, color=NAVY)
add_bullets(s, Inches(0.7), Inches(1.65), Inches(5.9), Inches(4.0),
            [(f"{i+1}. {t}  -- SELECTED", None, 0) for i, t in enumerate(earlier)], size=13.5, space_after=10)
add_bullets(s, Inches(7.0), Inches(1.65), Inches(5.9), Inches(4.0),
            [(f"{i+6}. {t}  -- SELECTED", None, 0) for i, t in enumerate(later)], size=13.5, space_after=10)
add_text(s, Inches(0.6), Inches(6.3), Inches(12.1), Inches(0.5),
         "Detail and results for every item are in the sections above.", size=12.5, italic=True, color=DARKGREY, align=PP_ALIGN.CENTER)

# ============================================================ THANK YOU
s = add_slide(); set_bg(s, NAVY)
add_text(s, Inches(1.5), Inches(3.0), Inches(10.3), Inches(1.0), "Thank You", size=44, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
add_text(s, Inches(1.5), Inches(3.9), Inches(10.3), Inches(0.6), "Questions and discussion", size=18, color=GOLD, align=PP_ALIGN.CENTER)

print("Part VIII done -- total slides:", len(prs.slides._sldIdLst))

prs.save(OUT)
print("SAVED:", OUT)
