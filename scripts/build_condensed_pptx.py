"""Condensed (<=30 slide) version of the final Capitolis CCR presentation.
Same content as build_final_pptx.py -- nothing removed, only merged onto
fewer, denser slides (part-divider slides folded into a header tag instead
of their own slide; related content slides combined). Native python-pptx,
no Node/pptxgenjs or LibreOffice available on this machine.
"""
import os
import fitz
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
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
OUT = os.path.join(ROOT, "docs", "Capitolis_CCR_Final_Presentation_Condensed.pptx")

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


def add_rect(slide, x, y, w, h, color):
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    shp.fill.solid()
    shp.fill.fore_color.rgb = color
    shp.line.fill.background()
    shp.shadow.inherit = False
    return shp


def add_text(slide, x, y, w, h, text, size=14, bold=False, color=DARKGREY, align=PP_ALIGN.LEFT,
             font="Calibri", italic=False, anchor=MSO_ANCHOR.TOP, line_spacing=1.08, wrap=True):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = wrap
    tf.vertical_anchor = anchor
    tf.margin_left = 0; tf.margin_right = 0; tf.margin_top = 0; tf.margin_bottom = 0
    for i, ln in enumerate(text.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = line_spacing
        r = p.add_run()
        r.text = ln
        r.font.size = Pt(size); r.font.bold = bold; r.font.italic = italic
        r.font.color.rgb = color; r.font.name = font
    return tb


def add_bullets(slide, x, y, w, h, items, size=12.5, color=DARKGREY, font="Calibri",
                 space_after=5, bullet_color=TEAL, line_spacing=1.04):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = 0; tf.margin_right = 0; tf.margin_top = 0; tf.margin_bottom = 0
    for i, item in enumerate(items):
        txt, lead, level = item if isinstance(item, tuple) else (item, None, 0)
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.level = level
        p.space_after = Pt(space_after)
        p.line_spacing = line_spacing
        pPr = p._p.get_or_add_pPr()
        buChar = pPr.makeelement(qn('a:buChar'), {'char': '•' if level == 0 else '–'})
        buFont = pPr.makeelement(qn('a:buFont'), {'typeface': 'Arial'})
        buClr = pPr.makeelement(qn('a:buClr'), {})
        srgb = pPr.makeelement(qn('a:srgbClr'), {'val': '%02X%02X%02X' % (bullet_color[0], bullet_color[1], bullet_color[2])})
        buClr.append(srgb); pPr.append(buClr); pPr.append(buFont); pPr.append(buChar)
        pPr.set('marL', str(Inches(0.2 + 0.2 * level)))
        pPr.set('indent', str(-Inches(0.2)))
        if lead:
            r1 = p.add_run(); r1.text = lead + " "; r1.font.bold = True; r1.font.size = Pt(size)
            r1.font.color.rgb = NAVY; r1.font.name = font
            r2 = p.add_run(); r2.text = txt; r2.font.size = Pt(size); r2.font.color.rgb = color; r2.font.name = font
        else:
            r = p.add_run(); r.text = txt; r.font.size = Pt(size); r.font.color.rgb = color; r.font.name = font
    return tb


def header(slide, part, title):
    add_rect(slide, 0, 0, SW, Inches(0.85), NAVY)
    add_text(slide, Inches(0.5), Inches(0.08), Inches(1.6), Inches(0.3), f"PART {part}",
             size=10.5, bold=True, color=GOLD)
    add_text(slide, Inches(0.5), Inches(0.33), Inches(12.3), Inches(0.5), title,
             size=21, bold=True, color=WHITE, anchor=MSO_ANCHOR.MIDDLE)


def content_slide(part, title):
    s = add_slide()
    set_bg(s)
    header(s, part, title)
    return s


def simple_table(slide, x, y, w, h, rows, col_widths=None, header_row=True, font_size=10.5, header_size=11):
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
            cell.margin_left = Pt(3); cell.margin_right = Pt(3); cell.margin_top = Pt(1); cell.margin_bottom = Pt(1)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            run = p.add_run()
            run.text = str(rows[r][c])
            run.font.size = Pt(header_size if (r == 0 and header_row) else font_size)
            run.font.name = "Calibri"
            run.font.bold = (r == 0 and header_row)
            run.font.color.rgb = WHITE if (r == 0 and header_row) else DARKGREY
            cell.fill.solid()
            cell.fill.fore_color.rgb = NAVY if (r == 0 and header_row) else (LIGHTBG if r % 2 == 0 else WHITE)
    return tbl_shape


print("helpers ready")


# ============================================================ TITLE + AGENDA
s = add_slide(); set_bg(s, NAVY)
add_rect(s, 0, Inches(4.55), SW, Pt(2.5), GOLD)
add_text(s, Inches(1.0), Inches(2.5), Inches(11.3), Inches(1.3),
         "Counterparty Credit Risk Engine for the Capitolis Book", size=34, bold=True, color=WHITE)
add_text(s, Inches(1.0), Inches(3.7), Inches(11.3), Inches(0.6),
         "Data, Models, Trade-offs, and Results -- Condensed", size=17, color=GOLD)
add_text(s, Inches(1.0), Inches(4.7), Inches(11.3), Inches(0.4),
         "Berkeley MFE Industry Project  |  Valuation date 2026-08-28", size=12.5, color=RGBColor(0xC9,0xD6,0xE6))

s = add_slide(); set_bg(s)
header(s, "-", "Agenda")
agenda = ["I. What Capitolis Gave Us", "II. Risks, Variables, and Data",
          "III. Models Considered, and Why the Final Model", "IV. Efficient Simulation",
          "V. What the Engine Does, and What It Finds", "VI. Sensitivities, Stress, and Validation",
          "VII. Credit and Capital", "VIII. Decisions, Limitations, and Conclusions"]
add_bullets(s, Inches(1.2), Inches(1.4), Inches(10.5), Inches(5.5),
            [(a, None, 0) for a in agenda], size=17, space_after=16)

# ============================================================ PART I (1 slide)
s = content_slide("I", "The Book, and the Exposure We Must Measure")
rows = [["Trade", "Type", "Cpty", "Underlying", "Ends", "Notional", "NPV t=0"],
        ["EQTRS_0001-3", "Eq. TRS", "A", "3 USD names each", "Oct'26", "50-99M", "-5.55/-1.08/+9.92M"],
        ["EQTRS_0004", "Eq. TRS", "B", "16 USD names", "Nov'26", "49.2M", "-0.87M"],
        ["EQTRS_0005/6", "Eq. TRS", "B", "3 JPY names each", "Oct'26", "12-31M", "+0.15/+1.63M"],
        ["EQTRS_0007/8", "Eq. TRS", "C", "7/3 USD names", "Oct'26/Jul'27", "95M/30M", "-0.37/+2.22M"],
        ["BF_0001/2", "Bond fwd", "A", "UST 3.88%'28/4.63%'35", "Oct/Nov'26", "100M/20M", "+0.51/-0.36M"],
        ["BF_0003", "Bond fwd", "C", "UST 2.88% 5/15/2049", "Dec'26", "500M", "+121.26M"],
        ["BF_0004", "Bond fwd", "C", "UST 1.13%'28", "Oct'26", "50M", "+1.97M"],
        ["BTRS_0001-4", "Bond TRS", "A/B/B/C", "UST 4.12/2.88/4.63/4.12%", "'27-'28", "5-40M", "+0.12/+0.21/+0.03/+0.04M"]]
simple_table(s, Inches(0.35), Inches(1.0), Inches(8.4), Inches(3.7), rows,
             col_widths=[1.2,0.7,0.5,1.7,0.9,0.8,1.6], font_size=8.3, header_size=8.8)
add_text(s, Inches(0.35), Inches(4.78), Inches(8.4), Inches(0.35),
         "Net MtM: CPTY_A +$3.57M   CPTY_B +$1.15M   CPTY_C +$125.12M   Book +$129.84M",
         size=10.5, bold=True, color=NAVY)
add_text(s, Inches(9.0), Inches(1.0), Inches(3.9), Inches(0.75),
         "Exposure = max( V(t+10bd) - V(t-1bd), 0 )", size=13.5, bold=True, color=NAVY)
add_bullets(s, Inches(9.0), Inches(1.85), Inches(3.9), Inches(2.6), [
    ("VM: netted value 1bd before t, two-way, no threshold", "", 0),
    ("MPoR: close-out 10 business days after t", "", 0),
    ("Netting within a counterparty only; never across", "", 0),
    ("Trades settling inside the window excluded", "", 0),
], size=11, space_after=7)
s.shapes.add_picture(f"{PNG}/fig26.png", Inches(9.0), Inches(4.55), width=Inches(3.9))

print("Part I done")


# ============================================================ PART II (2 slides)
s = content_slide("II", "Risk Factors and Data Philosophy")
rows = [["Risk factor", "Trades affected", "Model", "Calibrated from"],
        ["37 equity prices", "All 8 equity TRS", "Correlated GBM", "3y realised vol, dividend yield"],
        ["USDJPY", "Equity TRS, JPY names (2)", "GBM, quanto drift", "3y realised FX vol"],
        ["USD short rate", "Bond fwd/TRS, funding, disc.", "Hull-White 1F (=1F LGM)", "Swaption cube (a) + realised vol"],
        ["JPY short rate", "Drift of JPY names, USDJPY", "2nd Hull-White 1F", "Real JPY OIS curve, rate history"],
        ["Counterparty credit", "CVA/DVA/FVA/KVA only", "Hazard-rate survival", "ICE BofA rating OAS; no CDS"]]
simple_table(s, Inches(0.35), Inches(1.0), Inches(12.6), Inches(3.3), rows,
             col_widths=[1.6,2.1,2.0,2.3], font_size=11, header_size=11.5)
add_text(s, Inches(0.35), Inches(4.5), Inches(12.6), Inches(0.5),
         "39 correlated stochastic factors, one joint simulation, correlated by a single Cholesky factor every time step.",
         size=11.5, italic=True, color=DARKGREY)
add_text(s, Inches(0.35), Inches(5.1), Inches(12.6), Inches(0.3), "Data philosophy", size=13.5, bold=True, color=NAVY)
add_bullets(s, Inches(0.5), Inches(5.5), Inches(12.3), Inches(1.6), [
    ("Every number traces to a disclosed, real source -- no synthetic placeholders for calibration inputs", "", 0),
    ("Two tiers: public (Yahoo Finance, FRED, Databento) and licensed (Bloomberg, used/cross-checked, never redistributed raw)", "", 0),
], size=12, space_after=6)

s = content_slide("II", "Data Sources: Where Every Number Comes From")
rows = [["Source", "Used for", "Benefit of using real data"],
        ["Databento SOFR futures + Bloomberg long end", "USD discount curve, HW1F base", "Genuine market-implied curve; splice moved MPE99 $52.7M->$52.1M"],
        ["FRED Treasury CMT yields (public, since 1981)", "Realised long-end vol -> HW sigma (0.96%)", "Matches the actual yield vol this book depends on"],
        ["Bloomberg ATM normal swaption cube", "Mean-reversion a (0.0167, R2=0.84)", "Textbook, genuinely implied, forward-looking"],
        ["Yahoo Finance: 37 equities + USDJPY, 3y hist.", "Spots, div., realised vol, 39x39 correlation", "Public, free, long enough (2007-today) for reliable stats"],
        ["Real JPY OIS curve", "JPY Hull-White factor base curve", "Lets JPY rates move independently and go negative"],
        ["ICE BofA rating-index OAS (FRED)", "Counterparty/issuer credit spread proxy", "Basel MAR50.32(3)-sanctioned fallback; real market spreads"],
        ["Bloomberg (licensed): curve, vol cubes, surfaces", "Splice, calibration fits, model-risk checks", "Only source for genuine long-dated data; derived numbers only"]]
simple_table(s, Inches(0.35), Inches(1.0), Inches(12.6), Inches(5.9), rows,
             col_widths=[2.6,2.8,3.8], font_size=10.3, header_size=10.8)

print("Part II done")


# ============================================================ PART III (6 slides)
s = content_slide("III", "Models Considered: Rates, Equities, FX, Credit")
rows = [["Rate model", "Advantages", "Disadvantages", "Use"],
        ["Hull-White 1F (=1F LGM)", "Exact step, closed-form P(t,T); 2 params", "One factor -- curve near-parallel", "SELECTED"],
        ["G2++ (2-factor, =LGM2F)", "Level+slope move separately", "5 params; b at bound; 16.1% fit error", "Challenger"],
        ["2-factor + stoch. vol", "Vol clustering, fat tails", "Not implemented; more params", "Not built"]]
simple_table(s, Inches(0.35), Inches(1.0), Inches(12.6), Inches(1.9), rows,
             col_widths=[2.0,3.2,3.6,1.3], font_size=10.5, header_size=11)
rows2 = [["Equity/FX/credit model", "Advantages", "Disadvantages", "Use"],
         ["Equities: GBM", "Exact log-Euler step, fast", "No vol smile or clustering", "SELECTED"],
         ["Equities: stochastic vol", "Vol clustering, skew", "Not implemented; needs option surfaces", "Not built"],
         ["FX: GBM, quanto drift", "Consistent with both curves", "No smile", "SELECTED"],
         ["Credit: hazard-rate proxy", "Transparent, Basel-compliant", "No wrong-way risk, no spread vol", "SELECTED"],
         ["Credit: stochastic intensity", "Spread + wrong-way risk", "No counterparty CDS available", "Not available"]]
simple_table(s, Inches(0.35), Inches(3.1), Inches(12.6), Inches(3.3), rows2,
             col_widths=[2.3,2.9,3.6,1.3], font_size=10.2, header_size=10.8)
add_text(s, Inches(0.35), Inches(6.55), Inches(12.6), Inches(0.5),
         "The rate-model question is empirical: does the second factor materially change this book's exposure? Tested next.",
         size=11.5, italic=True, color=DARKGREY)

s = content_slide("III", "Correlation: Full Cholesky Matrix vs. PCA Factor Model")
s.shapes.add_picture(f"{PNG}/fig14.png", Inches(0.3), Inches(1.0), width=Inches(7.9))
rows = [["", "Full", "PCA k=5", "PCA k=10"], ["Step time (5,000 scen.)", "1.91s", "2.08s", "2.29s"],
        ["Variance explained", "100%", "47%", "62%"], ["Netting-set vol vs. full (B)", "-", "+1.7%", "+1.5%"]]
simple_table(s, Inches(8.5), Inches(1.1), Inches(4.4), Inches(1.8), rows,
             col_widths=[1.7,0.9,0.9,0.9], font_size=10, header_size=10.5)
add_text(s, Inches(8.5), Inches(3.2), Inches(4.4), Inches(3.6),
         "SELECTED full matrix: PCA is slower, not faster, at n=39 (draws k systematic + n idiosyncratic numbers, "
         "no dimensionality win). Loss of using PCA instead: no speed gain, and up to 1.7% extra sampling error. "
         "Kept only as an explainability tool: factor 1 (20%) is a broad market mode, factor 2 (8.9%) is Japan vs. US.",
         size=11.5, color=DARKGREY)

s = content_slide("III", "USD Rate Calibration: Mean Reversion and Volatility")
rows = [["Route (mean reversion a)", "Data", "a", "R2", "Use"],
        ["Swaption cube (preferred)", "Bloomberg ATM normal vol, 1M expiry", "0.0167", "0.845", "SELECTED"],
        ["SOFR-futures vol decay", "~2y Databento history, 8 contracts", "0.0458", "0.820", "cross-check"]]
simple_table(s, Inches(0.35), Inches(1.0), Inches(12.6), Inches(1.5), rows,
             col_widths=[2.6,3.4,1.1,1.0,1.3], font_size=11, header_size=11.5)
add_bullets(s, Inches(0.5), Inches(2.7), Inches(12.2), Inches(1.3), [
    ("Original source (overnight SOFR, 0.63%) understates long-dated yield moves (realised 10bd 20y move ~15bp vs. ~11bp implied)", "", 0),
    ("SELECTED: realised vol of 2y-30y Treasury yield changes directly, 0.96% -- validated by Kupiec backtest", "", 0)], size=11.5, space_after=6)
rows2 = [["Tenor", "Overnight-SOFR exc.", "Long-end sigma exc.", "Expected", "Pass?"],
         ["5y","1/1","4/3","1.6","yes"], ["10y","1/0","3/2","1.6","yes"], ["20y","1/1","3/1","1.6","yes"]]
simple_table(s, Inches(0.35), Inches(4.2), Inches(8.0), Inches(1.6), rows2,
             col_widths=[1.1,2.0,2.0,1.1,1.0], font_size=10.5, header_size=10.5)
s.shapes.add_picture(f"{PNG}/fig_dv01_compare.png", Inches(8.6), Inches(4.0), width=Inches(4.3))
add_text(s, Inches(8.6), Inches(6.1), Inches(4.3), Inches(1.1),
         "Book rate risk sits 82% in the 30y bucket (BF_0003, $500M, 2049 Treasury) -- one maturity dominates.",
         size=10.5, italic=True, color=DARKGREY)

print("Part III (1/2) done")


s = content_slide("III", "HW1F vs. G2++: Head to Head, Same Draws and Trades")
s.shapes.add_picture(f"{PNG}/fig19.png", Inches(0.3), Inches(1.0), width=Inches(7.2))
rows = [["", "HW1F", "G2++"], ["Fit to realised yield covariance", "-", "16.1% rel. error"],
        ["Parameters", "a=0.0167", "a=0.039, b=1.5 (at bound)"],
        ["Portfolio MPE99 (N=2,000, CRN)", "baseline $51.5M", "$50.0M (-3.0%)"],
        ["By counterparty", "-", "A -1%, B -3%, C -0%"]]
simple_table(s, Inches(7.7), Inches(1.0), Inches(5.3), Inches(2.3), rows,
             col_widths=[2.4,1.4,2.0], font_size=10.5, header_size=11)
add_text(s, Inches(7.7), Inches(3.5), Inches(5.3), Inches(3.3),
         "Benefit of 2-factor: lets the curve twist, not just shift. Cost: a parameter pinned at its bound, "
         "16% fit error, and a 3% move that doesn't justify the complexity here. Same random draws used in "
         "both runs (common random numbers), so the -3.0% gap is a real model difference, not sampling noise.",
         size=12, color=DARKGREY)

s = content_slide("III", "JPY Rates, and the Rate-Model Decision Register")
s.shapes.add_picture(f"{PNG}/fig16.png", Inches(0.3), Inches(1.0), width=Inches(4.6))
add_bullets(s, Inches(5.1), Inches(1.0), Inches(7.8), Inches(1.9), [
    ("REJECTED: constant USD-JPY differential -- cheap, cannot represent JPY moving independently or negative", "", 0),
    ("SELECTED: a second, real, simulated Hull-White 1F from the JPY OIS curve. TONA negative/near-zero most of 25 years", "", 0),
], size=11.5, space_after=6)
rows = [["JPY a route","Fitted a"],["OIS history","-0.0261"],["Swaption cube","-0.0374"],["JGB history","-0.0203"]]
simple_table(s, Inches(5.1), Inches(3.0), Inches(3.3), Inches(1.6), rows, col_widths=[2,1], font_size=10.5, header_size=10.5)
add_text(s, Inches(8.6), Inches(3.0), Inches(4.3), Inches(1.6),
         "All invalid (negative a): JPY vol rises with tenor. Used a=0.001 floor. Attribution: $52.1M -> $51.5M.",
         size=10.5, color=DARKGREY)
rows2 = [["Decision", "Final choice", "Evidence", "Trade-off"],
         ["USD rate model", "Hull-White 1F", "G2++ gap only -3.0% at 16.1% fit error, param. at bound", "No curve twist"],
         ["JPY rate model", "Hull-White 1F, dedicated", "All 3 real a-routes invalid; $52.1M->$51.5M", "1 extra factor"],
         ["Rate vol source", "Realised 2y-30y Treasury", "Matches actual move; both pass Kupiec", "More window sensitivity"]]
simple_table(s, Inches(0.35), Inches(4.9), Inches(12.6), Inches(2.1), rows2,
             col_widths=[1.7,2.3,5.0,2.5], font_size=10, header_size=10.5)

print("Part III done")


# ============================================================ PART IV (2 slides)
s = content_slide("IV", "Sampling Scheme: Five Methods, and What Latin Hypercube Does")
rows = [["Method", "RMSE", "vs. pseudo-random", "ms/trial"],
        ["Pseudo-random", "1.456", "1.0x (baseline)", "0.30"], ["Antithetic", "1.079", "1.3x better", "0.31"],
        ["Moment-matched", "0.232", "6.3x better", "0.55"], ["Sobol", "0.051", "28.8x better", "1.65"],
        ["Latin Hypercube", "0.029", "50.6x better", "0.98"]]
simple_table(s, Inches(0.35), Inches(1.0), Inches(6.3), Inches(2.3), rows,
             col_widths=[2.0,1.1,1.8,1.1], font_size=10.5, header_size=11)
add_text(s, Inches(6.9), Inches(1.0), Inches(6.0), Inches(2.3),
         "Real 663-dim engine check: no method wins both -- Sobol lowest PFE std (2.72M vs. 4.29M pseudo-random), "
         "moment-matched lowest median std (0.40M vs. 0.76M). LHS competitive on both (3.73M/0.48M), never worst.",
         size=11, color=DARKGREY)
add_text(s, Inches(0.35), Inches(3.5), Inches(12.6), Inches(0.5),
         "SELECTED Latin Hypercube: best on the controlled test, competitive, negligible extra cost.",
         size=13, bold=True, color=TEAL)
add_bullets(s, Inches(0.5), Inches(4.2), Inches(12.2), Inches(2.5), [
    ("Does stratify every marginal: each factor's draws cover equal-probability bins, tails always visited", "", 0),
    ("Does not stratify the joint distribution (~663 effective dims) -- interaction noise remains", "", 0),
    ("Unbiased (inverse-normal-CDF mapped); cost (N x dim) negligible next to repricing", "", 0),
    ("This is why LHS helps a smooth average (EE) more than a 99th-pct tail (PFE99)", "", 0),
], size=12.5, space_after=8)

s = content_slide("IV", "Scenario Count: Convergence Results and the Decision")
rows = [["Netting set","N=250","N=500","N=1,000","N=2,000","N=3,000"],
        ["CPTY_A","6.3%","5.1%","3.2%","2.6%","2.5%"], ["CPTY_B","5.1%","4.7%","3.8%","3.5%","3.5%"],
        ["CPTY_C","5.9%","4.8%","3.8%","3.1%","3.1%"], ["Portfolio","7.1%","4.9%","3.3%","2.2%","2.2%"]]
simple_table(s, Inches(0.35), Inches(1.0), Inches(7.2), Inches(1.9), rows,
             col_widths=[1.4,1,1,1,1,1], font_size=9.5, header_size=10)
rows2 = [["N","1,000","5,000","10,000","20,000","30,000"],["Rel. SE","0.66%","0.29%","0.21%","0.09%","0 (ref.)"],
         ["Time (8c)","119s","479s","929s","1,829s","2,729s"]]
simple_table(s, Inches(7.8), Inches(1.0), Inches(5.2), Inches(1.9), rows2,
             col_widths=[1.1,0.9,0.9,0.9,0.9,0.9], font_size=9, header_size=9.5)
add_text(s, Inches(0.35), Inches(3.2), Inches(12.6), Inches(0.9),
         "SELECTED: N=5,000 standard reporting (rel. SE ~1.4%, ~8 min); N=10,000 sign-off; beyond ~20,000 "
         "marginal SE gain per batch falls below 30% while cost scales linearly.", size=12.5, bold=True, color=TEAL)
rows3 = [["Decision", "Final choice", "Evidence", "Trade-off"],
         ["Sampling scheme", "Latin Hypercube", "50.6x lower RMSE vs. pseudo-random on controlled test", "No edge on PFE99 Greeks"],
         ["Scenario count", "N=5,000 / 10,000 sign-off", "Rel. SE ~1.4% at N=5,000", "~1.4% residual noise remains"]]
simple_table(s, Inches(0.35), Inches(4.4), Inches(12.6), Inches(2.3), rows3,
             col_widths=[1.8,2.4,5.0,2.9], font_size=11, header_size=11.5)

print("Part IV done")


# ============================================================ PART V (5 slides)
s = content_slide("V", "The Simulation Pipeline, and Key Equations")
steps = [("1. Calibrate", "Pull real data -> fit every model parameter"),
         ("2. Draw", "Latin Hypercube -> correlated shocks (Cholesky, real 39x39 matrix)"),
         ("3. Simulate", "Step every risk factor jointly across the full time grid"),
         ("4. Reprice", "Feed simulated states into the provided pricers -- every trade/date/scenario"),
         ("5. Aggregate", "Net by counterparty -> EE/median PFE/PFE99/MPE, both conventions"),
         ("6. Downstream", "Greeks, stress, CVA/DVA/FVA/KVA, SA-CVA, SA-CCR -- same paths")]
add_bullets(s, Inches(0.5), Inches(1.0), Inches(6.2), Inches(5.5), [(d, t, 0) for t, d in steps], size=11.5, space_after=10)
eqs = [("Rates (rates.py) -- Hull-White 1F:", "dr=[theta(t)-a r(t)]dt+sigma dW,  r(t)=x(t)+alpha(t)"),
       ("Equity/FX (equity_fx.py) -- log-Euler GBM:", "d ln S=(r_USD-q-0.5 sig^2)dt+sig dW"),
       ("Correlated shocks (engine.py):", "Z = L * Z_indep  (Cholesky of real 39x39 matrix)"),
       ("Exposure (spec_exposure.py):", "Exposure_c(t)=max(V_c(t+10bd)-V_c(t-1bd),0)"),
       ("CVA (cva.py), MAR50.32:", "CVA = LGD * sum_i DEE(t_i)*PD(t_i-1,t_i)")]
y = Inches(1.0)
for lead, eq in eqs:
    add_text(s, Inches(7.0), y, Inches(5.9), Inches(0.3), lead, size=10.5, bold=True, color=NAVY)
    add_text(s, Inches(7.2), y + Inches(0.3), Inches(5.7), Inches(0.35), eq, size=10.5, color=DARKGREY, font="Courier New")
    y += Inches(0.92)

s = content_slide("V", "What the Simulated Paths Actually Look Like")
s.shapes.add_picture(f"{PNG}/fig11.png", Inches(0.25), Inches(1.0), width=Inches(6.2))
s.shapes.add_picture(f"{PNG}/fig12.png", Inches(6.6), Inches(1.0), width=Inches(6.4))
add_text(s, Inches(0.35), Inches(6.5), Inches(12.6), Inches(0.6),
         "Left: simulated USD short rate (median tracks today's forward curve). Right: simulated USDJPY and "
         "two equities with 1-99% and 25-75% percentile bands.", size=11.5, italic=True, color=DARKGREY, align=PP_ALIGN.CENTER)

s = content_slide("V", "Headline Results (5,000 Scenarios, Close-out Exposure)")
rows = [["", "MPE99", "Peak EE"], ["CPTY_A","$25.9M","$4.7M"], ["CPTY_B","$9.6M","$1.8M"],
        ["CPTY_C","$29.6M","$5.2M"], ["Portfolio","$51.0M","$11.6M"]]
simple_table(s, Inches(0.35), Inches(1.0), Inches(3.3), Inches(2.2), rows,
             col_widths=[1.2,1,1], font_size=11.5, header_size=12)
add_bullets(s, Inches(0.35), Inches(3.4), Inches(3.3), Inches(2.6), [
    ("CVA $11.7k close-out / $247k level", "", 0), ("SA-CVA capital $0.10M / $2.23M", "", 0),
    ("SA-CCR EAD $260M", "", 0), ("KVA (10% CoC) $22.4k / $470k", "", 0),
    ("Level exposure MPE99: $201.9M", "", 0)], size=11.5, space_after=8)
s.shapes.add_picture(f"{PNG}/fig25.png", Inches(3.9), Inches(1.0), width=Inches(9.0))

print("Part V (1/2) done")


s = content_slide("V", "What Drives Each Counterparty: Greeks, Additivity, Diagnostics")
rows = [["", "Eq delta/+1%", "FX delta/+1%", "DV01/+1bp"], ["CPTY_A","-$2.25M","$0","$31k"],
        ["CPTY_B","-$0.96M","+$0.42M","-$4k"], ["CPTY_C","-$1.24M","$0","$594k"],
        ["Book","-$4.46M","+$0.42M","$622k"]]
simple_table(s, Inches(0.35), Inches(1.0), Inches(5.1), Inches(1.9), rows,
             col_widths=[1.1,1.3,1.3,1.3], font_size=9.8, header_size=10.2)
add_text(s, Inches(0.35), Inches(3.0), Inches(5.1), Inches(0.9),
         "Rank correlation: A-B 0.34, A-C 0.33, B-C 0.12. A is most equity-driven; C is the rate netting set "
         "(one $500M 2049 forward). Yield-equity corr. approx 0.00 -- no reliable offset.", size=9.8, color=DARKGREY)
s.shapes.add_picture(f"{PNG}/fig28.png", Inches(5.6), Inches(1.0), width=Inches(3.5))
add_text(s, Inches(5.6), Inches(4.75), Inches(3.5), Inches(2.0),
         "No netting across counterparties by construction; all 3 peak in the same weeks (no timing "
         "diversification); rank corr. 0.12-0.34. Result: Portfolio MPE99 ($51.0M) ~ A+C ($54.4M), 78% of "
         "the sum of all three.", size=9.5, color=DARKGREY)
s.shapes.add_picture(f"{PNG}/fig30.png", Inches(9.2), Inches(1.0), width=Inches(3.8))
add_text(s, Inches(9.2), Inches(4.75), Inches(3.8), Inches(2.0),
         "Expected NPV by trade: BF_0003 dominates, disappears at its Dec 2026 settlement.", size=9.5, italic=True, color=DARKGREY)

print("Part V done")


# ============================================================ PART VI (7 slides)
s = content_slide("VI", "Sensitivities: Common Random Numbers, and Method Comparison")
add_bullets(s, Inches(0.5), Inches(1.0), Inches(6.1), Inches(2.3), [
    ("Independent random draws: estimator std. dev. $245k -- too noisy", "", 0),
    ("Common random numbers (CRN): std. dev. $1k -- 282x noise reduction", "", 0),
    ("This, not the sampling scheme, controls Greeks precision", "", 0),
    ("Equity/FX bumps rescale GBM paths exactly: 78 bumps cost 88s actual vs. ~8,166s naive -- 93x cheaper", "", 0),
], size=12, space_after=8)
s.shapes.add_picture(f"{PNG}/fig_greeks_cost.png", Inches(0.9), Inches(3.5), width=Inches(5.2))
rows = [["Method", "Cost", "Verdict"],
        ["Bump, independent draws", "baseline, $245k noise", "REJECTED: noise swamps signal"],
        ["Bump, CRN (all reported)", "~260s (equity EE, N=300)", "SELECTED: works on black-box, quantiles"],
        ["Pathwise (eq/FX only)", "0.2-0.4s", "SELECTED cross-check: ~1000x faster, 0.02-0.4% agree"],
        ["Adjoint differentiation", "~3-5 valuations for all Greeks", "REJECTED: needs differentiable pricers"]]
simple_table(s, Inches(6.5), Inches(1.0), Inches(6.5), Inches(2.9), rows,
             col_widths=[2.1,2.1,3.0], font_size=10, header_size=10.5)
add_text(s, Inches(6.5), Inches(4.2), Inches(6.5), Inches(1.0),
         "Rate/vol Greeks (13 needed) still require resimulation at ~109s each -- unless the exact analytic "
         "method on the next slide applies.", size=11, italic=True, color=DARKGREY)

s = content_slide("VI", "Rate DV01: Zero-Grid Bump vs. Par-Instrument Jacobian")
rows = [["Tenor bucket", "Old (zero-grid)", "New (par-instr.)"], ["0.25y","-2,182","-2,892"], ["0.5y","-46","-1"],
        ["1y","-44","-14"], ["2y","-131","-205"], ["3y","-96","-105"], ["5y","-770","-713"],
        ["10y","-18,324 (39%)","-6,592 (11%)"], ["30y","-24,988 (54%)","-47,191 (82%)"],
        ["Sum", "-46,580", "-57,713"], ["Parallel bump", "-46,605", "-57,705"]]
simple_table(s, Inches(0.35), Inches(1.0), Inches(5.4), Inches(5.3), rows,
             col_widths=[1.8,1.3,1.3], font_size=10, header_size=10.5)
add_bullets(s, Inches(6.0), Inches(1.0), Inches(6.9), Inches(3.5), [
    ("Old: bump the fitted zero curve at 8 hand-picked tenors, triangular interpolation -- disconnected from "
     "how the curve was built", "", 0),
    ("SELECTED New: bump the curve's own ~45 native construction pillars, grouped into the same 8 buckets -- "
     "the genuine par-instrument (Jacobian) sensitivity", "", 0),
    ("Result: 82% of DV01 correctly in the 30y bucket, not 54%. Both sum to the same total (within 0.05%) -- "
     "total risk was always right, attribution across tenor was wrong", "", 0),
], size=12, space_after=12)
s.shapes.add_picture(f"{PNG}/fig_dv01_compare.png", Inches(6.3), Inches(4.3), width=Inches(6.2))

print("Part VI (1/4) done")


s = content_slide("VI", "An Exact Rate Greek, Reusing the Same Simulated Draws")
add_text(s, Inches(0.5), Inches(1.0), Inches(12.3), Inches(0.9),
         "In Hull-White 1F, r(t)=x(t)+alpha(t): x(t) is the simulated random factor; alpha(t) is deterministic "
         "(depends only on the curve). A curve bump that leaves a, sigma fixed leaves x(t) IDENTICAL to the base run.",
         size=13, color=DARKGREY)
add_bullets(s, Inches(0.7), Inches(2.0), Inches(11.8), Inches(1.6), [
    ("The whole bump effect is one closed-form number per date, added to the base run's own paths -- no "
     "resimulation, no new random draws", "", 0),
    ("Validated against a true independent resimulation: agreement to 1e-15 relative precision", "", 0),
], size=13, space_after=8)
add_text(s, Inches(0.7), Inches(3.7), Inches(11.8), Inches(0.4),
         "Separately: does Latin Hypercube itself reduce Greeks noise? Mixed result:", size=12.5, bold=True, color=NAVY)
s.shapes.add_picture(f"{PNG}/fig_sampling_greeks.png", Inches(2.9), Inches(4.1), width=Inches(7.5))

s = content_slide("VI", "Stress Testing: Design and Results")
rows = [["Family", "Scenarios"], ["Hypothetical (8)", "EQ_DOWN/UP_30, JPY_STRONG/WEAK_15, RATES_UP/DOWN_200, FLIGHT_TO_QUALITY, STAGFLATION"],
        ["Historical (5)", "HIST_EQUITY_CRASH, HIST_RATES_SPIKE, HIST_YEN_SURGE, HIST_GFC_2008, HIST_CHINA_DEVAL_2015"]]
simple_table(s, Inches(0.35), Inches(1.0), Inches(12.6), Inches(1.3), rows,
             col_widths=[1.5,9.0], font_size=10, header_size=10.5)
rows2 = [["Scenario","Close-out MPE99","Level MPE99"], ["EQ_DOWN_30","-15.3%","+62.3%"],["RATES_DOWN_200","+22.0%","-69.0%"],
         ["STAGFLATION","-24.1%","+89.1%"],["FLIGHT_TO_QUALITY","-2.0%","+19.6%"],["HIST_GFC_2008","-12.7%","+55.6%"]]
simple_table(s, Inches(0.5), Inches(2.6), Inches(5.6), Inches(2.9), rows2,
             col_widths=[2.2,1.4,1.4], font_size=10, header_size=10.5)
s.shapes.add_picture(f"{PNG}/fig33.png", Inches(6.3), Inches(2.6), width=Inches(6.6))
add_text(s, Inches(0.5), Inches(5.7), Inches(12.3), Inches(1.2),
         "Close-out exposure is far less sensitive to instantaneous level shocks than level exposure (margin "
         "is why). Equity-driven trades react only to equity/FX shocks; bond trades react only to rate shocks.",
         size=12, italic=True, color=DARKGREY)

s = content_slide("VI", "Extending the History: 2008 and 2015; Per-Trade Sensitivity")
s.shapes.add_picture(f"{PNG}/fig_hist_scenarios.png", Inches(0.3), Inches(1.0), width=Inches(5.0))
add_bullets(s, Inches(5.5), Inches(1.0), Inches(7.3), Inches(2.2), [
    ("Extended public price history back to 2007 (28 of 37 names covered)", "", 0),
    ("2008 GFC: Sep 29-Oct 10, 2008; -23% median / -44% worst single-name", "", 0),
    ("2015 China deval.: Aug 2015, -6.8% median", "", 0),
    ("Both land inside the range existing scenarios already covered -- a validation finding, not just more coverage", "", 0),
], size=11.5, space_after=7)
s.shapes.add_picture(f"{PNG}/fig34.png", Inches(3.65), Inches(3.65), height=Inches(3.6))

print("Part VI (3/4) done")


s = content_slide("VI", "Validation Summary, Attribution Decomposition, Model Risk")
rows = [["Check", "Result"], ["Put-call parity (GBM)", "max abs error 2.1e-4 (float precision)"],
        ["Zero-coupon bond repricing (HW1F)", "analytic vs. simulated: < 0.03% at all tenors"],
        ["Martingale test (discounted numeraire)", "mean drift < 0.1% of notional"],
        ["Independent resimulation (exact rate greek)", "agreement to 1e-15 relative"]]
simple_table(s, Inches(0.35), Inches(1.0), Inches(6.3), Inches(2.3), rows,
             col_widths=[3.0,3.3], font_size=10, header_size=10.5)
rows2 = [["Step added", "MPE99 impact"], ["Base (8-tenor zero curve)","$52.7M"],
         ["+ Bloomberg long-end splice","$52.1M (-1.1%)"], ["+ Par-instrument DV01 (attrib. only)","no change to MPE99"],
         ["+ PCA-10 factor correlation (CPTY_B netting vol)","+1.5%"]]
simple_table(s, Inches(6.9), Inches(1.0), Inches(6.0), Inches(2.3), rows2,
             col_widths=[3.6,2.4], font_size=10, header_size=10.5)
add_bullets(s, Inches(0.5), Inches(3.7), Inches(12.3), Inches(3.2), [
    ("Model risk, biggest levers: (1) correlation estimation window -- 2yr daily vs. 5yr: netting-set vol shifts "
     "2-4%; (2) HW1F vs. G2++ on the long end -- < 1% MPE99 difference, HW1F retained; (3) GBM vs. local/stoch vol "
     "for equities -- not tested, flagged as a limitation; (4) proxy curve selection for bond TRS names", "", 0),
    ("All of these are documented, bounded, and backed by a specific sensitivity run -- none is a blind assumption", "", 0),
], size=13, space_after=10)

# ============================================================ PART VII (2 slides)
s = content_slide("VII", "CVA, DVA, FVA, KVA -- Methodology and Numbers")
add_bullets(s, Inches(0.5), Inches(1.0), Inches(6.1), Inches(3.0), [
    ("CVA (MAR50.32): LGD x sum DEE(t_i) x PD(t_i-1,t_i), own-paths DEE, Bloomberg-implied hazard rates", "", 0),
    ("DVA: same formula, own-side default leg, own hazard curve", "", 0),
    ("FVA: funding spread x expected funding exposure over the life of the trade", "", 0),
    ("KVA: cost-of-capital rate x SA-CCR capital profile, discounted over trade life", "", 0),
], size=12, space_after=9)
rows = [["Metric","Close-out","Level"], ["CVA","$11.7k","$247k"], ["DVA","$9.8k","$198k"],
        ["FVA","$14.2k","$310k"], ["KVA (10% CoC)","$22.4k","$470k"]]
simple_table(s, Inches(6.9), Inches(1.0), Inches(6.0), Inches(2.6), rows,
             col_widths=[2.0,2.0,2.0], font_size=11, header_size=11.5)
add_text(s, Inches(6.9), Inches(3.9), Inches(6.0), Inches(1.0),
         "All four scale with the exposure convention chosen -- close-out is the economically correct basis "
         "(reflects margin), level overstates by ~20x.", size=11, italic=True, color=DARKGREY)

s = content_slide("VII", "SA-CVA, SA-CCR, and the Risky-Bond Extra Credit")
add_bullets(s, Inches(0.5), Inches(1.0), Inches(6.1), Inches(2.6), [
    ("SA-CVA capital: $0.10M (close-out) / $2.23M (level) -- regulatory formula, own EAD/sensitivity inputs", "", 0),
    ("SA-CCR EAD: $260M -- replacement cost + PFE add-on, per Basel/CRE52", "", 0),
    ("Both computed once from the same simulated book, not a separate model", "", 0),
], size=12, space_after=9)
add_bullets(s, Inches(6.9), Inches(1.0), Inches(6.0), Inches(3.0), [
    ("Extra credit: price the bond legs themselves as risky (hazard-rate) bonds, not just proxy-indexed TRS", "", 0),
    ("Implemented via the same Bloomberg-implied hazard curves used for CVA/DVA -- consistent credit risk "
     "treatment across pricing and xVA", "", 0),
    ("Framed in the kickoff deck as a stretch goal; delivered using the existing data pipeline, no new data source", "", 0),
], size=12, space_after=9)

# ============================================================ PART VIII (4 slides)
s = content_slide("VIII", "The Full Decision Register")
rows = [["Area","Decision","Why"],
        ["Rate model","HW1F (1-factor LGM)","G2++ < 1% MPE99 gain; HW1F simpler, faster, calibrates cleanly"],
        ["Equity/FX model","Correlated GBM + quanto drift","Matches book's instrument set; local/stoch vol unnecessary at this horizon"],
        ["Exposure convention","Close-out (margin period of risk)","Economically correct; level overstates by ~20x"],
        ["Sampling","Latin Hypercube","50.6x RMSE reduction on controlled test, negligible cost"],
        ["Scenario count","N=5,000 report / 10,000 sign-off","Rel. SE ~1.4% / ~1.0%, runtime acceptable"],
        ["Greeks","CRN bump-and-reprice + exact rate analytic + pathwise cross-check","282x noise reduction; 93x cheaper eq/FX; exact for rates"],
        ["DV01 attribution","Par-instrument (Jacobian) bucketing","Correct tenor attribution (82% in 30y vs. 54%); same total"],
        ["Correlation","Full empirical + PCA-10 cross-check","PCA-10 within 1.5% of full matrix; full matrix retained"]]
simple_table(s, Inches(0.35), Inches(1.0), Inches(12.6), Inches(5.6), rows,
             col_widths=[1.5,2.8,8.3], font_size=10, header_size=10.5)

s = content_slide("VIII", "Why This Engine")
add_bullets(s, Inches(0.5), Inches(1.0), Inches(12.3), Inches(4.5), [
    ("Every model choice is backed by a quantified comparison against at least one alternative -- not asserted", "", 0),
    ("Every number in this deck traces to a script and a JSON output in the repository -- reproducible, not hand-typed", "", 0),
    ("Rate Greeks use an exact analytic method validated to 1e-15 -- no Monte Carlo noise where it can be avoided", "", 0),
    ("DV01 attribution fixed to the genuine par-instrument sensitivity, not a disconnected zero-grid bump", "", 0),
    ("168 automated regression tests cover the pricers, calibration, simulation, and risk modules", "", 0),
    ("xVA, SA-CVA, SA-CCR, and risky-bond pricing all reuse the same simulated paths -- one consistent engine, not bolted-on add-ons", "", 0),
], size=14, space_after=14)

s = content_slide("VIII", "Limitations, and Production Configuration")
rows = [["Limitation","Mitigation / status"],
        ["GBM equity model: no vol smile/skew","Flagged; local/stoch vol a natural extension"],
        ["Correlation from 2yr daily history","Stability checked vs. 5yr window; PCA-10 cross-check"],
        ["Proxy curves for some bond TRS names","Sector-IG / longer-history proxy, documented per name"],
        ["Historical scenarios limited pre-2007","Extended via public price history to 2008 GFC, 2015 deval."],
        ["No stochastic correlation / regime-switching","Out of scope; static correlation is standard industry practice"]]
simple_table(s, Inches(0.35), Inches(1.0), Inches(7.0), Inches(2.8), rows,
             col_widths=[3.4,3.6], font_size=10, header_size=10.5)
add_bullets(s, Inches(7.6), Inches(1.0), Inches(5.3), Inches(2.8), [
    ("Report: N=10,000, close-out exposure, HW1F+GBM, LHS, full empirical correlation", "", 0),
    ("Greeks: CRN bump-and-reprice (black-box), exact analytic (rates), pathwise (eq/FX cross-check)", "", 0),
    ("Stress: 13 scenarios (8 hypothetical + 5 historical, now including 2008/2015)", "", 0),
], size=11.5, space_after=8)

s = content_slide("VIII", "Feedback Incorporated")
add_bullets(s, Inches(0.5), Inches(1.0), Inches(12.3), Inches(4.8), [
    ("Par-instrument DV01 attribution replaced the disconnected zero-grid bump", "", 0),
    ("Exact analytic rate Greek added, cross-validated to 1e-15 against resimulation", "", 0),
    ("Bloomberg long-end curve splice added; full numeric attribution of its effect on MPE99", "", 0),
    ("PCA factor-reduced correlation tested as a cross-check against the full empirical matrix", "", 0),
    ("Historical stress scenarios extended back to the 2008 GFC and 2015 China devaluation", "", 0),
    ("xVA extra credit (CVA/DVA/FVA/KVA) and risky-bond pricing both delivered using existing data pipeline", "", 0),
], size=14, space_after=14)

s = add_slide()
set_bg(s, NAVY)
add_text(s, Inches(1.5), Inches(3.0), Inches(10.3), Inches(1.0), "Thank You",
         size=40, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
add_text(s, Inches(1.5), Inches(4.0), Inches(10.3), Inches(0.6), "Questions and Discussion",
         size=18, color=GOLD, align=PP_ALIGN.CENTER)

prs.save(OUT)
print(f"SAVED {OUT} with {len(prs.slides.__iter__.__self__._sldIdLst)} slides")
print("Part VI done, Part VII done, Part VIII done, Thank You done")
