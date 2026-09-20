p = "scripts/build_report.py"
s = open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert a in s, a[:70]
    s = s.replace(a, b, 1)


# --- CVA 8.2: exact sources
rep('    add(doc.figure(fig_credit_curves(), "Proxy spread curves',
    '    add(P("<b>Sources.</b> Rating spreads: FRED series BAMLC0A1CAAA (AAA), BAMLC0A2CAA (AA), BAMLC0A3CA (A), BAMLC0A4CBBB (BBB), BAMLH0A1HYBB (BB) and BAMLH0A2HYB (B), ICE BofA US option-adjusted spreads. Maturity shape: BAMLC1A0C13Y, BAMLC2A0C35Y, BAMLC3A0C57Y and BAMLC4A0C710Y relative to BAMLC0A0CM (all US corporate). Basel parameters: Bank for International Settlements, Targeted revisions to the credit valuation adjustment risk framework (July 2020), MAR50. Equity bucket attributes (sector, country, market capitalisation): yfinance."))\n'
    '    add(doc.figure(fig_credit_curves(), "Proxy spread curves')

apps = '''    add(P("Appendix C. Data sources and lineage", H1))
    add(P("Every external input, where it came from, how it was obtained and what it is used for. Raw pulls are stored under data/raw/ (excluded from version control); licensed data is never redistributed."))
    add(tbl([["Input", "Source", "How obtained", "Used for", "Status"],
             ["Trades (16) and underlyings", "Capitolis: trade_data/*.csv", "Supplied files", "Trade definitions, baskets, bonds", "Given"],
             ["Pricing library", "Capitolis: capitolis_pricers", "Supplied package (standard library only)", "All trade valuation (npv), curves, day counts", "Given; independently reviewed"],
             ["USD SOFR futures (SR3, SR1)", "CME Globex via Databento (dataset GLBX.MDP3)", "Paid API; key only in an environment variable", "USD discount curve (bootstrapped by us), Hull-White fit, futures-vol mean-reversion cross-check", "Live, validated against Treasury.gov"],
             ["Treasury par yield curve", "U.S. Treasury (treasury.gov)", "Public download", "Independent check of the SOFR curve", "Validation only"],
             ["Equity spots, dividends, 3y price history (37 names)", "yfinance (Yahoo Finance)", "Public API, keyed by ISIN", "GBM start values and drift, realised volatility, correlation", "Live"],
             ["USDJPY spot and 3y history", "yfinance", "Public API", "FX start value, volatility, correlation", "Live"],
             ["SOFR level history", "FRED (series SOFR)", "Public CSV", "Rate volatility; USD-JPY rate correlation", "From April 2018"],
             ["TONA (JPY overnight rate), 1998 to date", "Bank of Japan Time-Series Data Search API (DB FM01, series STRDCLUCON)", "Public API", "JPY rate volatility; USD-JPY correlation; negative-rate evidence", "Public"],
             ["JGB par yields 1Y-40Y, 1974 to date", "Japan Ministry of Finance", "Public CSV (browser-like request headers)", "Test of JPY mean reversion", "Public"],
             ["USD swaption vol cube; JPY OIS curve and swaption vols; USDJPY forward points", "Bloomberg one-time export, snapshot 2026-08-31", "Provided by the project team", "USD mean reversion; JPY factor; JPY-USD rate differential; FX forwards", "Licensed: derived numbers only in the report"],
             ["Credit spreads by rating and maturity shape", "FRED: ICE BofA US option-adjusted spread indices", "Public CSV", "Counterparty credit spread proxy for CVA", "Public"],
             ["SA-CVA parameters and formulas", "BIS, Basel Framework MAR50 (July 2020 revisions)", "Public PDF", "Risk weights, correlations, aggregation", "Public"],
             ["Equity sector, country, market cap", "yfinance", "Public API", "SA-CVA equity buckets", "Live"]],
            widths=[1.7, 2.0, 1.6, 2.2, 1.2], font=7.0))
    add(P("Assumptions that are not sourced from data: counterparty ratings (BBB), LGD (60%), MPOR (10 business days), the uncollateralized status of the book, the correlation structure being static, and the JPY mean-reversion fallback to the USD value."))
    add(P("Appendix D. Methodology register", H1))
    add(tbl([["Component", "Method", "Key parameters", "Where (code)"],
             ["USD curve", "Bootstrap of SOFR futures: implied forward rate to chained discount factors, ACT/360", "33 live contracts, about 6.3y coverage, flat extrapolation beyond", "market/sofr.py"],
             ["USD rates", "One-factor Hull-White, shifted Ornstein-Uhlenbeck, exact transition, analytic bond price", "sigma 0.63% (realised SOFR); a 0.0167 (swaption cube)", "models/rates.py"],
             ["Mean reversion", "Regression of ln(vol) on tenor (vol decay); swaption cube preferred, futures and JGB as checks", "USD 0.0167; futures 0.0458; JPY invalid, fallback to USD", "models/hw_calibration.py"],
             ["JPY factor", "Second Hull-White factor on the real JPY OIS curve; realised TONA volatility", "sigma 0.276%; USD-JPY rate correlation -0.04 (not significant)", "models/calibration.py"],
             ["Equities and FX", "Correlated geometric Brownian motion, exact log step, drift r-q", "3y realised vols; JPY names via r_USD minus differential (2.64%)", "models/equity_fx.py"],
             ["Correlation", "Static 39x39 matrix (613 aligned days), Cholesky; optional PCA factor model", "5 factors explain about 46% of variance", "models/equity_factor_model.py, simulation/engine.py"],
             ["Random numbers", "Latin Hypercube sampling", "N = 5,000 recommended; 3,000 used for the figures", "simulation/random_numbers.py"],
             ["Dates", "Market pillar dates plus every trade event date", "42 nodes for this book", "simulation/engine.py"],
             ["Repricing", "Full repricing of every trade in every scenario and node, 8 worker processes", "About 90 ms per scenario", "simulation/parallel.py"],
             ["Exposure measures", "Netting by counterparty, max(V,0); EE, median PFE, PFE99, MPE", "PFE at the 99th percentile", "exposure/aggregate.py"],
             ["Collateral (hypothetical)", "MPOR look-ahead on the same paths, full variation margin", "10 business days, US federal holidays", "exposure/collateral.py"],
             ["CVA", "Regulatory CVA, MAR50.32; pathwise discounting; credit-triangle PD from spreads", "LGD 60%; BBB proxy; unilateral; independent", "exposure/cva.py, models/credit.py"],
             ["SA-CVA", "CVA bump sensitivities with common random numbers, MAR50 aggregation", "1,000 scenarios; 21 simulations; m_CVA = 1", "exposure/sa_cva.py, scripts/run_sa_cva.py"],
             ["Precision", "Bootstrap resampling of a large pool; 1/sqrt(N) extrapolation", "Relative SE of PFE99 about 1.0% at N = 5,000 at the worst date", "scripts/convergence_study_tail.py"],
             ["Validation", "t=0 self-check, martingale test, delta-normal VaR, stress test, unit tests", "69 automated tests", "scripts/, tests/"]],
            widths=[1.2, 2.8, 2.4, 1.9], font=7.0))
    add(P("Appendix E. Code map", H1))
    add(tbl([["Package", "Contents"],
             ["market/", "sofr, equities, fx, vols, correlations (data pulls and inputs); boj, mof_jgb, bloomberg (JPY data); credit_spreads, equity_buckets (CVA inputs)"],
             ["models/", "rates (Hull-White), equity_fx (GBM), calibration and hw_calibration (parameters), equity_factor_model (PCA), credit (PD from spreads)"],
             ["simulation/", "engine (grid, paths, MPOR nodes), random_numbers (five sampling schemes), parallel (multiprocessing repricing)"],
             ["exposure/", "aggregate (netting, EE, median PFE, PFE, MPE), collateral (MPOR-shifted), cva (regulatory CVA), sa_cva (Basel aggregation)"],
             ["scripts/", "run_simulation, run_mpor_comparison, run_sa_cva, generate_report_data, build_report (LaTeX), build_exec_deck, and the convergence, variance-reduction, VaR, martingale and stress benchmarks"],
             ["tests/", "69 tests: engine, time grid, MPOR, negative rates, factor model, BOJ and MOF data, tail convergence, median PFE, CVA and SA-CVA"]],
            widths=[1.2, 6.6]))
'''
rep('    add(P("Appendix B. Reproducing the results", H1))', apps + '    add(P("Appendix B. Reproducing the results", H1))')
open(p, "w", encoding="utf-8").write(s)

