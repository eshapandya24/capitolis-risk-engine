"""
Monte Carlo engine: simulates the joint, correlated risk factors (USD short
rate via Hull-White, 37 equities + USDJPY via correlated GBM) forward
through time, builds a real capitolis_pricers.market.MarketState at every
(scenario, time-node) pair, and reprices every trade there using the
already-validated pricer library -- no new pricing logic, just repeated
calls to the same `.npv()` the rest of the project already trusts.

Time grid: monthly nodes from ref_date out to the last trade's own
termination/forward date (bonds' own maturity is irrelevant once the TRADE
on them has ended -- a matured/settled trade contributes zero exposure from
that point on, handled by `_is_active`).
"""
from datetime import date, timedelta

import numpy as np

from capitolis_pricers.market import MarketState
from capitolis_pricers.curves import FxCurve
from capitolis_pricers.daycount import to_date, year_fraction

from .random_numbers import generate as gen_randoms

MONTHLY_STEP_MONTHS = 1


def _add_months(d, n):
    from capitolis_pricers.daycount import add_months
    return add_months(d, n)


def trade_expiry(trade):
    """The date beyond which a trade contributes zero further exposure."""
    if hasattr(trade, "end_date"):
        return to_date(trade.end_date)
    if hasattr(trade, "forward_date"):
        return to_date(trade.forward_date)
    raise AttributeError(f"Don't know how to find the expiry of {trade!r}")


def build_time_grid(ref_date, trades, step_months=MONTHLY_STEP_MONTHS, mpor_days=None):
    """Monthly "reporting" nodes from ref_date to the last trade's expiry
    (inclusive). If `mpor_days` is given, an extra look-ahead node is
    inserted `mpor_days` calendar days after EVERY reporting node (used for
    MPOR-shifted/collateralized exposure -- see exposure/collateral.py) --
    both node types sit on the SAME simulated path, so the look-ahead value
    is a genuine "what does this same scenario look like a bit later"
    query, not a separate simulation. Returns (dates, times, reporting_idx)
    where reporting_idx maps each reporting node's position in `dates` to
    {"reporting": i, "lookahead": j or None} (None if mpor_days wasn't
    requested, or the look-ahead would fall past the trade horizon)."""
    ref_date = to_date(ref_date)
    horizon = max(trade_expiry(t) for t in trades.values())
    reporting_dates = [ref_date]
    d = ref_date
    while d < horizon:
        d = _add_months(d, step_months)
        reporting_dates.append(min(d, horizon))
        if d >= horizon:
            break

    if mpor_days is None:
        times = [year_fraction(ref_date, d, "ACT/365F") for d in reporting_dates]
        return reporting_dates, times, {i: {"reporting": i, "lookahead": None} for i in range(len(reporting_dates))}

    all_dates = set(reporting_dates)
    lookahead_for = {}
    for rd in reporting_dates:
        la = rd + timedelta(days=mpor_days)
        if la <= horizon:
            all_dates.add(la)
            lookahead_for[rd] = la
    dates = sorted(all_dates)
    date_to_idx = {d: i for i, d in enumerate(dates)}
    times = [year_fraction(ref_date, d, "ACT/365F") for d in dates]

    node_map = {}
    for i, rd in enumerate(reporting_dates):
        node_map[i] = {"reporting": date_to_idx[rd],
                        "lookahead": date_to_idx.get(lookahead_for.get(rd))}
    return dates, times, node_map


