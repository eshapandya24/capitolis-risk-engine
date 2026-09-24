import sys
sys.path.insert(0, "scripts")
from _patchlib import Patcher
p = Patcher("scripts/build_report.py")
p.insert_after('add(callout("<b>Decision: number of paths.</b>', 'add(RN.convergence_closeout(doc))')
p.insert_after('add(RN.model_risk(doc))', 'add(RN.model_risk_text(doc))')
p.insert_after('add(P("On this version the CVA sensitivities are taken on the brief\'s close-out exposure', 'add(RN.sa_cva_conventions(doc))')
p.save()
print("13e done")
