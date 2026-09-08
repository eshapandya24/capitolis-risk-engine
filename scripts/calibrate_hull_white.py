"""
Driver script for Hull-White mean-reversion calibration -- the actual
calibration logic lives in src/risk_engine/models/hw_calibration.py (used
directly by models/calibration.py's build_calibration()), so this script
and the production model build always agree; this just runs it standalone
and prints/saves a report.

See src/risk_engine/models/hw_calibration.py's module docstring for the
method (historical volatility term-structure fit) and its disclosed
approximation.

    python scripts/calibrate_hull_white.py
"""
import json
import os
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    from risk_engine.models.hw_calibration import calibrate_mean_reversion

    ref_date = date(2026, 8, 28)
    print(f"Fetching historical vol per contract (as of {ref_date})...\n")
    result = calibrate_mean_reversion(ref_date)

    for row in result["contracts"]:
        print(f"  {row['symbol']:8s} avg_tenor={row['avg_tenor']:.2f}y  "
              f"vol={row['vol']:.4%}  (n={row['n_obs']} obs)")

    print(f"\nFitted: a = {result['a']:.4f}, sigma (from fit, cross-check only) = "
          f"{result['sigma_from_fit']:.4%}, R^2 = {result['r_squared']:.3f}")
    print("(Previous assumption: a = 0.03, a disclosed textbook value)")
    if result["r_squared"] < 0.5:
        print("\nWARNING: R^2 is low -- the exponential-decay fit is weak; treat `a` cautiously.")

    out_path = os.path.join(ROOT, "data", "processed", "hull_white_calibration.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
