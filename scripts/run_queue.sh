#!/bin/bash
# Heavy re-runs on the corrected engine, in order of importance. Each step logs to data/processed/report/queue_<step>.log
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/src;$PWD"
L=data/processed/report
run() { name=$1; shift; echo "$(date) start $name" >> $L/queue_status.log; "$@" > $L/queue_$name.log 2>&1; echo "$(date) done $name (exit $?)" >> $L/queue_status.log; }
run spec        python scripts/run_spec_simulation.py --scenarios 5000
run xva         python scripts/run_xva.py
run reportdata  python scripts/generate_report_data.py --scenarios 3000
run greeks      python scripts/run_greeks.py --scenarios 1000 --crn-n 300 --crn-repeats 3
run sacva       python scripts/run_sa_cva.py --scenarios 1000
run v_nojpy     python scripts/run_spec_simulation.py --scenarios 2000 --variant no_jpy
run v_flat      python scripts/run_spec_simulation.py --scenarios 2000 --variant no_jpy_flat
run v_sofr      python scripts/run_spec_simulation.py --scenarios 2000 --variant no_jpy_flat_sofr
