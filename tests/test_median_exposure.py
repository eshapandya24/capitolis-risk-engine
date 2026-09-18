import numpy as np
from risk_engine.exposure.aggregate import median_exposure, expected_exposure, build_profiles


def test_median_is_50th_percentile_and_below_mean_for_right_skew():
    rng = np.random.default_rng(0)
    arr = np.maximum(rng.lognormal(0, 1, size=(3, 5000)) - 1.0, 0.0)
    med = median_exposure(arr)
    assert np.allclose(med, np.quantile(arr, 0.5, axis=1))
    assert (med < expected_exposure(arr)).all()


def test_build_profiles_includes_median_exposure():
    npv = np.random.default_rng(1).normal(size=(2, 4, 300))
    prof = build_profiles(["a", "b"], {"a": "C", "b": "C"}, npv, list(range(4)), confidence=0.99)
    for key in ("C", "__portfolio__"):
        assert prof[key]["MedianExposure"].shape == (4,)
        assert (prof[key]["MedianExposure"] <= prof[key]["PFE"] + 1e-12).all()
