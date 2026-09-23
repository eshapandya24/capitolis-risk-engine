"""DVA / FVA formulas against closed-form values (no network)."""
import numpy as np
import pytest

from risk_engine.exposure import spec_exposure as spec
from risk_engine.exposure.cva import cva
from risk_engine.exposure.xva import dva, funding_cost, xva_summary
from risk_engine.models.credit import LGD

T = np.linspace(0.0, 5.0, 11)
FLAT = (np.array([1.0, 10.0]), np.array([0.02, 0.02]))


def test_flat_exposure_dva_matches_the_credit_triangle():
    """ENE = 1 flat, spread s: DVA = LGD * ENE * (1 - Q(T)), Q = exp(-s T / LGD)."""
    dene = np.ones_like(T)
    got = dva(dene, T, *FLAT)
    assert got == pytest.approx(LGD * (1.0 - np.exp(-0.02 * 5.0 / LGD)), rel=1e-9)


def test_dva_and_cva_are_mirror_images():
    ee = np.linspace(2.0, 0.0, len(T))
    assert dva(ee, T, *FLAT) == pytest.approx(cva(ee, T, *FLAT))


def test_funding_cost_of_constant_exposure_is_spread_times_exposure_times_time():
    assert funding_cost(np.full_like(T, 3.0), T, *FLAT) == pytest.approx(0.02 * 3.0 * 5.0)


def test_fva_is_spread_times_discounted_mean_value():
    epe, ene = np.full_like(T, 4.0), np.full_like(T, 1.5)
    s = xva_summary(epe, ene, T, FLAT, FLAT)
    assert s["FVA"] == pytest.approx(0.02 * (4.0 - 1.5) * 5.0)
    assert s["total"] == pytest.approx(s["CVA"] - s["DVA"] + s["FVA"])
    assert s["total_no_overlap"] == pytest.approx(s["CVA"] - s["DVA"] + s["FCA"])


def test_zero_negative_exposure_means_no_dva_or_funding_benefit():
    s = xva_summary(np.ones_like(T), np.zeros_like(T), T, FLAT, FLAT)
    assert s["DVA"] == 0.0 and s["FBA"] == 0.0 and s["bilateral_CVA"] == s["CVA"]


def test_negative_side_closeout_exposure_is_the_mirror_of_the_positive_side():
    nm = {0: {"reporting": 1, "lookahead": 2, "prev": 0}}
    net = np.array([[100.0, 100.0], [100.0, 100.0], [130.0, 60.0]])
    pos = spec.window_exposure(net, nm, {0: 0}, side="pos")
    neg = spec.window_exposure(net, nm, {0: 0}, side="neg")
    assert list(pos[0]) == [30.0, 0.0] and list(neg[0]) == [0.0, 40.0]
