import re


def patch(path, edits):
    s = open(path, encoding="utf-8").read()
    for a, b in edits:
        assert a in s, (path, a[:70])
        s = s.replace(a, b, 1)
    open(path, "w", encoding="utf-8").write(s)


# ------------------------------------------------------------- greeks/exposure.py
patch("src/risk_engine/greeks/exposure.py", [
    ('''def apply_rows(base_npv, rows, arr):''', '''class CloseOut:
    """Context for measuring exposure on the brief's definition,
    max(V(t+10bd) - V(t-1bd), 0), from an engine built with mpor_days and
    vm_lag_days (see exposure/spec_exposure.py). `keep` is the list of
    reporting dates (indices into the node map) within `horizon_days` of the
    reference date; all measures are returned on those dates only."""

    def __init__(self, engine, ref_date, horizon_days=365):
        from datetime import date as _d
        self.node_map = engine.node_map
        self.dates = engine.dates
        self.trade_expiry = dict(engine.trade_expiries)
        self.prev = {i: (m["prev"] if m["prev"] is not None else m["reporting"])
                     for i, m in engine.node_map.items()}
        self.reporting_idx = [engine.node_map[i]["reporting"] for i in range(len(engine.node_map))]
        self.keep = [i for i, r in enumerate(self.reporting_idx)
                     if (engine.dates[r] - ref_date).days <= horizon_days]

    def report_dates(self):
        return [self.dates[self.reporting_idx[i]] for i in self.keep]


def measures_closeout(trade_ids, trade_counterparty, npv, ctx, conf=CONF):
    """Like `measures`, on the close-out exposure of `ctx` (CloseOut)."""
    from ..exposure import spec_exposure as spec
    by = spec.exposure_by_counterparty(trade_ids, trade_counterparty, np.nan_to_num(npv), ctx.node_map,
                                       prev_node=ctx.prev, trade_expiry=ctx.trade_expiry,
                                       exclude_maturing=True, dates=ctx.dates)
    exp = {c: a[ctx.keep, :] for c, a in by.items()}
    exp["__portfolio__"] = sum(exp[c] for c in sorted(exp))
    return {c: {"EE": a.mean(1), "MED": np.quantile(a, 0.5, axis=1), "PFE": np.quantile(a, conf, axis=1)}
            for c, a in exp.items()}


def apply_rows(base_npv, rows, arr):'''),
])

