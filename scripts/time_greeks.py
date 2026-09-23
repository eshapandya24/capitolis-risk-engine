"""Clean timing of the Greeks machinery at N=300 (the N=2000 run's wall-clock
was inflated by the machine sleeping): base run, 82 equity/FX subset bumps in
one pool, and one full rate re-simulation. Merges into greeks_results.json."""
import json
import os
import sys
import time
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def main():
    from run_simulation import load_trades
    from risk_engine.models.calibration import build_calibration
    from risk_engine.simulation.engine import SimulationEngine
    from risk_engine.simulation.parallel import reprice_all_parallel, reprice_bumps_parallel
    from risk_engine.greeks.book import book_greeks
    from risk_engine.greeks.bumps import make_calib
    calib = build_calibration(date(2026, 8, 28))
    trades = load_trades()
    bg = book_greeks(calib, trades)
    holders = {i: {t for t, x in v["delta"].items() if abs(x) > 1e-6} for i, v in bg["equity"].items()}
    holders = {i: h for i, h in holders.items() if h}
    fx_h = {t for t, x in bg["fx"]["delta"].items() if abs(x) > 1e-6}
    all_t = set().union(*holders.values())
    N = 300
    eng = SimulationEngine(calib, trades, method="latin_hypercube", n_scenarios=N, seed=42, mpor_days=10, vm_lag_days=1)
    paths = eng.simulate_paths()
    t0 = time.perf_counter(); reprice_all_parallel(eng, paths); base = time.perf_counter() - t0
    bumps = []
    for isin, h in holders.items():
        for m in (1.01, 0.99):
            bumps.append({"eq": {isin: m}, "fx": 1.0, "trades": h})
    for m in (1.01, 0.99):
        bumps.append({"eq": {i: m for i in holders}, "fx": 1.0, "trades": all_t})
        bumps.append({"eq": {}, "fx": m, "trades": fx_h})
    t0 = time.perf_counter(); reprice_bumps_parallel(eng, paths, bumps); sub = time.perf_counter() - t0
    cal = make_calib(calib, ("ir_delta", None, 1e-4))
    t0 = time.perf_counter()
    e2 = SimulationEngine(cal, trades, method="latin_hypercube", n_scenarios=N, seed=42, mpor_days=10, vm_lag_days=1)
    p2 = e2.simulate_paths(); reprice_all_parallel(e2, p2); resim = time.perf_counter() - t0
    out = {"n": N, "base_run_s": base, "n_bumps": len(bumps), "subset_bumps_s": sub, "one_resim_s": resim}
    path = os.path.join(ROOT, "data", "processed", "greeks_results.json")
    g = json.load(open(path)); g["timing_clean"] = out
    json.dump(g, open(path, "w"))
    print(out)


if __name__ == "__main__":
    main()
