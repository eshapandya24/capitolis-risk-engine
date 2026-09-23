#!/bin/bash
# Model-risk and rates-model comparison runs; starts after run_queue.sh has finished.
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/src;$PWD"
L=data/processed/report
until grep -q "done v_sofr" $L/queue_status.log 2>/dev/null; do sleep 60; done
run() { name=$1; shift; echo "$(date) start $name" >> $L/queue_status.log; "$@" > $L/queue_$name.log 2>&1; echo "$(date) done $name (exit $?)" >> $L/queue_status.log; }
run f2000       python scripts/run_spec_simulation.py --scenarios 2000 --outdir data/processed/spec_run_final2000
run g2          python scripts/run_spec_simulation.py --scenarios 2000 --variant g2
run eqvol_up    python scripts/run_spec_simulation.py --scenarios 2000 --variant eqvol_up
run ratevol_up  python scripts/run_spec_simulation.py --scenarios 2000 --variant ratevol_up
run a_x3        python scripts/run_spec_simulation.py --scenarios 2000 --variant a_x3
run corr_up     python scripts/run_spec_simulation.py --scenarios 2000 --variant corr_up
