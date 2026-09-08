# MPOR-shifted exposure

Answers a direct question: was the engine using a 10-day MPOR (Margin
Period of Risk)? No — the production engine (`scripts/run_simulation.py`)
computes plain exposure at each reporting date, which is the *correct*
calculation for an **uncollateralized** counterparty (no periodic margining
process for a close-out delay to apply to). Since `trade_data/` carries no
CSA/margin terms for any of the 16 trades, the book is treated as
uncollateralized, and the production numbers are unaffected by this work.

This adds the MPOR-shifted (collateralized) calculation as a real,
tested, working capability — ready the moment actual CSA terms are known
for any counterparty — and demonstrates it against a hypothetical CSA so
it isn't just a theoretical stub.

## What MPOR is, and the formula used

For a margined counterparty, default doesn't mean instant close-out —
there's a real delay (industry standard **10 business days**, ISDA
SIMM/Basel) between the last collateral exchange and actually replacing
the position. During that window the market can move further against you,
beyond what's already collateralized.

At a reporting date `t`, using a look-ahead date `t+MPOR` on the **same**
simulated path (not a separate simulation):

```
C(t)            = max(V(t) - threshold, 0)      # collateral held at t
Exposure(t)     = max(V(t+MPOR) - C(t), 0)       # what's owed at the delayed
                                                   # close-out date, net of
                                                   # what's already collateralized
```

`threshold=0` (full variation margin) isolates the pure MPOR effect: every
dollar of today's MTM is already collateralized, so the remaining exposure
is purely the potential *move* over the 10-day window — not the whole
notional-driven MTM. `threshold=∞` recovers "never collateralized."

## Implementation

- `simulation/engine.py`'s `build_time_grid(mpor_days=...)` inserts an
  extra look-ahead node exactly `mpor_days` after every monthly reporting
  node, sharing the same simulated path — no separate simulation, no
  engine changes needed beyond the time grid (the engine already handles
  arbitrary non-uniform node spacing).
- `exposure/collateral.py` implements the formula above, netted by
  counterparty, and a side-by-side comparison against the plain
  (uncollateralized) calculation for the same paths.
- 4 tests (`tests/test_mpor.py`, no network needed): the look-ahead date is
  exactly `mpor_days` later; the last reporting node correctly has no
  look-ahead past the horizon; the formula matches a hand-calculation at
  three threshold values; exposure never goes negative on a value drop.

## Hypothetical demonstration (N=1,000, MPOR=10 days, threshold=$0)

**Explicitly illustrative — the real book has no CSA, this is "if one
existed":**

| Counterparty | Uncollateralized MPE | MPOR-shifted MPE (full VM) | Reduction |
|---|---|---|---|
| CPTY_A | $27.1M | $13.8M | 49.0% |
| CPTY_B | $11.2M | $4.7M | 58.0% |
| CPTY_C | $125.7M | $10.2M | **91.9%** |

**CPTY_C's number is the clearest illustration of why margining matters**:
its uncollateralized exposure is dominated almost entirely by one $500M
bond forward (`BF_0003`) — under a hypothetical full-VM CSA, that huge
notional-driven MTM gets collateralized away almost entirely, leaving only
the (much smaller) risk of the market moving further within a 10-day
window. This is exactly the mechanism CSAs exist to address.

## Run it

```bash
python scripts/run_mpor_comparison.py --scenarios 1000 --mpor-days 10 --threshold 0
```

## Open item

Whether any of the 16 trades are actually margined, and under what CSA
terms (threshold, MTA), is something only Capitolis's actual margin
agreements can answer — nothing in `trade_data/` indicates this either
way. Worth asking directly rather than assuming either uncollateralized or
collateralized.
