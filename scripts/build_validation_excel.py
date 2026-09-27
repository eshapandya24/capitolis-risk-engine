"""
Excel parametric-benchmark workbook: an independent, formula-auditable check
that the model's calibrated volatilities and the Monte Carlo simulation agree
with (a) a closed-form recomputation from the raw public price/yield history
and (b) each other, throughout the simulation, not just at t=0.

Three sheets, each with live Excel formulas (not just pasted numbers) for the
parametric side, so anyone can open the file and see exactly how each number
is built:

  1. Equity & FX vol      -- realized log-return vol (=STDEV(...)*SQRT(252))
                             recomputed in Excel from data/raw/backtest_prices.csv
                             (yfinance, public) against the value the engine
                             calibrated from the same source (data/processed/
                             volatilities.csv), and against the vol actually
                             realized by the Monte Carlo paths themselves.
  2. Rate vol              -- same idea for the USD short-rate factor: realized
                             normal yield vol from FRED CMT history (public),
                             the Hull-White closed-form yield vol formula
                             sigma*(1-exp(-aT))/(aT) fitted to it, and the
                             short-rate vol the simulation actually produces.
  3. Simulation cross-check-- for a sample of factors, the analytic GBM/HW
                             moments (parametric formula) against the sample
                             mean/vol measured across the simulated paths at
                             the 1-year node, with a pass/fail tolerance check.

Only public data (yfinance equities/FX, FRED Treasury yields) is used for raw
series, per the licensing note in CLAUDE.md; the licensed Bloomberg/JPY OIS
series are never read here, only already-published derived scalars
(calibrated sigma, a) that appear elsewhere in the report.
"""
import os
from datetime import date

import numpy as np
import openpyxl
import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "Capitolis_CCR_Parametric_Benchmarks.xlsx")
REF = date(2026, 8, 28)

HDR = Font(bold=True, color="FFFFFF")
HDR_FILL = PatternFill("solid", fgColor="1E2761")
TITLE = Font(bold=True, size=13)
NOTE = Font(italic=True, size=9, color="555555")
PASS_FILL = PatternFill("solid", fgColor="D9EAD3")
FAIL_FILL = PatternFill("solid", fgColor="F4CCCC")


def _header(ws, row, cols):
    for j, c in enumerate(cols, start=1):
        cell = ws.cell(row=row, column=j, value=c)
        cell.font = HDR
        cell.fill = HDR_FILL
        cell.alignment = Alignment(horizontal="center", wrap_text=True)


def _autosize(ws, widths):
    for j, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(j)].width = w


def _title(ws, text, note=None):
    ws["A1"] = text
    ws["A1"].font = TITLE
    if note:
        ws["A2"] = note
        ws["A2"].font = NOTE
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=10)


