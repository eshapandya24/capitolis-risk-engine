p = "scripts/martingale_test.py"
s = open(p, encoding="utf-8").read()
i = s.index('    print("\\n=== Test 2: equity gains-process martingale')
j = s.index("    print(f\"\\n{'PASS' if all_ok")
new = '''    print("\\n=== Test 2: equity gains-process martingale  E[S_T*e^(qT)*disc] vs S_0 (USD value for JPY names) ===")
    cur = getattr(gbm, "currencies", {})
    jp = [f for f in gbm.vols if cur.get(f) == "JPY"]
    us = [f for f in gbm.vols if f in gbm.spots0 and f != "FX_USDJPY" and cur.get(f) != "JPY"]
    tickers = sorted(us, key=lambda f: -gbm.vols[f])[:4] + sorted(jp, key=lambda f: -gbm.vols[f])[:2]
    T_final_idx = len(eng.dates) - 1
    T_final = times[T_final_idx]
    x_fx0 = gbm.spots0["FX_USDJPY"]
    for isin in tickers:
        S0 = gbm.spots0[isin]
        q = gbm.dividends.get(isin, 0.0)
        ST = np.exp(paths["ln_spot"][isin][:, T_final_idx])
        if cur.get(isin) == "JPY":
            # a JPY name is a martingale in USD terms: S / X, with X = JPY per USD
            ST = ST / np.exp(paths["ln_fx"][:, T_final_idx])
            S0 = S0 / x_fx0
        gains = ST * np.exp(q * T_final) * disc[:, T_final_idx]
        mc_mean = gains.mean()
        se = gains.std() / np.sqrt(n_scenarios)
        z = (mc_mean - S0) / se if se > 0 else 0.0
        ok = abs(z) < 4
        all_ok &= ok
        tag = "(JPY, USD value)" if cur.get(isin) == "JPY" else ""
        print(f"  {isin:14s} {tag:17s} S0={S0:9.3f}  E[gains]={mc_mean:9.3f} +/- {se:6.4f}  z={z:+.2f}  "
              f"{'OK' if ok else 'FAIL'}")

    print("\\n=== Test 3: JPY bank account in USD  E[B_JPY(T) / (X_T B_USD(T))] = 1/X_0 ===")
    hwj = calib.get("hw_jpy")
    if hwj is not None and "x_jpy" in paths:
        disc_j = money_market_discount(hwj, paths["x_jpy"], times)      # exp(-int r_JPY)
        bj = 1.0 / disc_j[:, T_final_idx]
        v = x_fx0 * bj * disc[:, T_final_idx] / np.exp(paths["ln_fx"][:, T_final_idx])
        se = v.std() / np.sqrt(n_scenarios)
        z = (v.mean() - 1.0) / se
        ok = abs(z) < 4
        all_ok &= ok
        print(f"  E = {v.mean():.5f} +/- {se:.5f}  z={z:+.2f}  {'OK' if ok else 'FAIL'}")
        print("  (USDJPY drifts down when USD rates exceed JPY rates: mean ln(X_T/X_0) = "
              f"{(paths['ln_fx'][:, T_final_idx] - paths['ln_fx'][:, 0]).mean():+.4f})")

'''
s = s[:i] + new + s[j:]
open(p, "w", encoding="utf-8").write(s)
print("martingale patched")
