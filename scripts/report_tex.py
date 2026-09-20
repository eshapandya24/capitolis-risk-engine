"""LaTeX back end for scripts/build_report.py.

Exposes the same small API the report content was written against (P, B,
tbl, code, callout, Report.figure, ...), but every call returns a LaTeX
string instead of a reportlab flowable. Report.multiBuild() writes
docs/latex/report.tex (+ figures as vector PDFs) and compiles it with
pdflatex. All text is pure ASCII (checked by A()).
"""
import os
import re
import shutil
import subprocess

from report_lib import plt, NAVY, TEAL, ORANGE, GOLD, GREY, PAL  # noqa: F401  (matplotlib style + colours)


class Sty:
    def __init__(self, name):
        self.name = name


H1, H2, H3, BODY, SMALL, CAP, TOCH = (Sty(n) for n in ("h1", "h2", "h3", "body", "small", "cap", "toch"))
W = None  # unused: figures are always \linewidth wide


def A(s):
    s = str(s)
    bad = [c for c in s if ord(c) > 127]
    assert not bad, f"non-ASCII in report text: {bad[:5]} in {s[:60]!r}"
    return s


_ESC = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
        "{": r"\{", "}": r"\}", "~": r"$\sim$", "^": r"\textasciicircum{}", "<": r"\textless{}",
        ">": r"\textgreater{}", "|": r"\textbar{}"}
_TAG = re.compile(r"(</?b>|</?i>|<font face='Courier'>|</font>|<br/>)")


def _esc(t):
    t = "".join(_ESC.get(c, c) for c in t)
    t = re.sub(r'"([^"]*)"', r"``\1''", t)
    t = re.sub(r"(?<![\w])'([^']*?)'(?![\w])", r"`\1'", t)
    return t


def inline(s):
    out = []
    for part in _TAG.split(A(s)):
        if part == "<b>":
            out.append(r"\textbf{")
        elif part == "<i>":
            out.append(r"\emph{")
        elif part == "<font face='Courier'>":
            out.append(r"\texttt{")
        elif part in ("</b>", "</i>", "</font>"):
            out.append("}")
        elif part == "<br/>":
            out.append(r"\\ ")
        else:
            out.append(_esc(part))
    return "".join(out)


_num = re.compile(r"^(\d+(\.\d+)*\.?|Appendix [A-Z]\.)\s+")
_state = {"appendix": False}


def P(text, style=BODY):
    if style is TOCH:
        return ""
    if style in (H1, H2, H3):
        t = _num.sub("", text)
        if style is H1:
            pre = ""
            if text.startswith("Appendix") and not _state["appendix"]:
                pre = "\\clearpage\n\\appendix\n"
                _state["appendix"] = True
            return f"{pre}\\section{{{inline(t)}}}\n"
        if style is H2:
            return f"\\subsection{{{inline(t)}}}\n"
        return f"\\subsubsection*{{{inline(t)}}}\n"
    body = inline(text)
    if style is SMALL:
        return "{\\small " + body + "}\n\n"
    return body + "\n\n"


def B(items, style=None):
    return "\\begin{itemize}\n" + "".join(f"\\item {inline(t)}\n" for t in items) + "\\end{itemize}\n"


def code(text):
    longest = max(len(l) for l in text.splitlines())
    assert longest <= 108, f"code line too long ({longest}): {text[:50]!r}"
    return "{\\fontsize{7.2}{8.8}\\selectfont\n\\begin{verbatim}\n" + A(text) + "\n\\end{verbatim}}\n"


def callout(text):
    return ("\\begin{center}\\fcolorbox{teal}{teal!7}{\\parbox{0.94\\linewidth}{\\vspace{2pt}"
            + inline(text) + "\\vspace{2pt}}}\\end{center}\n")


def tbl(rows, widths=None, header=True, font=7.8, zebra=True, align_right_from=None):
    n = len(rows[0])
    if widths is None:
        widths = [1.0] * n
    tot = float(sum(widths))
    spec = "".join(f">{{\\raggedright\\arraybackslash}}p{{\\dimexpr {w / tot:.4f}\\linewidth-2\\tabcolsep\\relax}}" for w in widths)
    size = "\\footnotesize" if font >= 7.6 else "\\scriptsize"
    lines = [f"{{{size}\\setlength{{\\LTpre}}{{4pt}}\\setlength{{\\LTpost}}{{6pt}}",
             f"\\begin{{longtable}}{{{spec}}}", "\\toprule"]
    body = rows
    if header:
        hd = " & ".join("\\textbf{\\textcolor{white}{" + inline(c) + "}}" for c in rows[0])
        lines += ["\\rowcolor{navy}" + hd + " \\\\", "\\endhead"]
        body = rows[1:]
    for i, r in enumerate(body):
        shade = "\\rowcolor{gray!9}" if (zebra and i % 2 == 1) else ""
        lines.append(shade + " & ".join(inline(c) for c in r) + " \\\\")
    lines += ["\\bottomrule", "\\end{longtable}}", ""]
    return "\n".join(lines) + "\n"


