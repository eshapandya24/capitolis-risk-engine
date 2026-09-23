#!/bin/bash
# Stress test, additional model-risk variants, PCA study, risky-bond sample and pathwise validation;
# starts after run_queue2.sh has finished.
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/src;$PWD"
L=data/processed/report
until grep -q "done corr_up" $L/queue_status.log 2>/dev/null; do sleep 60; done
run() { name=$1; shift; echo "$(date) start $name" >> $L/queue_status.log; "$@" > $L/queue_$name.log 2>&1; echo "$(date) done $name (exit $?)" >> $L/queue_status.log; }
run stress      python scripts/run_stress.py --scenarios 1000
run eqvol_x2    python scripts/run_spec_simulation.py --scenarios 2000 --variant eqvol_x2
run rate_flight python scripts/run_spec_simulation.py --scenarios 2000 --variant rate_eq_flight
run rate_toget  python scripts/run_spec_simulation.py --scenarios 2000 --variant rate_eq_together
run pca         python scripts/run_pca_study.py
run risky       python scripts/run_risky_bond_sample.py
run pathwise    python scripts/validate_pathwise.py
