#!/bin/bash
cd "$(dirname "$0")/.."
export PYTHONPATH="C:/Users/ESHA/OneDrive/Documents/UCB MFE/Capitolis/src;C:/Users/ESHA/OneDrive/Documents/UCB MFE/Capitolis"
L=data/processed/report
until grep -q "ALL DONE 6" $L/queue_status.log 2>/dev/null; do sleep 30; done
echo "$(date) start pathwise2" >> $L/queue_status.log
python scripts/validate_pathwise.py > $L/queue_pathwise2.log 2>&1
echo "$(date) done pathwise2 (exit $?)" >> $L/queue_status.log
echo "$(date) ALL DONE 7" >> $L/queue_status.log
