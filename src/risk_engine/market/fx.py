"""
USDJPY FX spot and forward curve — fetch/clean/cache.

Needed only for the JPY compo trades (EQTRS_0005, EQTRS_0006). See
data/MARKET_DATA.md §3. Spot is live via yfinance (`JPY=X`, quoted JPY per
USD, matching the pricer's convention).

Forward points: previously stubbed (no free live source). Now filled in
using the user's Bloomberg data export (data/raw/bloomberg/ — a one-time
static snapshot dated 2026-08-31, not a live feed; see
market/bloomberg.py's module docstring) when available; falls back to
spot-only (the original behavior) if that data isn't present.

Only the spot is required to *price*; the forward curve is a simulation-only
input (see capitolis_pricers README §6-7) -- EXCEPT that having real
forward points also lets us back out an actual JPY discount curve (see
build_fx_curve below), which is a genuine improvement over assuming FX
forwards purely from covered interest parity off a single USD curve.
"""
from datetime import timedelta

import yfinance as yf

TICKER = "JPY=X"  # USDJPY: JPY per USD

# Tenor label -> approximate year fraction, for sorting/pillar placement.
# Exact dates are used for the actual curve-fraction computation below
# (add_months/timedelta), this is only used to pick calendar offsets.
_TENOR_MONTHS = {"1W": None, "2W": None, "3W": None, "1M": 1, "2M": 2, "3M": 3,
                 "4M": 4, "6M": 6, "9M": 9, "12M": 12, "2Y": 24, "3Y": 36, "5Y": 60}
_TENOR_WEEKS = {"1W": 1, "2W": 2, "3W": 3}


def fetch_spot():
    """Pull live USDJPY spot. Returns float (JPY per USD)."""
    return yf.Ticker(TICKER).fast_info.last_price


def fetch_forward_points(ref_date=None):
    """Real USDJPY forward points curve, from the Bloomberg data export
    (data/raw/bloomberg/). Returns {tenor_label: forward_adjustment_jpy}
    (already unscaled -- see bloomberg.py's FWD_SCALE note). Raises if that
    data isn't present (no free live source for this exists)."""
    from .bloomberg import load_usdjpy_forward_points, available
    if not available():
        raise FileNotFoundError(
            "No live free source for FX forward points, and the Bloomberg data export "
            "(data/raw/bloomberg/) isn't present -- see data/MARKET_DATA.md #3")
    return load_usdjpy_forward_points()


def build_fx_curve(ref_date, usd_curve, spot=None):
    """Builds a real capitolis_pricers.curves.FxCurve using ACTUAL quoted
    USDJPY forward points (not just covered-interest-parity off one curve).

    Method: for each quoted tenor, forward = spot + forward_points. Covered
    interest parity says F(T) = S * DF_usd(T) / DF_jpy(T), so inverting
    gives an IMPLIED JPY discount factor at each tenor:

        DF_jpy(T) = DF_usd(T) * S / F(T)

    Building a Curve from those implied JPY discount factors and handing it
    to FxCurve as `quote_curve` means FxCurve.forward(T) reproduces the
    REAL quoted forward exactly (by construction) at every quoted tenor,
    rather than assuming forwards derive purely from our own USD curve with
    no JPY-side information at all (the previous spot-only behavior).

    This is still not a full stochastic JPY curve for simulation (see
    models/equity_fx.py's constant-differential simplification, which this
    doesn't change) -- it upgrades the deterministic/pricing-time FX curve
    only. Falls back to a spot-only FxCurve (the original behavior) if the
    Bloomberg forward-points data isn't available.
    """
    from capitolis_pricers.curves import Curve, FxCurve
    from capitolis_pricers.daycount import to_date, add_months, year_fraction

    ref = to_date(ref_date)
    try:
        points = fetch_forward_points(ref_date)
    except FileNotFoundError:
        s = spot if spot is not None else fetch_spot()
        return FxCurve("USD", "JPY", s, usd_curve)

    if spot is None:
        from .bloomberg import load_usdjpy_spot
        spot = load_usdjpy_spot()

    pillar_times, jpy_dfs = [0.0], [1.0]
    for tenor_label, points_adj in points.items():
        if tenor_label in _TENOR_WEEKS:
            d = ref + timedelta(weeks=_TENOR_WEEKS[tenor_label])
        elif tenor_label in _TENOR_MONTHS and _TENOR_MONTHS[tenor_label] is not None:
            d = add_months(ref, _TENOR_MONTHS[tenor_label])
        else:
            continue
        t = year_fraction(ref, d, usd_curve.basis)
        if t <= 0:
            continue
        forward = spot + points_adj
        df_usd = usd_curve.discount(d)
        df_jpy = df_usd * spot / forward
        pillar_times.append(t)
        jpy_dfs.append(df_jpy)

    order = sorted(range(len(pillar_times)), key=lambda i: pillar_times[i])
    pillar_times = [pillar_times[i] for i in order]
    jpy_dfs = [jpy_dfs[i] for i in order]

    jpy_curve = Curve(ref, pillar_times, jpy_dfs, basis=usd_curve.basis)
    return FxCurve("USD", "JPY", spot, usd_curve, jpy_curve)


def fetch_history(start, end):
    """Daily USDJPY close history for vol/correlation calibration (data/MARKET_DATA.md #5)."""
    return yf.Ticker(TICKER).history(start=start, end=end)["Close"]