def PageBreak():
    return "\\clearpage\n"


def Spacer(*a, **k):
    return ""


def make_toc():
    return "\\tableofcontents\n"


def titlepage(title, subtitle, line1, line2):
    return ("\\begin{titlepage}\n\\vspace*{1.6in}\n"
            "{\\color{navy}\\rule{\\linewidth}{1.2pt}}\\\\[1.2em]\n"
            "{\\Huge\\bfseries\\color{navy} " + inline(title) + "\\par}\n\\vspace{0.6em}\n"
            "{\\Large " + inline(subtitle) + "\\par}\n\\vspace{0.6em}\n"
            "{\\color{navy}\\rule{\\linewidth}{1.2pt}}\\\\[2em]\n"
            "{\\large " + inline(line1) + "\\par}\n\\vspace{0.4em}\n{\\normalsize " + inline(line2) + "\\par}\n"
            "\\end{titlepage}\n")


PREAMBLE = r"""\documentclass[11pt,letterpaper]{article}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{lmodern}
\usepackage[margin=1in]{geometry}
\usepackage{graphicx}
\usepackage[table,dvipsnames]{xcolor}
\usepackage{colortbl}
\usepackage{array}
\usepackage{longtable}
\usepackage{booktabs}
\usepackage{float}
\usepackage{caption}
\usepackage{enumitem}
\usepackage{amsmath}
\usepackage{fancyhdr}
\usepackage{titlesec}
\usepackage{microtype}
\usepackage[hidelinks]{hyperref}
\definecolor{navy}{HTML}{1F3A5F}
\definecolor{teal}{HTML}{2A9D8F}
\setlist[itemize]{leftmargin=1.4em,itemsep=2pt,topsep=3pt}
\titleformat{\section}{\Large\bfseries\color{navy}}{\thesection}{0.6em}{}
\titleformat{\subsection}{\large\bfseries\color{navy}}{\thesubsection}{0.6em}{}
\titlespacing*{\section}{0pt}{16pt}{8pt}
\titlespacing*{\subsection}{0pt}{12pt}{5pt}
\captionsetup{font=small,labelfont=bf,justification=raggedright,singlelinecheck=false}
\setlength{\parindent}{0pt}
\setlength{\parskip}{5pt}
\setlength{\emergencystretch}{2em}
\sloppy
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{\small\textcolor{gray}{__SHORT__}}
\fancyfoot[C]{\small\thepage}
\renewcommand{\headrulewidth}{0.3pt}
\begin{document}
"""


class Report:
    def __init__(self, path, title, tmpdir):
        self.pdf_path = path
        self.title = title
        root = os.path.join(os.path.dirname(os.path.dirname(path)), "docs", "latex")
        self.texdir = os.path.join(os.path.dirname(path), "latex")
        self.figdir = os.path.join(self.texdir, "figures")
        if os.path.isdir(self.figdir):
            shutil.rmtree(self.figdir, ignore_errors=True)
        os.makedirs(self.figdir, exist_ok=True)
        self.fig_n = 0

    def figure(self, fig, caption, width=None, height_in=None):
        self.fig_n += 1
        name = f"fig{self.fig_n:02d}.pdf"
        fig.savefig(os.path.join(self.figdir, name), bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return ("\\begin{figure}[H]\n\\centering\n"
                f"\\includegraphics[width=\\linewidth]{{figures/{name}}}\n"
                f"\\caption{{{inline(caption)}}}\n\\end{{figure}}\n")

    def multiBuild(self, S):
        body = "".join(S if isinstance(S, list) else [S])
        tex = PREAMBLE.replace("__SHORT__", inline(self.title)) + body + "\n\\end{document}\n"
        texpath = os.path.join(self.texdir, "report.tex")
        with open(texpath, "w", encoding="ascii", newline="\n") as f:
            f.write(tex)
        for _ in range(2):
            r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "report.tex"],
                               cwd=self.texdir, capture_output=True, text=True)
            if r.returncode != 0:
                print(r.stdout[-3000:])
                raise RuntimeError("pdflatex failed; see docs/latex/report.log")
        shutil.copyfile(os.path.join(self.texdir, "report.pdf"), self.pdf_path)
        for ext in ("aux", "toc", "out"):
            p = os.path.join(self.texdir, f"report.{ext}")
            if os.path.exists(p):
                os.remove(p)
