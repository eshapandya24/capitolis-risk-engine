import re
p = "scripts/build_report.py"
s = open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert a in s, "MISSING: " + a[:100]
    s = s.replace(a, b, 1)


rep("moves MPE by more than 10%%)", "moves MPE by about 9%%)")

s = re.sub(r'    add\(P\("An independent standard method.*?\)\)\n',
           '''    add(P("An independent standard method: portfolio dollar-deltas by bump-and-reprice with the same volatilities and correlations as the simulation, combined into a delta-normal VaR at the first simulated node (one day, the overnight pillar). The 99% delta-normal VaR is $11.4M against $11.7M from the Monte Carlo P&L distribution (ratio 0.98; accepted range 0.3-1.3). At this short horizon the book is close to linear in the risk factors, so close agreement is expected; a large discrepancy would have indicated a sign or scaling error in the deltas or the covariance."))
''', s, count=1, flags=re.S)
s = re.sub(r'    add\(P\("Directional test with common random numbers.*?\)\)\n',
           '''    add(P("Directional test with common random numbers (800 scenarios, same seed in base and bumped runs). Base MPE (PFE99) is $174.0M. Raising equity volatility by 50% increases it to $189.8M (+9.1%); a +100bp parallel shift of the USD curve to $230.5M (+32.5%), consistent with the USD rate being the largest single delta; and raising Hull-White sigma by 50% to $183.4M (+5.4%). All three moved exposure in the economically required direction. The magnitudes also show the scale of model risk: an equity volatility error of 50% matters about ten times more than the sampling error at the recommended path count."))
''', s, count=1, flags=re.S)

simm = '''    add(P("<b>Relation to SIMM and Basel.</b> The 10-day figure is the convention shared by both frameworks. Under the Basel counterparty credit risk rules (SA-CCR and the internal models method) the margin period of risk for a margined bilateral OTC netting set is at least 10 business days, 5 business days for centrally cleared trades and 20 business days for large or illiquid netting sets, and it lengthens after margin disputes. The ISDA Standard Initial Margin Model (SIMM) is a different object: a sensitivity-based methodology for the <i>initial margin</i> that the uncleared margin rules require counterparties to post, calibrated to a 99% one-tailed loss over a 10-day horizon using a stress period. Initial margin is collateral posted in addition to variation margin and held against precisely the close-out window described above."))
    add(P("Our engine does <b>not</b> implement SIMM and does not model initial margin. The calculation in this section is a variation-margin-only illustration: a threshold of zero removes any unsecured amount, but there is no initial margin buffer. If initial margin were posted it would absorb part of the 10-day move and reduce the exposure shown further; quantifying that requires computing SIMM sensitivities for each netting set, which we have not attempted. Two simplifications should also be noted: the look-ahead uses 10 <i>calendar</i> days (10 business days would be about 14), and no minimum transfer amount is modelled."))
'''
rep('''    add(P("Whether any trade is actually margined is the most important open question for Capitolis:''', simm + '''    add(P("Whether any trade is actually margined is the most important open question for Capitolis:''')

rep('["Pillar dates",', '["SIMM", "ISDA Standard Initial Margin Model: sensitivity-based initial margin for uncleared derivatives, calibrated to a 99% 10-day loss (not implemented here)"],\n             ["Pillar dates",')
rep('"<b>No wrong-way risk', '"<b>Margin modelling is partial:</b> the collateral illustration is variation-margin only, uses 10 calendar days, and has no initial margin (SIMM) or minimum transfer amount.",\n           "<b>No wrong-way risk')
open(p, "w", encoding="utf-8").write(s)
print("ok4")
