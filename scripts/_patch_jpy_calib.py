p = "src/risk_engine/models/calibration.py"
s = open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert a in s, a[:60]
    s = s.replace(a, b, 1)


new_fn = '''def calibrate_jpy_rate_correlations(ref_date, lookback_years=3, rate_tenor=1):
    """Correlation of the JPY short-rate factor's daily shocks with USDJPY and
    with every equity, from the SAME 3-year daily window used for the vols
    and the correlation matrix (data/processed/history_*.csv).

    The JPY factor is a short-rate model, but the overnight call rate moves in
    steps on BoJ meeting days, so its daily changes are almost pure noise
    against market returns. The 1-year OIS zero-ish par rate (JYSO1 in the
    JPY OIS history) responds to the same policy news day by day and is the
    standard proxy for the short-rate factor's shock; its daily change is used
    here. RATE_USD's correlation with the JPY factor is calibrated
    separately from SOFR/TONA (calibrate_usd_jpy_rate_corr) and is not
    returned here.

    Returns {"corr": {factor: rho}, "n_obs": int, "rate_col": str, "window": (start, end)}.
    Raises if the JPY OIS history or the return histories are unavailable."""
    from ..market import jpy_ois

    if not jpy_ois.available():
        raise FileNotFoundError("JPY OIS history not found under data/raw/sources/")
    hist = jpy_ois.load_jpy_ois_history()
    col = next(c for c in hist.columns if c.startswith("JYSO") and abs(jpy_ois.tenor_years(c) - rate_tenor) < 1e-9)
    d_rate = hist[col].diff().dropna() / 100.0

    eq = pd.read_csv(os.path.join(PROCESSED, "history_equities.csv"), index_col=0, parse_dates=True)
    fx = pd.read_csv(os.path.join(PROCESSED, "history_usdjpy.csv"), index_col=0, parse_dates=True)["USDJPY"]
    rets = np.log(eq).diff()
    rets["FX_USDJPY"] = np.log(fx).diff()
    end = pd.Timestamp(ref_date)
    rets = rets[(rets.index > end - pd.DateOffset(years=lookback_years)) & (rets.index <= end)]
    joined = rets.join(d_rate.rename("_rate"), how="inner").dropna(subset=["_rate"])
    if len(joined) < 100:
        raise ValueError(f"Only {len(joined)} overlapping days between JPY OIS changes and returns")
    out = {}
    for f in rets.columns:
        pair = joined[[f, "_rate"]].dropna()
        out[f] = float(pair[f].corr(pair["_rate"])) if len(pair) >= 100 else 0.0
    return {"corr": out, "n_obs": int(len(joined)), "rate_col": col,
            "window": (str(joined.index.min().date()), str(joined.index.max().date()))}


def build_calibration(ref_date):'''
rep("def build_calibration(ref_date):", new_fn)
rep('''    equity_factor_names = [f for f in factor_order if f not in ("FX_USDJPY", "RATE_USD")]''', '''    try:
        jpy_corr_detail = calibrate_jpy_rate_correlations(ref_date)
        jpy_rate_corr = jpy_corr_detail["corr"]
        print(f"  JPY-rate factor correlations from {jpy_corr_detail['rate_col']} daily changes "
              f"(n={jpy_corr_detail['n_obs']}): USDJPY {jpy_rate_corr['FX_USDJPY']:+.3f}, "
              f"equities {min(v for k, v in jpy_rate_corr.items() if k != 'FX_USDJPY'):+.3f} to "
              f"{max(v for k, v in jpy_rate_corr.items() if k != 'FX_USDJPY'):+.3f}")
    except Exception as exc:
        print(f"  WARN: could not calibrate JPY-rate correlations with FX/equities ({exc}); "
              f"the JPY factor will only correlate with the USD rate")
        jpy_rate_corr, jpy_corr_detail = {}, None

    equity_factor_names = [f for f in factor_order if f not in ("FX_USDJPY", "RATE_USD")]''')
rep('''        "usd_jpy_rate_factor_corr_detail": usd_jpy_corr_detail,''', '''        "usd_jpy_rate_factor_corr_detail": usd_jpy_corr_detail,
        "jpy_rate_corr": jpy_rate_corr,
        "jpy_rate_corr_detail": jpy_corr_detail,''')
open(p, "w", encoding="utf-8").write(s)
print("ok")
