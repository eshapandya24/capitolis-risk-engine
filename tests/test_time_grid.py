"""
Regression tests for the simulation time grid (simulation/engine.py):
standard market pillar dates (Capitolis's own suggested convention -- the
same tenor points used to build our SOFR curve, dense near-term/sparse
further out) and mandatory trade event dates (so a trade's own
reset/maturity/settlement date always lands exactly on a simulated node,
not smoothed over by the nearest generic grid point).

All self-contained with fake trade objects -- no network needed.
"""
from datetime import date, timedelta

from risk_engine.simulation.engine import pillar_dates, trade_event_dates, build_time_grid


class _FakeTRS:
    """Duck-types the .reset_m/.start_date/.end_date shape of Equity TRS / Bond TRS."""
    def __init__(self, start_date, end_date, reset_m, counterparty="CPTY_X"):
        self.start_date = start_date
        self.end_date = end_date
        self.reset_m = reset_m
        self.counterparty = counterparty


class _FakeForward:
    """Duck-types Bond Forward's .forward_date shape."""
    def __init__(self, forward_date, counterparty="CPTY_X"):
        self.forward_date = forward_date
        self.counterparty = counterparty


def test_pillar_dates_are_dense_near_term_and_sparse_far_term():
    ref = date(2026, 1, 15)
    horizon = date(2036, 1, 15)  # a full 10y horizon to exercise the whole pillar set
    dates = pillar_dates(ref, horizon)

    gaps_days = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
    first_gap, last_gap = gaps_days[0], gaps_days[-1]
    assert first_gap < 10, f"expected a short near-term gap (O/N-ish), got {first_gap} days"
    assert last_gap > first_gap * 5, (
        f"expected far-term pillar spacing to be much wider than near-term: "
        f"first gap={first_gap}d, last gap={last_gap}d")


def test_pillar_dates_always_include_ref_date_and_horizon():
    ref = date(2026, 8, 28)
    horizon = date(2027, 3, 1)
    dates = pillar_dates(ref, horizon)
    assert dates[0] == ref
    assert dates[-1] == horizon


def test_pillar_dates_never_exceed_horizon():
    ref = date(2026, 8, 28)
    horizon = date(2026, 10, 1)  # short horizon, well inside most pillar tenors
    dates = pillar_dates(ref, horizon)
    assert all(d <= horizon for d in dates)


def test_trs_event_dates_match_its_own_reset_schedule():
    trade = _FakeTRS(start_date=date(2026, 1, 15), end_date=date(2027, 1, 15), reset_m=3)
    events = trade_event_dates(trade)
    # quarterly resets from a 1y trade: start, +3m, +6m, +9m, end -> 5 dates
    assert date(2026, 1, 15) in events
    assert date(2026, 4, 15) in events
    assert date(2027, 1, 15) in events
    assert len(events) == 5


def test_forward_event_date_is_just_its_settlement_date():
    trade = _FakeForward(forward_date=date(2026, 12, 6))
    assert trade_event_dates(trade) == [date(2026, 12, 6)]


def test_build_time_grid_forces_trade_event_dates_onto_the_grid():
    """The core guarantee: a trade's real maturity date must appear EXACTLY
    in the grid, not be approximated by the nearest pillar/monthly point."""
    ref = date(2026, 8, 28)
    odd_maturity = date(2026, 10, 14)  # deliberately not a round pillar date
    trades = {"t1": _FakeTRS(start_date=ref, end_date=odd_maturity, reset_m=0)}

    for mode in ("pillar", "monthly"):
        dates, times, node_map = build_time_grid(ref, trades, grid_mode=mode)
        assert odd_maturity in dates, f"grid_mode={mode} lost the trade's own maturity date"


def test_build_time_grid_can_disable_event_dates_for_comparison():
    # Two trades: the SHORTER one's maturity is an "interior" date (not the
    # horizon itself, which pillar_dates() always includes regardless of
    # include_trade_event_dates -- using it here would test the wrong thing).
    ref = date(2026, 8, 28)
    odd_interior_maturity = date(2026, 10, 14)
    horizon_maturity = date(2028, 1, 15)
    trades = {
        "t1": _FakeTRS(start_date=ref, end_date=odd_interior_maturity, reset_m=0),
        "t2": _FakeTRS(start_date=ref, end_date=horizon_maturity, reset_m=0),
    }
    dates, times, _ = build_time_grid(ref, trades, grid_mode="pillar", include_trade_event_dates=False)
    # without forcing event dates, the interior maturity is not guaranteed present
    # (it may or may not coincide with a pillar by chance; here it does not)
    assert odd_interior_maturity not in dates

    dates_with_events, _, _ = build_time_grid(ref, trades, grid_mode="pillar", include_trade_event_dates=True)
    assert odd_interior_maturity in dates_with_events, "enabling event dates should force it back in"


def test_pillar_grid_is_at_least_as_efficient_as_monthly_for_a_short_book():
    """Not a strict requirement in general, but for our actual ~1.5y book
    the pillar grid should not need MORE nodes than plain monthly (dense
    near-term pillars roughly match monthly spacing there; sparse far-term
    pillars save nodes where the book runs past 1-2 years)."""
    ref = date(2026, 8, 28)
    trades = {
        "eq": _FakeTRS(start_date=ref, end_date=date(2026, 11, 2), reset_m=1),
        "bond": _FakeTRS(start_date=ref, end_date=date(2028, 1, 15), reset_m=3),
    }
    pillar_n = len(build_time_grid(ref, trades, grid_mode="pillar")[0])
    monthly_n = len(build_time_grid(ref, trades, grid_mode="monthly")[0])
    assert pillar_n <= monthly_n * 1.2, (
        f"pillar grid ({pillar_n} nodes) unexpectedly much larger than monthly ({monthly_n})")
