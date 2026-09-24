import sys
sys.path.insert(0, "scripts")
from _patchlib import Patcher
p = Patcher("scripts/build_report.py")
p.sub('''["SA-CVA capital", "$%.2fM (RWA $%.1fM)" % (Rc0["K_sa_cva"] / 1e6, Rc0["RWA"] / 1e6), "Basel standardised approach on the close-out exposure; dominated by counterparty credit spread risk"],''',
      '''["SA-CVA capital", "$%.2fM close-out; $%.2fM uncollateralized (RWA $%.1fM; $%.1fM)" % (Rc0["K_sa_cva"] / 1e6, RN._j("sa_cva_results_level.json")["K_sa_cva"] / 1e6, Rc0["RWA"] / 1e6, RN._j("sa_cva_results_level.json")["RWA"] / 1e6), "Basel standardised approach on the two exposure definitions; dominated by counterparty credit spread risk (Section 8.4)"],''')
p.sub('''the SA-CVA requirement is ${Rc0['K_sa_cva']/1e6:.2f}M (RWA ${Rc0['RWA']/1e6:.1f}M) and the SA-CCR exposure at default {m(Sa['total']['EAD'])}.''',
      '''the SA-CVA requirement is ${Rc0['K_sa_cva']/1e6:.2f}M on the close-out exposure and ${RN._j('sa_cva_results_level.json')['K_sa_cva']/1e6:.2f}M (RWA ${RN._j('sa_cva_results_level.json')['RWA']/1e6:.1f}M) on the uncollateralized exposure, and the SA-CCR exposure at default {m(Sa['total']['EAD'])}.''')
p.save()
print("13f done")
