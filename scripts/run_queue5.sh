#!/bin/bash
# All remaining heavy runs on the corrected engine, in order of importance. One step at a time.
# Each step logs to data/processed/report/queue_<name>.log; the status line carries the real exit code.
cd "$(dirname "$0")/.."
export PYTHONPATH="C:/Users/ESHA/OneDrive/Documents/UCB MFE/Capitolis/src;C:/Users/ESHA/OneDrive/Documents/UCB MFE/Capitolis"
L=data/processed/report
run() {
  name=$1; shift
  echo "$(date) start $name" >> $L/queue_status.log
  "$@" > $L/queue_$name.log 2>&1
  rc=$?
  echo "$(date) done $name (exit $rc)" >> $L/queue_status.log
}
run xva          python scripts/run_xva.py
run additivity   python scripts/analyze_additivity.py
run reportdata   python scripts/generate_report_data.py --scenarios 3000
run greeks       python scripts/run_greeks.py --scenarios 1000 --crn-n 300 --crn-repeats 3
run sacva        python scripts/run_sa_cva.py --scenarios 1000
run sacva_level  python scripts/run_sa_cva.py --scenarios 1000 --exposure level
run f2000        python scripts/run_spec_simulation.py --scenarios 2000 --outdir data/processed/spec_run_final2000
run v_nojpy      python scripts/run_spec_simulation.py --scenarios 2000 --variant no_jpy
run v_flat       python scripts/run_spec_simulation.py --scenarios 2000 --variant no_jpy_flat
run v_sofr       python scripts/run_spec_simulation.py --scenarios 2000 --variant no_jpy_flat_sofr
run stress       python scripts/run_stress.py --scenarios 1000
run pathwise     python scripts/validate_pathwise.py
run pca          python scripts/run_pca_study.py
run risky        python scripts/run_risky_bond_sample.py
run g2           python scripts/run_spec_simulation.py --scenarios 2000 --variant g2
run ratevol_up   python scripts/run_spec_simulation.py --scenarios 2000 --variant ratevol_up
run eqvol_up     python scripts/run_spec_simulation.py --scenarios 2000 --variant eqvol_up
run corr_up      python scripts/run_spec_simulation.py --scenarios 2000 --variant corr_up
run a_x3         python scripts/run_spec_simulation.py --scenarios 2000 --variant a_x3
run eqvol_x2     python scripts/run_spec_simulation.py --scenarios 2000 --variant eqvol_x2
run rate_flight  python scripts/run_spec_simulation.py --scenarios 2000 --variant rate_eq_flight
run rate_toget   python scripts/run_spec_simulation.py --scenarios 2000 --variant rate_eq_together
run martingale   python scripts/martingale_test.py
run timegreeks   python scripts/time_greeks.py
echo "$(date) ALL DONE" >> $L/queue_status.log
