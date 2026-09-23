"""Report patch, part B: Section 7 (results)."""
import sys
sys.path.insert(0, "scripts")
from _patchlib import Patcher

p = Patcher("scripts/build_report.py")

# ---------------------------------------------------------------- 7.1 reading paragraph, then new 7.2 and 7.3
p.replace('add(P("<b>Reading the results.</b> The close-out MPE99 is far below', '''
_bf = S_["per_trade"]["BF_0003"]
add(P("<b>Reading the results.</b> The close-out MPE99 is far below the level exposure because the prior-day value is margined: CPTY_C's bond forward BF_0003 is worth %s today but its 99th-percentile 10-day move peaks at %s, so its counterparty peaks at $%.1fM against $%.1fM of level exposure. CPTY_A and CPTY_B are driven by the equity swap baskets, whose 10-day equity moves set the tail. Close-out exposure is a measure of market risk over the close-out window, not of the accumulated value, which is why the peak occurs in the first weeks, when the largest baskets are alive, and falls as trades mature. The uncollateralized level exposure is kept as a secondary measure (Sections 7.4 to 7.6), and the earlier full-variation-margin illustration (Section 7.7) used a same-day, zero-floored margin formula that differs slightly from the brief's. Section 7.2 explains why the portfolio figure is close to the sum of the counterparty figures; Sections 7.3, 7.9 and 7.10 show how the numbers move with each model correction, with the model inputs and under stress." % (m(_bf["mtm_t0"]), m(_bf["MPE"]), new_[2], unc_[2])))
add(P("7.2 Why the portfolio MPE is close to the sum of the counterparty MPEs", H2))
add(RN2.additivity_section(doc)[0])
add(P("7.3 What changed since the earlier version", H2))
add(RN.attribution(doc))
''')

# ---------------------------------------------------------------- headings (numbers are stripped by the LaTeX back end; kept for the source's readers)
p.sub('add(P("7.2 Exposure today (t = 0)", H2))', 'add(P("7.4 Exposure today (t = 0)", H2))')
p.sub('add(P("7.3 Uncollateralized exposure profiles through time (secondary view)", H2))', 'add(P("7.5 Uncollateralized exposure profiles through time (secondary view)", H2))')
p.sub('add(P("7.4 Where does the risk come from?", H2))', 'add(P("7.6 Where does the risk come from?", H2))')
p.sub('add(P("7.5 Earlier illustration: full variation margin with an MPOR shift", H2))', 'add(P("7.7 Earlier illustration: full variation margin with an MPOR shift", H2))')
p.sub('add(P("7.6 Full-rank correlation versus PCA factor model", H2))', 'add(P("7.8 Full-rank correlation versus PCA factor model", H2))')

# ---------------------------------------------------------------- 7.9 model risk and 7.10 stress at the end of Section 7
p.insert_after('add(P("This is a like-for-like comparison at one scenario count', '''
add(P("7.9 Model risk: which inputs matter", H2))
add(RN.model_risk(doc))
add(P("7.10 Stress testing", H2))
_stress_out, _ = RN2.stress_section(doc)
add(_stress_out)
''')

p.save()
print("13b done")
