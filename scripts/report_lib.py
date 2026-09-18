"""Small reportlab/matplotlib helpers for scripts/build_report.py.

Hard rule inherited from earlier report builds: every string handed to
reportlab must be pure ASCII (non-ASCII characters trigger missing-glyph
failures in this environment), so A() asserts it instead of silently
mangling.
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (BaseDocTemplate, Frame, Image, KeepTogether, PageBreak,
                                PageTemplate, Paragraph, Preformatted, Spacer, Table,
                                TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

NAVY = "#1F3A5F"
TEAL = "#2A9D8F"
ORANGE = "#E76F51"
GOLD = "#E9C46A"
GREY = "#8D99AE"
PAL = [NAVY, TEAL, ORANGE, GOLD, GREY, "#6D597A", "#B56576"]

plt.rcParams.update({
    "font.size": 8, "axes.titlesize": 9, "axes.labelsize": 8, "legend.fontsize": 7,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
    "grid.alpha": 0.25, "figure.dpi": 150, "axes.prop_cycle": matplotlib.cycler(color=PAL),
})

_ss = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=_ss["BodyText"], fontName="Helvetica", fontSize=9.2,
                      leading=12.6, alignment=TA_LEFT, spaceAfter=5)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=7.8, leading=10, textColor=colors.HexColor("#444444"))
CAP = ParagraphStyle("cap", parent=BODY, fontSize=7.8, leading=10, textColor=colors.HexColor("#333333"),
                     fontName="Helvetica-Oblique", spaceAfter=9)
TOCH = ParagraphStyle("toch", fontName="Helvetica-Bold", fontSize=16, textColor=colors.HexColor(NAVY), spaceAfter=8)
H1 = ParagraphStyle("h1", parent=_ss["Heading1"], fontName="Helvetica-Bold", fontSize=16,
                    textColor=colors.HexColor(NAVY), spaceBefore=4, spaceAfter=8)
H2 = ParagraphStyle("h2", parent=_ss["Heading2"], fontName="Helvetica-Bold", fontSize=11.5,
                    textColor=colors.HexColor(NAVY), spaceBefore=8, spaceAfter=4)
H3 = ParagraphStyle("h3", parent=_ss["Heading3"], fontName="Helvetica-Bold", fontSize=9.6,
                    textColor=colors.HexColor("#333333"), spaceBefore=5, spaceAfter=2)
BUL = ParagraphStyle("bul", parent=BODY, leftIndent=14, bulletIndent=4, spaceAfter=2)
CODE = ParagraphStyle("code", fontName="Courier", fontSize=7, leading=9, leftIndent=8,
                      backColor=colors.HexColor("#F3F5F8"), borderPadding=4, spaceAfter=7)
CALL = ParagraphStyle("call", parent=BODY, backColor=colors.HexColor("#EAF4F2"), borderPadding=6,
                      leftIndent=6, rightIndent=6, spaceBefore=4, spaceAfter=9)

W = 6.6 * inch  # usable width


def A(s):
    s = str(s)
    bad = [c for c in s if ord(c) > 127]
    assert not bad, f"non-ASCII in report text: {bad[:5]} in {s[:60]!r}"
    return s


def P(text, style=BODY):
    return Paragraph(A(text), style)


def B(items, style=BUL):
    return [Paragraph(A(t), style, bulletText="-") for t in items]


def code(text):
    longest = max(len(l) for l in text.splitlines())
    assert longest <= 108, f"code line too long ({longest}): {text[:50]!r}"
    return Preformatted(A(text), CODE)


def callout(text):
    return Paragraph(A(text), CALL)


def tbl(rows, widths=None, header=True, font=7.8, zebra=True, align_right_from=None):
    cell = ParagraphStyle("cell", parent=BODY, fontSize=font, leading=font + 2.2, spaceAfter=0)
    cellb = ParagraphStyle("cellb", parent=cell, fontName="Helvetica-Bold", textColor=colors.white)
    data = []
    for ri, r in enumerate(rows):
        st = cellb if (header and ri == 0) else cell
        data.append([Paragraph(A(c), st) for c in r])
    if widths is None:
        widths = [W / len(rows[0])] * len(rows[0])
    else:
        tot = sum(widths)
        widths = [w / tot * W for w in widths]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#C9CED6")),
             ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
             ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(NAVY)))
    if zebra:
        for i in range(1 if header else 0, len(rows)):
            if i % 2 == 0:
                style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F3F5F8")))
    t.setStyle(TableStyle(style))
    return KeepTogether([t]) if len(rows) <= 12 else t


class Report(BaseDocTemplate):
    def __init__(self, path, title, tmpdir):
        super().__init__(path, pagesize=letter, leftMargin=0.95 * inch, rightMargin=0.95 * inch,
                         topMargin=0.85 * inch, bottomMargin=0.8 * inch, title=A(title),
                         author="Capitolis x Berkeley MFE project team")
        self.tmpdir = tmpdir
        self.fig_n = 0
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="f")
        self.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=self._decor)])
        self._short = title

    def _decor(self, canv, doc):
        canv.saveState()
        canv.setFont("Helvetica", 7.5)
        canv.setFillColor(colors.HexColor("#666666"))
        canv.drawString(self.leftMargin, letter[1] - 0.55 * inch, A(self._short))
        canv.drawRightString(letter[0] - self.rightMargin, 0.5 * inch, f"Page {doc.page}")
        canv.setStrokeColor(colors.HexColor("#C9CED6"))
        canv.line(self.leftMargin, letter[1] - 0.6 * inch, letter[0] - self.rightMargin, letter[1] - 0.6 * inch)
        canv.restoreState()

    def afterFlowable(self, fl):
        if isinstance(fl, Paragraph):
            n = fl.style.name
            if n in ("h1", "h2"):
                lvl = 0 if n == "h1" else 1
                text = fl.getPlainText()
                key = f"h{self.seq.nextf('heading')}"
                self.canv.bookmarkPage(key)
                self.notify("TOCEntry", (lvl, text, self.page, key))

    def figure(self, fig, caption, width=W, height_in=None):
        """Save a matplotlib figure, return [Image, caption] kept together."""
        self.fig_n += 1
        path = os.path.join(self.tmpdir, f"fig{self.fig_n:03d}.png")
        fig.savefig(path, dpi=170, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        from PIL import Image as PILImage
        w, h = PILImage.open(path).size
        img = Image(path, width=width, height=width * h / w)
        return KeepTogether([img, Paragraph(A(f"Figure {self.fig_n}. {caption}"), CAP)])


def make_toc():
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle("t1", fontName="Helvetica-Bold", fontSize=9.5, leftIndent=0, spaceBefore=4, leading=12),
        ParagraphStyle("t2", fontName="Helvetica", fontSize=8.5, leftIndent=14, leading=11),
    ]
    return toc