class SimulationEngine:
    def __init__(self, calib, trades, method="pseudo_random", n_scenarios=2000,
                 step_months=MONTHLY_STEP_MONTHS, seed=42, curve_tenors=(0.25, 0.5, 1, 2, 3, 5, 7, 10),
                 mpor_days=None):
        self.calib = calib
        self.trades = trades
        self.method = method
        self.n_scenarios = n_scenarios
        self.seed = seed
        self.curve_tenors = curve_tenors
        self.mpor_days = mpor_days

        self.hw = calib["hw"]
        self.gbm = calib["gbm"]
        self.factor_order = calib["factor_order"]  # [equities..., FX_USDJPY, RATE_USD]
        self.n_factors = len(self.factor_order)
        self.rate_idx = self.factor_order.index("RATE_USD")
        self.fx_idx = self.factor_order.index("FX_USDJPY")
        self.equity_idx = {f: i for i, f in enumerate(self.factor_order)
                            if f not in ("RATE_USD", "FX_USDJPY")}

        corr = calib["corr_matrix"].loc[self.factor_order, self.factor_order].values
        corr = _nearest_psd(corr)
        self.L = np.linalg.cholesky(corr)

        self.dates, self.times, self.node_map = build_time_grid(
            calib["ref_date"], trades, step_months, mpor_days=mpor_days)
        self.n_steps = len(self.times) - 1

        self.trade_expiries = {tid: trade_expiry(t) for tid, t in trades.items()}
        self.trade_counterparty = {tid: t.counterparty for tid, t in trades.items()}

    # ------------------------------------------------------------------
    def _correlated_draws(self):
        z = gen_randoms(self.method, self.n_scenarios, self.n_steps, self.n_factors, seed=self.seed)
        # correlate each step's cross-sectional draw: (n_scenarios, n_factors) @ L.T
        correlated = np.einsum("snf,gf->sng", z, self.L)
        return correlated

    def simulate_paths(self):
        """Returns dict: 'x_rate' (n_scen, n_nodes), 'ln_spot' {factor: (n_scen, n_nodes)}."""
        n_scen, n_steps = self.n_scenarios, self.n_steps
        z = self._correlated_draws()  # (n_scen, n_steps, n_factors)

        x_rate = np.zeros((n_scen, n_steps + 1))
        ln_spot = {f: np.zeros((n_scen, n_steps + 1)) for f in self.equity_idx}
        ln_fx = np.zeros((n_scen, n_steps + 1))

        for f, idx in self.equity_idx.items():
            ln_spot[f][:, 0] = np.log(self.gbm.spots0[f])
        ln_fx[:, 0] = np.log(self.gbm.spots0["FX_USDJPY"])

        for k in range(n_steps):
            t_prev, t_next = self.times[k], self.times[k + 1]
            dt = t_next - t_prev
            r_prev = self.hw.short_rate(x_rate[:, k], t_prev)  # vectorized short rate at step start

            z_rate = z[:, k, self.rate_idx]
            x_rate[:, k + 1] = _vec_step_x(self.hw, x_rate[:, k], dt, z_rate)

            for f, idx in self.equity_idx.items():
                z_f = z[:, k, idx]
                ln_spot[f][:, k + 1] = _vec_step_log_spot(self.gbm, ln_spot[f][:, k], f, r_prev, dt, z_f)

            z_fx = z[:, k, self.fx_idx]
            ln_fx[:, k + 1] = _vec_step_log_fx(self.gbm, ln_fx[:, k], r_prev, dt, z_fx)

        return {"x_rate": x_rate, "ln_spot": ln_spot, "ln_fx": ln_fx}

    def price_one_scenario(self, paths, s, node_indices=None):
        """Reprice every trade, for ONE scenario index `s`, across all (or a
        subset of) time nodes. Returns an (n_trades, len(node_indices)) array.
        This is the single unit of work shared by the serial path below and
        the multiprocessing path in simulation/parallel.py -- keeping exactly
        one implementation avoids the two ever silently diverging."""
        trade_ids = list(self.trades.keys())
        node_indices = range(len(self.dates)) if node_indices is None else node_indices
        out = np.zeros((len(trade_ids), len(node_indices)), dtype=np.float64)

        for oi, node_idx in enumerate(node_indices):
            node_date, t = self.dates[node_idx], self.times[node_idx]
            r_t = self.hw.short_rate(paths["x_rate"][s, node_idx], t)
            usd_curve = self.hw.fast_node_curve(node_date, t, r_t)
            equity_spots = {f: float(np.exp(paths["ln_spot"][f][s, node_idx]))
                             for f in self.equity_idx}
            fx_spot = float(np.exp(paths["ln_fx"][s, node_idx]))
            fx_curve = FxCurve("USD", "JPY", fx_spot, usd_curve)
            market = MarketState(
                ref_date=node_date, reporting_ccy="USD",
                discount_curves={"USD": usd_curve},
                equity_spots=equity_spots,
                equity_dividend_rates=self.gbm.dividends,
                fx_curves={("USD", "JPY"): fx_curve},
            )
            for ti, tid in enumerate(trade_ids):
                if node_date > self.trade_expiries[tid]:
                    continue
                try:
                    out[ti, oi] = self.trades[tid].npv(market, reporting=True)
                except Exception:
                    out[ti, oi] = np.nan
        return out

    def reprice_all(self, paths, scenario_stride=1):
        """Serial reprice of every scenario. Returns (trade_ids, npv array
        [n_trades, n_nodes, n_scenarios_used]). For large scenario counts,
        prefer simulation.parallel.reprice_all_parallel, which does exactly
        the same per-scenario work (price_one_scenario) across processes."""
        trade_ids = list(self.trades.keys())
        scen_range = range(0, self.n_scenarios, scenario_stride)
        npv = np.zeros((len(trade_ids), len(self.dates), len(scen_range)), dtype=np.float64)
        for si, s in enumerate(scen_range):
            npv[:, :, si] = self.price_one_scenario(paths, s)
        return trade_ids, npv


def _nearest_psd(corr, eps=1e-8):
    """Clip tiny negative eigenvalues (numerical noise from CSV round-trip)
    so Cholesky never fails; the matrix was already validated PSD at
    construction (correlations.py), this only guards float round-trip."""
    vals, vecs = np.linalg.eigh(corr)
    vals_clipped = np.clip(vals, eps, None)
    fixed = vecs @ np.diag(vals_clipped) @ vecs.T
    d = np.sqrt(np.diag(fixed))
    fixed = fixed / np.outer(d, d)
    np.fill_diagonal(fixed, 1.0)
    return fixed


def _vec_step_x(hw, x_prev, dt, z):
    import math
    a, sigma = hw.a, hw.sigma
    mean = x_prev * math.exp(-a * dt)
    var = (sigma ** 2 / (2 * a)) * (1 - math.exp(-2 * a * dt))
    return mean + math.sqrt(max(var, 0.0)) * z


def _vec_step_log_spot(gbm, ln_s_prev, isin, r_usd_t, dt, z):
    import math
    sigma = gbm.vols[isin]
    q = gbm.dividends.get(isin, 0.0)
    r = (r_usd_t - gbm.jpy_usd_rate_diff) if gbm.currencies.get(isin) == "JPY" else r_usd_t
    drift = (r - q - 0.5 * sigma ** 2) * dt
    return ln_s_prev + drift + sigma * math.sqrt(max(dt, 0.0)) * z


def _vec_step_log_fx(gbm, ln_fx_prev, r_usd_t, dt, z):
    import math
    sigma = gbm.fx_vol
    drift = (gbm.jpy_usd_rate_diff - 0.5 * sigma ** 2) * dt
    return ln_fx_prev + drift + sigma * math.sqrt(max(dt, 0.0)) * z