d = open("scripts/build_exec_deck.py", encoding="utf-8").read()
marker = '    S += [P("Assumptions, limits, next steps", TITLE)]'
new = '''    rows = [["Input", "Source", "Used for"],
            ["Trades, pricing library", "Capitolis (supplied)", "16 trades; all valuation"],
            ["USD SOFR futures", "CME via Databento", "USD curve (our bootstrap)"],
            ["Equities, USDJPY, sectors", "yfinance", "Spots, vols, correlation, SA-CVA buckets"],
            ["SOFR history; credit spreads by rating", "FRED (SOFR, ICE BofA OAS)", "Rate vol; CVA credit proxy"],
            ["TONA; JGB yields", "Bank of Japan API; Japan MoF", "JPY rate vol, correlation, mean-reversion test"],
            ["Swaption cube, JPY OIS, FX forwards", "Bloomberg export (licensed)", "USD mean reversion, JPY factor, FX carry"],
            ["SA-CVA rules", "BIS Basel MAR50 (2020)", "Risk weights, correlations, aggregation"]]
    S += [P("Data sources", TITLE), table(rows, [3.0 * inch, 3.2 * inch, 3.6 * inch]), PageBreak()]
    rows = [["Component", "Method", "Key choice"],
            ["USD rates", "Hull-White one-factor", "a = 0.0167 (swaptions), sigma = 0.63% (SOFR)"],
            ["Equities, FX", "Correlated GBM", "3y realised vols, static 39x39 correlation, Cholesky"],
            ["JPY", "Second Hull-White factor, negative-rate capable", "TONA vol; mean reversion falls back to USD"],
            ["Sampling", "Latin Hypercube", "5,000 paths reporting; 3,000 here"],
            ["Dates", "Market pillars + trade events", "42 nodes"],
            ["Exposure", "Net, max(V,0); EE, median PFE, PFE99, MPE", "Uncollateralized; MPOR 10 business days as hypothetical"],
            ["CVA", "Regulatory CVA (MAR50.32)", "BBB bond-spread proxy, LGD 60%, unilateral"],
            ["SA-CVA", "Bump sensitivities, MAR50 aggregation", "Common random numbers, 21 runs, m_CVA = 1"]]
    S += [P("Methodology at a glance", TITLE), table(rows, [1.6 * inch, 4.0 * inch, 4.2 * inch]), PageBreak()]
'''
d = d.replace(marker, new + marker)
open("scripts/build_exec_deck.py", "w", encoding="utf-8").write(d)
print("ok7")
