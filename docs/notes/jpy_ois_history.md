# JPY OIS par-rate history (data/raw/sources/JPY.xlsx)

A Bloomberg export provided by the project team: the overnight call rate
(`MUTKCALM Index`) and 35 JPY OIS par-rate tenors (`JYSO*`, 1 week to 40
years), daily, 2011-10-05 to 2026-09-18 (3,903 business days). It replaces
the earlier one-day Bloomberg snapshot as the primary JPY source.
`data/raw/sources/jpy_ois_history.csv` is the parsed copy. Licensed data:
gitignored, and only derived numbers appear in the report.

Ticker suffixes: `1Z/2Z/3Z` = 1-3 weeks, `A..K` = 1-11 months, `1` = 1 year,
`1C/1F/1I` = 15/18/21 months, then whole years 2-12, 15, 20, 25, 30, 35, 40.

## What it is used for (market/jpy_ois.py)

- **JPY zero curve**: OIS par rates bootstrapped to discount factors (one
  payment to 1y, annual fixed payments beyond, par rates interpolated on an
  annual grid). Validated against Bloomberg's own JPY zero curve on
  2026-08-31: within 1bp at 1, 2, 5, 10, 20 and 30 years.
- **JPY rate volatility**: overnight call-rate vol over the trailing 3 years
  (0.267%; the Bank of Japan TONA series gives 0.276%).
- **JPY-USD rate differential**: 1y zero rate of our USD curve minus the JPY
  OIS zero rate on the same date (2.59%, was 2.64% mixing dates).
- **Mean reversion test**: realised par-rate vol by tenor for 1,2,3,5,7,10,
  15,20,30y.

## Finding

JPY OIS vol RISES with tenor in every window (1y to 15y, and since the end
of negative rates in March 2024): 1y tenor about 20bp/yr against 30y about
54bp/yr over three years. The exp(-a*tenor) fit gives a negative `a`
(-0.017 to -0.029), and one factor (the level) explains about 84% of daily
curve changes. A single mean-reverting Gaussian factor cannot represent it, so
the JPY Hull-White factor uses the lowest admissible value a = 0.001
(`JPY_MEAN_REVERSION_FLOOR`, the Ho-Lee limit). This is the third independent
confirmation, after the JPY swaption cube and the JGB yield history.

The history also shows the whole negative-rate era: the call rate was
negative on 2,100+ days and par rates out to 5 years were negative at times
(minimum -0.373%).
