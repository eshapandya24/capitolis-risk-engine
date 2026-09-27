#!/bin/bash
cd "/c/Users/ESHA/OneDrive/Documents/UCB MFE/Capitolis"
export PYTHONPATH="C:/Users/ESHA/OneDrive/Documents/UCB MFE/Capitolis/src;C:/Users/ESHA/OneDrive/Documents/UCB MFE/Capitolis;C:/Users/ESHA/OneDrive/Documents/UCB MFE/Capitolis/scripts"
python scripts/run_greeks_sampling.py --n 256 --repeats 6 > data/processed/greeks_sampling_eq.log 2>&1; rc=$?; echo "eq/fx rc=$rc"
python scripts/run_greeks_sampling.py --n 256 --repeats 4 --rates --methods pseudo_random,latin_hypercube --out data/processed/greeks_sampling_rates.json > data/processed/greeks_sampling_rates.log 2>&1; rc=$?; echo "rates rc=$rc"
