p = "scripts/build_report.py"
s = open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert a in s, "MISSING: " + a[:80]
    s = s.replace(a, b, 1)


rep('["JPY OIS curve, swaption cube, USDJPY forwards", "Bloomberg one-time export, 2026-08-31 snapshot", "JPY factor, JPY-USD differential", "Licensed data: only derived quantities are reported"],',
    '["JPY OIS par-rate history, 35 tenors, 2011-2026", "Bloomberg export provided by the project team (data/raw/sources/JPY.xlsx)", "JPY curve, JPY factor volatility, JPY-USD differential, mean-reversion test", "Licensed data: only derived quantities are reported"],\n             ["USD and JPY swaption cubes, USDJPY forwards", "Bloomberg one-time export, 2026-08-31 snapshot", "USD mean reversion, cross-checks, FX forwards", "Licensed data: only derived quantities are reported"],')
rep('["USD swaption vol cube; JPY OIS curve and swaption vols; USDJPY forward points", "Bloomberg one-time export, snapshot 2026-08-31", "Provided by the project team", "USD mean reversion; JPY factor; JPY-USD rate differential; FX forwards", "Licensed: derived numbers only in the report"],',
    '["JPY OIS par-rate history (MUTKCALM overnight plus 35 OIS tenors, 5 Oct 2011 to 18 Sep 2026)", "Bloomberg (tickers JYSO*, MUTKCALM Index)", "Provided by the project team, saved as data/raw/sources/JPY.xlsx (parsed copy jpy_ois_history.csv)", "JPY zero curve (bootstrapped), JPY volatility, JPY-USD differential, mean-reversion test", "Licensed: derived numbers only in the report"],\n             ["USD and JPY swaption cubes; USDJPY forward points", "Bloomberg one-time export, snapshot 2026-08-31", "Provided by the project team", "USD mean reversion; JPY cross-check; FX forwards", "Licensed: derived numbers only in the report"],')
rep("and the JPY mean-reversion fallback to the USD value.", "and the JPY mean reversion being set at its lower bound (a = 0.001) because every calibration route gives a negative value.")
rep('"USD 0.0167; futures 0.0458; JPY invalid, fallback to USD"', '"USD 0.0167; futures 0.0458; JPY: all routes negative, lower bound 0.001 used"')
rep('["JPY factor", "Second Hull-White factor on the real JPY OIS curve; realised TONA volatility", "sigma 0.276%; USD-JPY rate correlation -0.04 (not significant)", "models/calibration.py"],',
    '["JPY factor", "Second Hull-White factor; curve bootstrapped from the JPY OIS par history; overnight volatility from the same file", "sigma 0.267%; a = 0.001; USD-JPY rate correlation -0.04 (not significant)", "models/calibration.py, market/jpy_ois.py"],')
rep("drift r-q\", \"3y realised vols; JPY names via r_USD minus differential (2.64%)\"", "drift r-q\", \"3y realised vols; JPY names via r_USD minus differential (about 2.6%)\"")
rep('"Diagnosed as a real structural property (two sources); guarded with documented fallback"', '"Diagnosed as a real structural property (three sources); lower bound a = 0.001 used"')
rep('"<b>JPY:</b> mean reversion is a fallback and the JPY rate does not yet drive JPY equity/FX drift (two trades).",', '"<b>JPY:</b> mean reversion is at its lower bound (the data give a negative value) and the JPY rate does not yet drive JPY equity/FX drift (two trades).",')

# negative-rate evidence from the OIS history (derived numbers only)
rep('    fg, frac = fig_ou_negative()\n',
    '    from risk_engine.market import jpy_ois\n    _h = jpy_ois.load_jpy_ois_history()\n    _cols = [c for c in _h.columns if c.startswith("JYSO") and jpy_ois.tenor_years(c) <= 5.0]\n    add(P("The daily JPY OIS history provided by the project team (35 tenors, %d business days from October 2011) shows the same for the whole short end of the curve: the overnight call rate was negative on %d days, and OIS par rates out to five years were negative on %d of those days, with a minimum of %.2f%%." % (len(_h), int((_h["MUTKCALM"] < 0).sum()), int((_h[_cols] < 0).any(axis=1).sum()), _h.min().min())))\n    fg, frac = fig_ou_negative()\n')
open(p, "w", encoding="utf-8").write(s)

d = open("scripts/build_exec_deck.py", encoding="utf-8").read()
d = d.replace('"TONA vol; mean reversion falls back to USD"', '"Curve and vol from the daily JPY OIS history; mean reversion at lower bound 0.001"')
d = d.replace("(sigma from real Bank of Japan TONA; USD-JPY rate correlation calibrated near zero) but does not yet drive JPY equity drift; its mean reversion falls back to USD's because real JPY vol rises with tenor.",
              "(curve and volatility from the daily JPY OIS history; USD-JPY rate correlation calibrated near zero) but does not yet drive JPY equity drift; mean reversion is at its lower bound because JPY vol rises with tenor in three independent datasets.")
d = d.replace('["TONA; JGB yields", "Bank of Japan API; Japan MoF", "JPY rate vol, correlation, mean-reversion test"],', '["JPY OIS history (35 tenors, 2011-2026)", "Bloomberg file from the project team (data/raw/sources)", "JPY curve, vol, differential, mean-reversion test"],\n            ["TONA; JGB yields", "Bank of Japan API; Japan MoF", "JPY rate correlation; cross-checks"],')
d = d.replace('["Swaption cube, JPY OIS, FX forwards", "Bloomberg export (licensed)", "USD mean reversion, JPY factor, FX carry"],', '["Swaption cubes, FX forwards", "Bloomberg snapshot (licensed)", "USD mean reversion, FX forwards"],')
open("scripts/build_exec_deck.py", "w", encoding="utf-8").write(d)
print("ok9")
