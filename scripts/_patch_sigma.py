p = "src/risk_engine/models/calibration.py"
s = open(p, encoding="utf-8").read()
a = '''    rate_vol = vol_table["RATE_USD"]
    mean_reversion_a, hw_calib_detail = load_or_calibrate_mean_reversion(ref_date)
'''
b = '''    rate_vol = vol_table["RATE_USD"]
    mean_reversion_a, hw_calib_detail = load_or_calibrate_mean_reversion(ref_date)
    rate_vol_detail = {"source": "overnight_sofr_realised", "sigma": rate_vol}
    try:
        from ..market import treasury
        ust_vols = treasury.realized_vols(ref_date)
        sigma_fit = treasury.fit_hw_sigma(mean_reversion_a, ust_vols)
        rate_vol_detail = {"source": "ust_cmt_realised_long_end_fit", "sigma": sigma_fit,
                           "sofr_overnight_sigma": rate_vol, "realised_vols": ust_vols,
                           "fit_tenors": list(treasury.FIT_TENORS)}
        print(f"  USD Hull-White sigma fitted to realised 2y-30y Treasury yield vols: {sigma_fit:.4%} "
              f"(overnight-SOFR realised vol was {rate_vol:.4%}; a={mean_reversion_a:.4f})")
        rate_vol = sigma_fit
    except Exception as exc:
        print(f"  WARN: Treasury long-end vol fit unavailable ({exc}); using overnight SOFR realised vol {rate_vol:.4%}")
'''
assert a in s
s = s.replace(a, b, 1)
a2 = '''        "hw_mean_reversion_a": mean_reversion_a,'''
assert a2 in s
s = s.replace(a2, '''        "hw_rate_vol_detail": rate_vol_detail,
        "hw_mean_reversion_a": mean_reversion_a,''', 1)
open(p, "w", encoding="utf-8").write(s)
print("ok")