# ------------------------------------------------------------- run_greeks.py
patch("scripts/run_greeks.py", [
    ('''    ap.add_argument("--crn-repeats", type=int, default=4)
    args = ap.parse_args()
''', '''    ap.add_argument("--crn-repeats", type=int, default=4)
    ap.add_argument("--convention", choices=("closeout", "level"), default="closeout",
                    help="closeout: exposure = max(V(t+10bd) - V(t-1bd), 0) within one year (the brief); "
                         "level: uncollateralized max(V, 0) over the whole life (earlier version)")
    args = ap.parse_args()
    global OUT
    if args.convention == "level":
        OUT = OUT.replace("greeks_results.json", "greeks_results_level.json")
'''),
    ('''    from risk_engine.greeks.exposure import measures, apply_rows, diff_measures
''', '''    from risk_engine.greeks.exposure import measures, apply_rows, diff_measures, CloseOut, measures_closeout
'''),
    ('''    eng = SimulationEngine(calib, trades, method="latin_hypercube", n_scenarios=N, seed=42)
    t0 = time.perf_counter()
    paths = eng.simulate_paths()
    ids, npv0 = reprice_all_parallel(eng, paths)
    npv0 = np.nan_to_num(npv0)
    timing["base_run_s"] = time.perf_counter() - t0
    node_idx = list(range(len(eng.dates)))
    cpm = eng.trade_counterparty
    base = measures(ids, cpm, npv0, node_idx)
    res = {"n_scenarios": N, "dates": [str(d) for d in eng.dates], "times": list(map(float, eng.times)),
           "base": base, "book_t0": book, "equity": {}, "timing": timing}''', '''    closeout = args.convention == "closeout"
    eng_kw = dict(mpor_days=10, vm_lag_days=1) if closeout else {}

    def make_engine(cal, n, seed):
        return SimulationEngine(cal, trades, method="latin_hypercube", n_scenarios=n, seed=seed, **eng_kw)

    def measure(e, ids_, npv_):
        """Exposure measures on the chosen convention for engine `e`."""
        if closeout:
            return measures_closeout(ids_, e.trade_counterparty, npv_, CloseOut(e, ref))
        return measures(ids_, e.trade_counterparty, npv_, list(range(len(e.dates))))

    eng = make_engine(calib, N, 42)
    t0 = time.perf_counter()
    paths = eng.simulate_paths()
    ids, npv0 = reprice_all_parallel(eng, paths)
    npv0 = np.nan_to_num(npv0)
    timing["base_run_s"] = time.perf_counter() - t0
    cpm = eng.trade_counterparty
    base = measure(eng, ids, npv0)
    if closeout:
        ctx0 = CloseOut(eng, ref)
        out_dates = ctx0.report_dates()
        out_times = [eng.times[ctx0.reporting_idx[i]] for i in ctx0.keep]
    else:
        out_dates, out_times = list(eng.dates), list(eng.times)
    res = {"n_scenarios": N, "convention": args.convention, "dates": [str(d) for d in out_dates],
           "times": list(map(float, out_times)),
           "base": base, "book_t0": book, "equity": {}, "timing": timing}'''),
    ('''        M[(kind, name, tag)] = measures(ids, cpm, apply_rows(npv0, rows, arr), node_idx)''',
     '''        M[(kind, name, tag)] = measure(eng, ids, apply_rows(npv0, rows, arr))'''),
    ('''        e2 = SimulationEngine(cal, trades, method="latin_hypercube", n_scenarios=n, seed=seed)
        p2 = e2.simulate_paths()
        i2, n2 = reprice_all_parallel(e2, p2)
        return measures(i2, e2.trade_counterparty, np.nan_to_num(n2), list(range(len(e2.dates))))''',
     '''        e2 = make_engine(cal, n, seed)
        p2 = e2.simulate_paths()
        i2, n2 = reprice_all_parallel(e2, p2)
        return measure(e2, i2, np.nan_to_num(n2))'''),
    ('''        e = SimulationEngine(calib, trades, method="latin_hypercube", n_scenarios=args.crn_n, seed=seed_a)
        p = e.simulate_paths()
        i_, n_ = reprice_all_parallel(e, p)
        n_ = np.nan_to_num(n_)
        b_ = measures(i_, e.trade_counterparty, n_, list(range(len(e.dates))))''', '''        e = make_engine(calib, args.crn_n, seed_a)
        p = e.simulate_paths()
        i_, n_ = reprice_all_parallel(e, p)
        n_ = np.nan_to_num(n_)
        b_ = measure(e, i_, n_)'''),
    ('''        u_ = measures(i_, e.trade_counterparty, apply_rows(n_, *rows_arr), list(range(len(e.dates))))''',
     '''        u_ = measure(e, i_, apply_rows(n_, *rows_arr))'''),
])
print("greeks patched")


