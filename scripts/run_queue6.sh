#!/bin/bash
# Re-run the four attribution runs that failed on a local-import bug, after queue 5 has finished.
cd "$(dirname "$0")/.."
export PYTHONPATH="C:/Users/ESHA/OneDrive/Documents/UCB MFE/Capitolis/src;C:/Users/ESHA/OneDrive/Documents/UCB MFE/Capitolis"
L=data/processed/report
until grep -q "ALL DONE" $L/queue_status.log 2>/dev/null; do sleep 60; done
run() { name=$1; shift; echo "$(date) start $name" >> $L/queue_status.log; "$@" > $L/queue_$name.log 2>&1; rc=$?; echo "$(date) done $name (exit $rc)" >> $L/queue_status.log; }
run f2000      python scripts/run_spec_simulation.py --scenarios 2000 --outdir data/processed/spec_run_final2000
run v_nojpy    python scripts/run_spec_simulation.py --scenarios 2000 --variant no_jpy
run v_flat     python scripts/run_spec_simulation.py --scenarios 2000 --variant no_jpy_flat
run v_sofr     python scripts/run_spec_simulation.py --scenarios 2000 --variant no_jpy_flat_sofr
echo "$(date) ALL DONE 6" >> $L/queue_status.log
