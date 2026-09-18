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

# Standard market curve pillar tenors -- the SAME convention already
# documented for our own SOFR curve (data/MARKET_DATA.md #1: "O/N, T/N,
# 1W, 2W, 1M, 2M, 3M, 6M, 9M, 1Y, 18M, 2Y, 3Y, 4Y, 5Y, 7Y, 10Y"). Named
# directly by Capitolis as the intended convention for simulation reporting
# dates, not just curve-building tenors: (days, months) pairs, used up to
# 1Y in days for precision (O/N=1 calendar day, not "1/365 months"), then
# in months beyond that (add_months handles month-length variation
# correctly, e.g. day-of-month clamping, which raw day-counting wouldn't).
PILLAR_TENORS_DAYS = [1, 2, 7, 14]              # O/N, T/N, 1W, 2W
PILLAR_TENORS_MONTHS = [1, 2, 3, 6, 9, 12, 18, 24, 36, 48, 60, 84, 120]  # 1M..10Y


def _add_months(d, n):
    from capitolis_pricers.daycount import add_months
    return add_months(d, n)


def pillar_dates(ref_date, horizon):
    """Standard market curve pillar dates from ref_date, capped at horizon
    -- see PILLAR_TENORS_* above. This is the industry-standard convention
    for where to observe/report exposure (dense near-term, sparse further
    out, because pillar tenor spacing is itself front-loaded), rather than
    an arbitrary uniform calendar grid."""
    ref_date = to_date(ref_date)
    dates = {ref_date}
    for days in PILLAR_TENORS_DAYS:
        d = ref_date + timedelta(days=days)
        if d <= horizon:
            dates.add(d)
    for months in PILLAR_TENORS_MONTHS:
        d = _add_months(ref_date, months)
        if d <= horizon:
            dates.add(d)
    dates.add(horizon)  # always include the final maturity itself
    return sorted(dates)


def trade_expiry(trade):
    """The date beyond which a trade contributes zero further exposure."""
    if hasattr(trade, "end_date"):
        return to_date(trade.end_date)
    if hasattr(trade, "forward_date"):
        return to_date(trade.forward_date)
    raise AttributeError(f"Don't know how to find the expiry of {trade!r}")


def trade_event_dates(trade):
    """Every cashflow/reset/termination date for a trade -- used as
    MANDATORY simulation grid nodes (see build_time_grid). Why this
    matters: a trade's exposure can jump discontinuously exactly on a
    reset or maturity date (a TRS funding leg re-strikes; a trade rolls off
    the book entirely), and a generic monthly grid has no reason to land on
    that exact date -- it would smooth over a real cliff instead of
    capturing it. Industry CCR engines handle this by forcing trade event
    dates into the monitoring-date grid rather than relying on a uniform
    schedule alone; this does the same, cheaply, since the engine already
    supports arbitrary non-uniform node spacing (proven by the MPOR
    look-ahead nodes, which use the same mechanism)."""
    from capitolis_pricers.daycount import schedule_forward
    if hasattr(trade, "reset_m"):  # Equity TRS, Bond TRS: full reset schedule
        return [to_date(d) for d in schedule_forward(trade.start_date, trade.end_date, trade.reset_m)]
    if hasattr(trade, "forward_date"):  # Bond Forward: single settlement date
        return [to_date(trade.forward_date)]
    return []


