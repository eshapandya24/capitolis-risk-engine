p = "scripts/_patch_report13d.py"
s = open(p, encoding="utf-8").read()
s = s.replace("i.e. it was too wide on average because it inherited the volatility of the 2022-23 hiking cycle, and would be too narrow",
              "i.e. it was too wide on average, reflecting a calibration window that included the 2022-23 hiking cycle, and would be too narrow")
a = 'python scripts/run_xva.py; run_sa_ccr.py; run_backtest.py # CVA/DVA/FVA, SA-CCR, Kupiec backtest'
assert a in s
s = s.replace(a, 'python scripts/run_xva.py && python scripts/run_sa_ccr.py   # CVA/DVA/FVA and SA-CCR')
b = 'python scripts/run_stress.py --scenarios 1000             # stress test'
assert b in s
s = s.replace(b, 'python scripts/run_backtest.py                            # Kupiec backtest\\\\n"\\n             "python scripts/run_stress.py --scenarios 1000             # stress test')
tail = 'p.save()\nprint("13d done")'
assert tail in s
s = s.replace(tail, """p.insert_after('add(B(["<b>Counterparty ratings are assumed</b> (BBB financials).', '''
add(P("8.9 Extra credit: a risky-bond sample trade", H2))
add(RN2.risky_bond_section(doc))
''')
p.save()
print("13d done")""")
open(p, "w", encoding="utf-8").write(s)
print("fixed")
