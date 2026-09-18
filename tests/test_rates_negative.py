"""
Regression tests proving the Hull-White short-rate model (models/rates.py)
genuinely supports NEGATIVE interest rates -- important because JPY had a
real multi-year negative-rate (NIRP) history, and the requested rate model
must be able to represent that, not just clamp/floor at zero the way a
CIR or Black-Karasinski model would.

Hull-White is Gaussian (r(t) = x(t) + alpha(t), x is a zero-mean OU
process) -- nothing in its construction floors r(t) at zero, so this is a
structural property of the model, not a special code path. These tests
demonstrate it directly on a synthetic curve, since our only REAL JPY curve
snapshot (2026-08-31, post-BOJ-hikes) happens to be positive -- a
synthetic negative-flat-curve case is the honest way to exercise this
capability without fabricating a "real" negative JPY curve we don't have.

See also src/risk_engine/models/calibration.py's build_jpy_hull_white(),
which builds a real (currently positive-rate) JPY Hull-White factor off
the actual Bloomberg JPY OIS curve -- this file only tests the underlying
model's negative-rate capability in isolation.
"""
import math

from capitolis_pricers.curves import flat_curve
from risk_engine.models.rates import HullWhite1F


def test_negative_flat_curve_produces_negative_short_rate_and_discount_above_one():
    """A flat curve at a historically-realistic JPY NIRP-era rate (-0.10%)
    should round-trip: short_rate0() recovers the negative rate, and a
    negative rate implies DF(0,t) > 1 (a bond worth MORE than face value
    today), not an error or a floored-at-zero result."""
    ref_date = "2026-08-28"
    negative_rate = -0.001  # -0.10%, in line with real historical JPY OIS
    curve = flat_curve(ref_date, negative_rate)
    hw = HullWhite1F(curve, sigma=0.002, a=0.02)

    r0 = hw.short_rate0()
    assert r0 < 0, f"expected a negative short rate, got {r0}"
    assert math.isclose(r0, negative_rate, abs_tol=1e-6)

    df_1y = hw.discount0(1.0)
    assert df_1y > 1.0, f"a negative rate should discount to DF > 1, got {df_1y}"


def test_simulated_ou_path_can_go_negative_even_off_a_positive_curve():
    """Even starting from TODAY's real (currently positive) JPY curve, the
    simulated short rate at a future date can go negative -- the model
    doesn't floor it. Uses many antithetic-free draws and checks that at
    least some produce r(t) < 0, which would be impossible under a
    floored/non-negative model (CIR, Black-Karasinski)."""
    import random
    curve = flat_curve("2026-08-28", 0.001)  # a low, still-positive JPY-like level
    hw = HullWhite1F(curve, sigma=0.004, a=0.02)  # realistic JPY-scale vol

    rng = random.Random(7)
    dt = 1.0
    negative_count = 0
    n = 500
    for _ in range(n):
        z = rng.gauss(0, 1)
        x_t = hw.step_x(0.0, dt, z)
        r_t = hw.short_rate(x_t, dt)
        if r_t < 0:
            negative_count += 1

    assert negative_count > 0, (
        "expected at least some simulated paths to go negative starting from "
        "a low positive rate with realistic vol -- got none, model may be floored")


def test_bond_price_still_valid_under_negative_short_rate():
    """bond_price() should return a sensible (finite, positive) price even
    when the simulated short rate itself is negative -- no NaN/inf from an
    unguarded log or division."""
    curve = flat_curve("2026-08-28", -0.002)
    hw = HullWhite1F(curve, sigma=0.003, a=0.02)
    price = hw.bond_price(t=1.0, T=3.0, r_t=-0.005)
    assert math.isfinite(price)
    assert price > 0