def build_time_grid(ref_date, trades, step_months=MONTHLY_STEP_MONTHS, mpor_days=None,
                     include_trade_event_dates=True, grid_mode="pillar"):
    """Base "reporting" nodes from ref_date to the last trade's expiry
    (inclusive), UNIONED with every trade's own reset/maturity/forward
    dates (see trade_event_dates) so exposure discontinuities land exactly
    on a simulated node rather than being smoothed over by the nearest
    generic grid point -- set include_trade_event_dates=False to disable.

    grid_mode picks how the BASE reporting dates (before the event-date
    union above) are chosen:
      - "pillar" (default, industry-standard): standard market curve pillar
        tenors (see pillar_dates/PILLAR_TENORS_* above) -- the same
        convention already used for building our own SOFR curve, dense
        near-term and progressively sparser further out, matching how
        production CCR/PFE systems actually choose monitoring dates.
      - "monthly": uniform monthly steps (the original, simpler approach --
        kept for comparison/backward compatibility, not recommended as the
        production default).

    If `mpor_days` is given, an extra look-ahead node is inserted
    `mpor_days` calendar days after EVERY reporting node (used for
    MPOR-shifted/collateralized exposure -- see exposure/collateral.py) --
    both node types sit on the SAME simulated path, so the look-ahead value
    is a genuine "what does this same scenario look like a bit later"
    query, not a separate simulation. Returns (dates, times, reporting_idx)
    where reporting_idx maps each reporting node's position in `dates` to
    {"reporting": i, "lookahead": j or None} (None if mpor_days wasn't
    requested, or the look-ahead would fall past the trade horizon)."""
    ref_date = to_date(ref_date)
    horizon = max(trade_expiry(t) for t in trades.values())

    if grid_mode == "pillar":
        base_dates = set(pillar_dates(ref_date, horizon))
    elif grid_mode == "monthly":
        base_dates = {ref_date}
        d = ref_date
        while d < horizon:
            d = _add_months(d, step_months)
            base_dates.add(min(d, horizon))
            if d >= horizon:
                break
    else:
        raise ValueError(f"grid_mode must be 'pillar' or 'monthly', got {grid_mode!r}")

    event_dates = set()
    if include_trade_event_dates:
        for t in trades.values():
            for ed in trade_event_dates(t):
                if ref_date < ed <= horizon:
                    event_dates.add(ed)

    reporting_dates = sorted(base_dates | event_dates)

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
                 mpor_days=None, grid_mode="pillar", include_trade_event_dates=True,
                 corr_mode="full", n_pca_factors=5):
        """
        corr_mode: "full" (default) -- exact Cholesky factor of the full
            39x39 empirical correlation matrix (unchanged behavior).
            "factor" -- PCA/factor-model approximation (see
            models/equity_factor_model.py): correlated shocks come from
            n_pca_factors common systematic drivers plus per-name
            idiosyncratic noise, instead of one full-rank Cholesky factor.
            Approximate by construction (see reconstruction_error there);
            offered as a more parsimonious, more estimation-robust
            alternative, not a replacement default.
        n_pca_factors: only used when corr_mode="factor".
        """
        self.calib = calib
        self.trades = trades
        self.method = method
        self.n_scenarios = n_scenarios
        self.seed = seed
        self.curve_tenors = curve_tenors
        self.mpor_days = mpor_days
        self.corr_mode = corr_mode
        self.n_pca_factors = n_pca_factors

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

        if corr_mode == "full":
            self.L = np.linalg.cholesky(corr)
        elif corr_mode == "factor":
            from ..models.equity_factor_model import build_pca_factor_loadings
            self.pca_B, self.pca_idio_var = build_pca_factor_loadings(corr, n_pca_factors)
        else:
            raise ValueError(f"Unsupported corr_mode {corr_mode!r}; expected 'full' or 'factor'")

        self.dates, self.times, self.node_map = build_time_grid(
            calib["ref_date"], trades, step_months, mpor_days=mpor_days,
            grid_mode=grid_mode, include_trade_event_dates=include_trade_event_dates)
        self.n_steps = len(self.times) - 1

        self.trade_expiries = {tid: trade_expiry(t) for tid, t in trades.items()}
        self.trade_counterparty = {tid: t.counterparty for tid, t in trades.items()}

    # ------------------------------------------------------------------
    def _correlated_draws(self):
        if self.corr_mode == "factor":
            return self._factor_correlated_draws()
        z = gen_randoms(self.method, self.n_scenarios, self.n_steps, self.n_factors, seed=self.seed)
        # correlate each step's cross-sectional draw: (n_scenarios, n_factors) @ L.T
        correlated = np.einsum("snf,gf->sng", z, self.L)
        return correlated

    def _factor_correlated_draws(self):
        """corr_mode="factor": build correlated shocks as
        B @ f + sqrt(idio_var) * e, f = k systematic draws, e = n
        idiosyncratic draws (own seed offset, so the idiosyncratic noise
        isn't spuriously correlated with the systematic factors through
        RNG-stream reuse)."""
        n_scen, n_steps, n = self.n_scenarios, self.n_steps, self.n_factors
        k = self.n_pca_factors
        f = gen_randoms(self.method, n_scen, n_steps, k, seed=self.seed)          # (n_scen, n_steps, k)
        e = gen_randoms(self.method, n_scen, n_steps, n, seed=self.seed + 1)       # (n_scen, n_steps, n)
        systematic = np.einsum("snk,fk->snf", f, self.pca_B)
        idio = e * np.sqrt(self.pca_idio_var)[None, None, :]
        return systematic + idio

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
