p = "scripts/martingale_test.py"
s = open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert a in s, a[:70]
    s = s.replace(a, b, 1)


# collect results
rep("    all_ok = True\n", "    all_ok = True\n    results = {\"n_scenarios\": n_scenarios, \"equity_z\": {}, \"bank_account_max_rel_bp\": 0.0}\n")
rep("        all_ok &= ok\n        print(f\"  T={T:6.3f}y", "        all_ok &= ok\n        results[\"bank_account_max_rel_bp\"] = max(results[\"bank_account_max_rel_bp\"], rel_diff * 1e4)\n        print(f\"  T={T:6.3f}y")
rep("        tag = \"(JPY, USD value)\"", "        results[\"equity_z\"][isin] = float(z)\n        tag = \"(JPY, USD value)\"")
rep("        print(f\"  E = {v.mean():.5f} +/- {se:.5f}", "        results[\"jpy_account_z\"] = float(z)\n        results[\"usdjpy_mean_log_change\"] = float((paths['ln_fx'][:, T_final_idx] - paths['ln_fx'][:, 0]).mean())\n        print(f\"  E = {v.mean():.5f} +/- {se:.5f}")
i = s.index("    print(f\"\\n{'PASS' if all_ok")
s = s[:i] + "    import json as _json\n    _json.dump(results, open(os.path.join(ROOT, 'data', 'processed', 'martingale_results.json'), 'w'), indent=1)\n" + s[i:]
open(p, "w", encoding="utf-8").write(s)
print("ok")
