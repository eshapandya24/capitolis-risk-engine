#!/bin/bash
# Analyses that need the finished runs, then the clean Greeks timing on an idle machine.
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/src;$PWD"
L=data/processed/report
until grep -q "done pathwise" $L/queue_status.log 2>/dev/null; do sleep 60; done
run() { name=$1; shift; echo "$(date) start $name" >> $L/queue_status.log; "$@" > $L/queue_$name.log 2>&1; echo "$(date) done $name (exit $?)" >> $L/queue_status.log; }
run additivity  python scripts/analyze_additivity.py
run timegreeks  python scripts/time_greeks.py
