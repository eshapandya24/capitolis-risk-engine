"""
Multiprocessing wrapper around SimulationEngine.price_one_scenario -- each
scenario's repricing is fully independent of every other scenario, so this
is an embarrassingly-parallel workload. Splits scenarios into chunks, sends
the engine + full paths ONCE per worker (via Pool's initializer, not once
per task), and each worker prices its chunk using the exact same
price_one_scenario() the serial path uses -- no separate/divergent pricing
logic.

Windows uses the 'spawn' start method, so the worker-init function and the
per-task function must both be plain module-level functions (not closures
or lambdas), and the driver script must guard its top-level work in
`if __name__ == "__main__":` -- see scripts/run_simulation.py.
"""
import os
from multiprocessing import get_context

_WORKER = {}


def _init_worker(engine, paths):
    _WORKER["engine"] = engine
    _WORKER["paths"] = paths


def _price_chunk(scenario_indices):
    engine = _WORKER["engine"]
    paths = _WORKER["paths"]
    import numpy as np
    n_trades = len(engine.trades)
    out = np.zeros((n_trades, len(engine.dates), len(scenario_indices)), dtype=np.float64)
    for i, s in enumerate(scenario_indices):
        out[:, :, i] = engine.price_one_scenario(paths, s)
    return out


def reprice_all_parallel(engine, paths, n_workers=None, chunks_per_worker=4):
    """Same result shape/semantics as engine.reprice_all(paths), computed
    across processes. Must be called from inside `if __name__ == '__main__':`
    on Windows."""
    import numpy as np

    n_workers = n_workers or os.cpu_count() or 4
    n_scen = engine.n_scenarios
    chunk_size = max(1, n_scen // (n_workers * chunks_per_worker))
    chunks = [list(range(i, min(i + chunk_size, n_scen))) for i in range(0, n_scen, chunk_size)]

    ctx = get_context("spawn")
    with ctx.Pool(processes=n_workers, initializer=_init_worker, initargs=(engine, paths)) as pool:
        results = pool.map(_price_chunk, chunks)

    trade_ids = list(engine.trades.keys())
    npv = np.concatenate(results, axis=2)
    return trade_ids, npv