# ------------------------------------------------------------- run_sa_cva.py
patch("scripts/run_sa_cva.py", [
    ('''def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", type=int, default=1000)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    global OUT
    if args.tag:
        OUT = OUT + "_" + args.tag
    os.makedirs(OUT, exist_ok=True)
''', '''def closeout_dee(eng, paths, ids, npv):
    """Discounted EE of the brief's exposure, max(V(t+10bd) - V(t-1bd), 0),
    per counterparty on the reporting dates (whole life, not just one year:
    CVA integrates over the life of the trades)."""
    from risk_engine.exposure import spec_exposure as spec
    from risk_engine.exposure.cva import path_discount_factors
    prev = {i: (m["prev"] if m["prev"] is not None else m["reporting"]) for i, m in eng.node_map.items()}
    by = spec.exposure_by_counterparty(ids, eng.trade_counterparty, np.nan_to_num(npv), eng.node_map,
                                       prev_node=prev, trade_expiry=dict(eng.trade_expiries),
                                       exclude_maturing=True, dates=eng.dates)
    ridx = [eng.node_map[i]["reporting"] for i in range(len(eng.node_map))]
    disc = path_discount_factors(paths["x_rate"], eng.times, eng.hw)[:, ridx]
    times = np.array([eng.times[r] for r in ridx])
    return times, {c: (by[c] * disc.T).mean(axis=1) for c in by}


def run_closeout(calib, trades, n, bumps, holders_by_bucket, fx_holders):
    """All SA-CVA cases on the close-out exposure. Equity and FX delta bumps
    reuse the base paths (spot bumps rescale GBM paths exactly) and reprice
    only the trades holding the bumped factor; rate and vol bumps
    re-simulate with the same random numbers."""
    from risk_engine.simulation.engine import SimulationEngine
    from risk_engine.simulation.parallel import reprice_all_parallel, reprice_bumps_parallel
    from risk_engine.greeks.exposure import apply_rows

    def cached(key):
        path = os.path.join(OUT, key + ".npz")
        if os.path.exists(path):
            z = np.load(path, allow_pickle=True)
            return z["times"], {c: z["dee_" + c] for c in ("CPTY_A", "CPTY_B", "CPTY_C")}
        return None

    def save(key, times, dee):
        np.savez(os.path.join(OUT, key + ".npz"), times=times, **{"dee_" + c: v for c, v in dee.items()})

    def build(cal):
        return SimulationEngine(cal, trades, method="latin_hypercube", n_scenarios=n, seed=42,
                                mpor_days=10, vm_lag_days=1)

    res = {}
    base_key = key_of(("base", "-"))
    eng = build(calib)
    paths = eng.simulate_paths()
    base_npv_path = os.path.join(OUT, "base_npv.npz")
    t0 = time.perf_counter()
    if os.path.exists(base_npv_path):
        ids, npv0 = list(np.load(base_npv_path, allow_pickle=True)["ids"]), np.load(base_npv_path)["npv"]
    else:
        ids, npv0 = reprice_all_parallel(eng, paths)
        npv0 = np.nan_to_num(npv0)
        np.savez_compressed(base_npv_path, ids=np.array(ids), npv=npv0)
    times, dee = closeout_dee(eng, paths, ids, npv0)
    save(base_key, times, dee)
    res[base_key] = (times, dee)
    print(f"  base done in {time.perf_counter() - t0:.0f}s", flush=True)

    delta = [b for b in bumps if b[0] in ("eq_delta", "fx_delta")]
    if delta:
        specs = []
        for b in delta:
            if b[0] == "fx_delta":
                specs.append({"eq": {}, "fx": 1.01, "trades": set(fx_holders)})
            else:
                names = b[2]
                held = set().union(*[holders_by_bucket.get(i, set()) for i in names])
                specs.append({"eq": {i: 1.01 for i in names}, "fx": 1.0, "trades": held})
        t0 = time.perf_counter()
        out = reprice_bumps_parallel(eng, paths, specs)
        for b, (rows, arr) in zip(delta, out):
            t2, d2 = closeout_dee(eng, paths, ids, apply_rows(npv0, rows, arr))
            save(key_of(b), t2, d2)
            res[key_of(b)] = (t2, d2)
        print(f"  {len(delta)} equity/FX delta bumps (subset repricing) in {time.perf_counter() - t0:.0f}s", flush=True)

    for b in bumps:
        k = key_of(b)
        if k in res:
            continue
        hit = cached(k)
        if hit is not None:
            res[k] = hit
            continue
        t0 = time.perf_counter()
        e2 = build(make_calib(calib, b))
        p2 = e2.simulate_paths()
        i2, n2 = reprice_all_parallel(e2, p2)
        t2, d2 = closeout_dee(e2, p2, i2, n2)
        save(k, t2, d2)
        res[k] = (t2, d2)
        print(f"  {k:20s} re-simulated in {time.perf_counter() - t0:.0f}s", flush=True)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", type=int, default=1000)
    ap.add_argument("--tag", default="")
    ap.add_argument("--exposure", choices=("closeout", "level"), default="closeout",
                    help="closeout: exposure = max(V(t+10bd) - V(t-1bd), 0) (the brief); level: uncollateralized max(V, 0)")
    args = ap.parse_args()
    global OUT
    if args.exposure == "closeout":
        OUT = OUT + "_closeout"
    if args.tag:
        OUT = OUT + "_" + args.tag
    os.makedirs(OUT, exist_ok=True)
'''),
    ('''    res = {key_of(b): run_case(calib, trades, args.scenarios, b) for b in bumps}
''', '''    if args.exposure == "closeout":
        from risk_engine.greeks.book import book_greeks
        bg = book_greeks(calib, trades)
        holders = {i: {t for t, x in v["delta"].items() if abs(x) > 1e-6} for i, v in bg["equity"].items()}
        fx_holders = {t for t, x in bg["fx"]["delta"].items() if abs(x) > 1e-6}
        res = run_closeout(calib, trades, args.scenarios, bumps, holders, fx_holders)
    else:
        res = {key_of(b): run_case(calib, trades, args.scenarios, b) for b in bumps}
'''),
    ('''    out = {"n_scenarios": args.scenarios, "ref_date": str(ref),''', '''    out = {"n_scenarios": args.scenarios, "exposure": args.exposure, "ref_date": str(ref),'''),
    ('''    with open(os.path.join(ROOT, "data", "processed", "sa_cva_results%s.json" % (("_" + args.tag) if args.tag else "")), "w") as f:''',
     '''    name = "sa_cva_results%s%s.json" % ("_level" if args.exposure == "level" else "", ("_" + args.tag) if args.tag else "")
    with open(os.path.join(ROOT, "data", "processed", name), "w") as f:'''),
])
print("sa_cva patched")