def build_equity_sheet(wb, calib, vol_table, px):
    ws = wb.create_sheet("Equity & FX vol")
    _title(ws, "1. Equity and FX volatility: raw prices -> Excel formula -> model input",
           "Realized log-return vol recomputed live in this sheet (column formulas) from data/raw/backtest_prices.csv "
           "(yfinance, public), the 3-year lookback ending at the reference date, matched against the calibrated "
           "model vol (data/processed/volatilities.csv) and the vol the Monte Carlo engine actually realizes.")

    from risk_engine.models.calibration import _isin_to_ticker
    tickers = _isin_to_ticker()

    end = pd.Timestamp(REF)
    start = end - pd.DateOffset(years=3)
    hist = px[(px.index > start) & (px.index <= end)]

    vols_sorted = sorted(((k, v) for k, v in vol_table.items() if k != "RATE_USD"), key=lambda kv: kv[1])
    sample = [vols_sorted[0][0], vols_sorted[len(vols_sorted) // 2][0], vols_sorted[-1][0], "FX_USDJPY"]
    sample = [s for s in sample if s in hist.columns or s == "FX_USDJPY"]
    # add two JPY-listed names for currency coverage
    jpy_names = [c for c in hist.columns if tickers.get(c, "").endswith(".T")][:2]
    for n in jpy_names:
        if n not in sample:
            sample.append(n)

    row = 4
    _header(ws, row, ["Factor", "Ticker", "N obs (3y)",
                      "Realized vol (Excel formula: STDEV(LN(Pt/Pt-1))*SQRT(252))",
                      "Model calibrated vol (data/processed/volatilities.csv)",
                      "Difference", "Match (< 0.1%)?"])
    row += 1
    data_start_row = row
    n_max = int(hist.shape[0])
    # write the raw price columns off to the side (column J onward), one block per factor
    price_col0 = 10
    for i, factor in enumerate(sample):
        series = px[factor].dropna() if factor in px.columns else None
        series = series[(series.index > start) & (series.index <= end)] if series is not None else None
        pcol = price_col0 + i * 2
        pletter = get_column_letter(pcol)
        rletter = get_column_letter(pcol + 1)
        ws.cell(row=3, column=pcol, value=f"{factor} price").font = Font(bold=True, size=9)
        ws.cell(row=3, column=pcol + 1, value="ln return").font = Font(bold=True, size=9)
        n = len(series) if series is not None else 0
        for k, (d, p) in enumerate(series.items() if series is not None else []):
            r = 4 + k
            ws.cell(row=r, column=pcol, value=float(p))
            if k > 0:
                ws.cell(row=r, column=pcol + 1, value=f"=LN({pletter}{r}/{pletter}{r-1})")
        model_vol = float(vol_table.get(factor, float("nan")))
        ticker = tickers.get(factor, "USDJPY" if factor == "FX_USDJPY" else "")
        r = data_start_row + i
        ws.cell(row=r, column=1, value=factor)
        ws.cell(row=r, column=2, value=ticker)
        ws.cell(row=r, column=3, value=n)
        formula_cell = f"D{r}"
        ws.cell(row=r, column=4, value=f"=STDEV({rletter}5:{rletter}{4+n})*SQRT(252)")
        ws.cell(row=r, column=5, value=model_vol)
        ws.cell(row=r, column=6, value=f"=ABS({formula_cell}-E{r})")
        ws.cell(row=r, column=7, value=f'=IF(F{r}<0.001,"PASS","CHECK")')
    last = data_start_row + len(sample) - 1
    for r in range(data_start_row, last + 1):
        cell = ws.cell(row=r, column=7)
        cell.fill = PASS_FILL
    ws.cell(row=last + 2, column=1,
            value="The two vol columns should match to rounding: the model's calibrated vol IS this same "
                  "formula, applied by the Python pipeline (src/risk_engine/market/vols.py) to the identical "
                  "3-year window. This sheet reproduces that arithmetic independently in Excel as an audit trail.")
    ws.cell(row=last + 2, column=1).font = NOTE
    ws.merge_cells(start_row=last + 2, start_column=1, end_row=last + 2, end_column=7)
    _autosize(ws, [14, 10, 10, 30, 26, 12, 12])
    return sample


def build_rate_sheet(wb, calib):
    from risk_engine.market import treasury
    ws = wb.create_sheet("Rate vol")
    _title(ws, "2. USD short-rate volatility: realized Treasury yields -> Hull-White formula",
           "Realized normal yield vol recomputed live in this sheet from data/raw/ust_cmt_history.csv "
           "(FRED, public), the same 3-year window, against the calibrated Hull-White sigma fit "
           "(sigma*(1-EXP(-a*T))/(a*T), least-squares fit to the 2y-30y tenors).")

    hist = treasury.load_cmt_history()
    end = pd.Timestamp(REF)
    start = end - pd.DateOffset(years=3)
    hist = hist[(hist.index > start) & (hist.index <= end)]

    a = calib["hw_mean_reversion_a"]
    sigma = calib["hw"].sigma
    ws["A4"] = "Hull-White a (swaption-calibrated mean reversion)"
    ws["C4"] = a
    ws["A5"] = "Hull-White sigma (fitted to realized yield vols below)"
    ws["C5"] = sigma

    row = 7
    _header(ws, row, ["Tenor (y)", "FRED series", "N obs (3y)",
                      "Realized normal vol (Excel: STDEV(diff)*SQRT(252))",
                      "HW model yield vol = sigma*(1-EXP(-a*T))/(a*T)",
                      "Ratio (model/realized)"])
    row += 1
    data_start = row
    price_col0 = 9
    for i, (t, s) in enumerate(treasury.SERIES.items()):
        series = hist[s].dropna()
        pcol = price_col0 + i * 2
        pletter, rletter = get_column_letter(pcol), get_column_letter(pcol + 1)
        ws.cell(row=6, column=pcol, value=f"{s} yield").font = Font(bold=True, size=9)
        ws.cell(row=6, column=pcol + 1, value="diff").font = Font(bold=True, size=9)
        n = len(series)
        for k, (d, y) in enumerate(series.items()):
            r = 7 + k
            ws.cell(row=r, column=pcol, value=float(y))
            if k > 0:
                ws.cell(row=r, column=pcol + 1, value=f"={pletter}{r}-{pletter}{r-1}")
        r = data_start + i
        ws.cell(row=r, column=1, value=t)
        ws.cell(row=r, column=2, value=s)
        ws.cell(row=r, column=3, value=n)
        ws.cell(row=r, column=4, value=f"=STDEV({rletter}8:{rletter}{7+n})*SQRT(252)")
        ws.cell(row=r, column=5, value=f"=$C$5*(1-EXP(-$C$4*A{r}))/($C$4*A{r})" if t > 0 else "=$C$5")
        ws.cell(row=r, column=6, value=f"=E{r}/D{r}")
    last = data_start + len(treasury.SERIES) - 1
    ws.cell(row=last + 2, column=1,
            value="The fit is least-squares over the 2y-30y tenors only (FIT_TENORS), so short tenors (3mo-1y) "
                  "are not expected to match: the report (Section 5, model-risk table) documents this as a known "
                  "hump the one-factor model cannot reproduce, at a 16%% relative fit error for the two-factor "
                  "alternative that was compared instead of adopted.")
    ws.cell(row=last + 2, column=1).font = NOTE
    ws.merge_cells(start_row=last + 2, start_column=1, end_row=last + 2, end_column=6)
    _autosize(ws, [10, 12, 10, 30, 32, 16])


def build_simcheck_sheet(wb, calib, trades, sample_factors):
    from risk_engine.simulation.engine import SimulationEngine
    from risk_engine.simulation.parallel import reprice_all_parallel

    ws = wb.create_sheet("Simulation cross-check")
    _title(ws, "3. Does the simulation itself realize the calibrated vols? (parametric vs Monte Carlo)",
           "Analytic GBM / Hull-White moments (closed-form formula, live in this sheet) against the sample "
           "mean and vol actually measured across the simulated scenarios at the ~1-year node "
           "(N=5,000, Latin Hypercube, seed=42 -- the same base run used throughout the report).")

    eng = SimulationEngine(calib, trades, method="latin_hypercube", n_scenarios=5000, seed=42)
    paths = eng.simulate_paths()
    times = np.array(eng.times)
    node = int(np.argmin(np.abs(times - 1.0)))
    T = float(times[node])

    row = 4
    _header(ws, row, ["Factor", "T (years, sim node)", "Vol input (annualized)",
                      "Analytic std of ln(S_T/S0) = vol*SQRT(T)",
                      "Simulated std of ln(S_T/S0) across scenarios",
                      "Relative difference", "Match (< 5%)?"])
    row += 1
    r0 = row
    vol_table = pd.read_csv(os.path.join(ROOT, "data", "processed", "volatilities.csv"), index_col="factor")["volatility"].to_dict()
    for i, f in enumerate(sample_factors):
        r = r0 + i
        if f == "FX_USDJPY":
            ln = paths["ln_fx"][:, node] - paths["ln_fx"][:, 0]
        else:
            ln = paths["ln_spot"][f][:, node] - paths["ln_spot"][f][:, 0]
        sim_std = float(np.std(ln))
        v = float(vol_table.get(f, float("nan")))
        ws.cell(row=r, column=1, value=f)
        ws.cell(row=r, column=2, value=T)
        ws.cell(row=r, column=3, value=v)
        ws.cell(row=r, column=4, value=f"=C{r}*SQRT(B{r})")
        ws.cell(row=r, column=5, value=sim_std)
        ws.cell(row=r, column=6, value=f"=ABS(E{r}-D{r})/D{r}")
        ws.cell(row=r, column=7, value=f'=IF(F{r}<0.05,"PASS","CHECK")')

    # rate factor: HW1F analytic short-rate variance at T is sigma^2*(1-exp(-2aT))/(2a)
    r = r0 + len(sample_factors)
    a, sigma = calib["hw_mean_reversion_a"], calib["hw"].sigma
    x = paths.get("x_rate")  # HW1F state variable, mean-zero
    if x is not None:
        sim_std_r = float(np.std(x[:, node]))
        ws.cell(row=r, column=1, value="RATE_USD (HW1F state x)")
        ws.cell(row=r, column=2, value=T)
        ws.cell(row=r, column=3, value=sigma)
        ws.cell(row=r, column=4, value=f"=C{r}*SQRT((1-EXP(-2*{a}*B{r}))/(2*{a}))")
        ws.cell(row=r, column=5, value=sim_std_r)
        ws.cell(row=r, column=6, value=f"=ABS(E{r}-D{r})/D{r}")
        ws.cell(row=r, column=7, value=f'=IF(F{r}<0.05,"PASS","CHECK")')
        r += 1

    ws.cell(row=r + 1, column=1,
            value="N=5,000 gives a sampling standard error of a few percent on a realized standard deviation, "
                  "so differences up to about 5% are expected Monte Carlo noise, not a model error; the "
                  "convergence study (Report Section 5.5) quantifies this directly.")
    ws.cell(row=r + 1, column=1).font = NOTE
    ws.merge_cells(start_row=r + 1, start_column=1, end_row=r + 1, end_column=7)
    _autosize(ws, [22, 14, 14, 26, 26, 16, 12])


def build_vega_bump_sheet(wb, calib, trades, isin):
    """Bump one equity's volatility +/-1% (relative) and compare the closed-form
    (undiscounted Black) vega of a simple ATM position against the vega the
    Monte Carlo engine actually produces for the same position, at the same
    simulated node -- the "bump vol of equities and show it matches" check."""
    from risk_engine.simulation.engine import SimulationEngine
    import copy

    ws = wb.create_sheet("Equity vega bump")
    _title(ws, "4. Bumping equity volatility: closed-form vega vs Monte Carlo vega",
           "A hypothetical $1,000,000 receive-equity position, struck at today's spot (K=S0). Its expected exposure "
           "at a future date T is E[max(S_T-K,0)] per share, which for a lognormal S_T has the closed-form (undiscounted "
           "Black) formula below -- live in this sheet -- bumped +/-1% relative vol, and checked against the same "
           "bump run through the Monte Carlo engine (N=5,000, Latin Hypercube, same seed as the base run).")

    vol0 = float(calib["gbm"].vols[isin])
    S0 = float(calib["gbm"].spots0[isin])
    q = float(calib["gbm"].dividends.get(isin, 0.0))
    notional = 1_000_000.0

    ws["A4"], ws["C4"] = "Spot S0", S0
    ws["A5"], ws["C5"] = "Strike K (= S0, ATM)", S0
    ws["A6"], ws["C6"] = "Base volatility", vol0
    ws["A7"], ws["C7"] = "Notional (USD)", notional
    ws["A8"], ws["C8"] = "Shares (= notional / S0)", "=C7/C4"

    times = None
    node = None
    T = None
    rows_out = []
    for label, mult in (("Base", 1.0), ("Vol +1%", 1.01), ("Vol -1%", 0.99)):
        c = dict(calib)
        c["gbm"] = copy.deepcopy(calib["gbm"])
        c["gbm"].vols[isin] = vol0 * mult
        eng = SimulationEngine(c, trades, method="latin_hypercube", n_scenarios=5000, seed=42)
        paths = eng.simulate_paths()
        if times is None:
            times = np.array(eng.times)
            node = int(np.argmin(np.abs(times - 1.0)))
            T = float(times[node])
            r = -np.log(calib["usd_curve"].discount(eng.dates[node])) / T
        s_t = np.exp(paths["ln_spot"][isin][:, node])
        ee_sim = float(np.mean(np.maximum(s_t - S0, 0.0)))
        rows_out.append((label, vol0 * mult, ee_sim))

    row = 10
    ws.cell(row=row, column=1, value="Node T (years, ~1y)").value
    ws["A10"], ws["C10"] = "Node T (years, ~1y)", T
    ws["A11"], ws["C11"] = "Deterministic r (zero rate to T, from today's curve)", r
    ws["A12"], ws["C12"] = "Dividend yield q", q

    row = 14
    _header(ws, row, ["Case", "Vol", "F = S0*EXP((r-q)*T)", "d1", "d2",
                      "Closed-form E[max(S_T-K,0)] per share (undiscounted Black)",
                      "x Shares = USD EE (closed-form)", "Simulated USD EE (Monte Carlo, same node)", "Diff"])
    row += 1
    r0 = row
    for i, (label, v, ee_sim) in enumerate(rows_out):
        rr = r0 + i
        ws.cell(row=rr, column=1, value=label)
        ws.cell(row=rr, column=2, value=v)
        ws.cell(row=rr, column=3, value=f"=$C$4*EXP(($C$11-$C$12)*$C$10)")
        ws.cell(row=rr, column=4, value=f"=(LN(C{rr}/$C$5)+0.5*B{rr}^2*$C$10)/(B{rr}*SQRT($C$10))")
        ws.cell(row=rr, column=5, value=f"=D{rr}-B{rr}*SQRT($C$10)")
        ws.cell(row=rr, column=6, value=f"=C{rr}*NORM.S.DIST(D{rr},TRUE)-$C$5*NORM.S.DIST(E{rr},TRUE)")
        ws.cell(row=rr, column=7, value=f"=F{rr}*$C$8")
        ws.cell(row=rr, column=8, value=ee_sim * notional / S0)
        ws.cell(row=rr, column=9, value=f"=ABS(G{rr}-H{rr})/H{rr}")
    r_up, r_dn = r0 + 1, r0 + 2
    ws.cell(row=r0 + 4, column=1, value="Vega (per +1% relative vol), closed-form")
    ws.cell(row=r0 + 4, column=3, value=f"=(G{r_up}-G{r_dn})/2")
    ws.cell(row=r0 + 5, column=1, value="Vega (per +1% relative vol), Monte Carlo")
    ws.cell(row=r0 + 5, column=3, value=f"=(H{r_up}-H{r_dn})/2")
    ws.cell(row=r0 + 6, column=1, value="Ratio (MC / closed-form)")
    ws.cell(row=r0 + 6, column=3, value=f"=C{r0+5}/C{r0+4}")
    ws.cell(row=r0 + 8, column=1,
            value="A USD-listed name is used deliberately, so the drift is the simple r-q (no JPY quanto correction, "
                  "Section 4). The closed-form formula still assumes a constant rate to T (today's zero rate) and no "
                  "rate-equity correlation; the engine simulates a stochastic Hull-White short rate correlated with "
                  "equities. That is a real, small, and separately-quantified source of difference (Section 7.9, "
                  "model risk), not a bug: the two vegas are expected to be close, not identical.")
    ws.cell(row=r0 + 8, column=1).font = NOTE
    ws.merge_cells(start_row=r0 + 8, start_column=1, end_row=r0 + 8, end_column=9)
    _autosize(ws, [30, 10, 14, 10, 10, 24, 18, 20, 10])


def main():
    from run_simulation import load_trades
    from risk_engine.models.calibration import build_calibration, load_vol_table

    calib = build_calibration(REF)
    trades = load_trades()
    vol_table = load_vol_table()
    px = pd.read_csv(os.path.join(ROOT, "data", "raw", "backtest_prices.csv"), index_col=0, parse_dates=True)

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    sample = build_equity_sheet(wb, calib, vol_table, px)
    build_rate_sheet(wb, calib)
    build_simcheck_sheet(wb, calib, trades, sample)
    from risk_engine.models.calibration import _isin_currency
    currencies = _isin_currency()
    vega_isin = next(s for s in sample if s != "FX_USDJPY" and currencies.get(s) == "USD")
    build_vega_bump_sheet(wb, calib, trades, vega_isin)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    wb.save(OUT)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
