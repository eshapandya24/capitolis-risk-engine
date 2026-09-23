"""
SA-CCR exposure at default (Basel CRE52 / BCBS 279) for the uncollateralized
netting sets of the ESF book: a regulatory cross-check next to the Monte
Carlo exposure measures, and the EAD that feeds counterparty-credit-risk
capital.

    EAD        = alpha * (RC + PFE),  alpha = 1.4
    RC         = max(V - C, 0)                     replacement cost (C = 0: no CSA data)
    PFE        = multiplier * AddOn_aggregate
    multiplier = min(1, F + (1 - F) exp((V - C) / (2 (1 - F) AddOn)))  F = 5%

Only the asset classes present in the book are implemented:
  * Interest rate (bond forwards and bond TRS on US Treasuries): per trade
    the adjusted notional is notional * SD, SD = (exp(-0.05 S) - exp(-0.05 E))
    / 0.05 with S, E the start and end of the period the underlying bond's
    rate exposure covers (S = derivative expiry, E = bond maturity); trades in
    a currency form one hedging set, netted within three maturity buckets
    (E < 1y, 1-5y, > 5y) with correlations 1.4 / 1.4 / 0.6, supervisory factor
    0.5%.
  * Equity (equity TRS): each name is its own entity, supervisory factor 32%
    (single name), systematic/idiosyncratic aggregation with rho = 0.5.
No FX, credit or commodity trades exist. Unmargined maturity factor
sqrt(min(M, 1y)), M floored at 10 business days. Delta is +1 for a position
that gains when the primary risk factor rises (IR: short a bond; equity:
long the equity), -1 otherwise. Simplifications are stated where they occur
(no collateral, no CSA, single-name equity only).
"""
import math

import numpy as np

ALPHA = 1.4
FLOOR = 0.05
SF_IR = 0.005
SF_EQ_SINGLE = 0.32
RHO_EQ_SINGLE = 0.5
MIN_MATURITY = 10.0 / 250.0
IR_CORR = {(0, 1): 1.4, (1, 2): 1.4, (0, 2): 0.6}


def supervisory_duration(start, end):
    """SD = (exp(-0.05 S) - exp(-0.05 E)) / 0.05, S floored at 0."""
    s = max(start, 0.0)
    return (math.exp(-0.05 * s) - math.exp(-0.05 * end)) / 0.05


def maturity_factor(maturity):
    """Unmargined: sqrt(min(M, 1)); M floored at 10 business days."""
    return math.sqrt(min(max(maturity, MIN_MATURITY), 1.0))


def ir_bucket(end):
    return 0 if end < 1.0 else (1 if end <= 5.0 else 2)


def ir_addon(items):
    """items: dicts with currency, delta, notional, start, end, maturity.
    Returns (add-on, {currency: effective notional of the hedging set})."""
    by_ccy = {}
    for it in items:
        d = it["notional"] * supervisory_duration(it["start"], it["end"])
        eff = it["delta"] * d * maturity_factor(it["maturity"])
        b = by_ccy.setdefault(it["currency"], [0.0, 0.0, 0.0])
        b[ir_bucket(it["end"])] += eff
    en = {}
    for ccy, (d1, d2, d3) in by_ccy.items():
        en[ccy] = math.sqrt(max(d1 * d1 + d2 * d2 + d3 * d3 + 2 * 0.7 * d1 * d2 + 2 * 0.7 * d2 * d3 + 2 * 0.3 * d1 * d3, 0.0))
    return SF_IR * sum(en.values()), en


def equity_addon(items, sf=SF_EQ_SINGLE, rho=RHO_EQ_SINGLE):
    """items: dicts with entity, delta, notional (USD value of the position),
    maturity. Returns (add-on, {entity: add-on_k})."""
    eff = {}
    for it in items:
        eff[it["entity"]] = eff.get(it["entity"], 0.0) + it["delta"] * it["notional"] * maturity_factor(it["maturity"])
    add = {k: sf * v for k, v in eff.items()}
    a = np.array(list(add.values()), dtype=float)
    if a.size == 0:
        return 0.0, add
    return float(math.sqrt((rho * a.sum()) ** 2 + ((1.0 - rho ** 2) * a ** 2).sum())), add


def multiplier(v, addon):
    if addon <= 0:
        return 1.0
    return min(1.0, FLOOR + (1.0 - FLOOR) * math.exp(v / (2.0 * (1.0 - FLOOR) * addon)))


def ead(mtm, ir_items, eq_items):
    """EAD for one netting set. mtm = net value V (no collateral)."""
    a_ir, en = ir_addon(ir_items)
    a_eq, per_entity = equity_addon(eq_items)
    addon = a_ir + a_eq
    rc = max(mtm, 0.0)
    m = multiplier(mtm, addon)
    return {"V": mtm, "RC": rc, "addon_ir": a_ir, "addon_equity": a_eq, "addon": addon, "multiplier": m,
            "PFE": m * addon, "EAD": ALPHA * (rc + m * addon), "ir_effective_notional": en}


def build_items(trades, ref_date, equity_spots, fx_usdjpy, bond_of):
    """SA-CCR inputs per counterparty from the pricer trade objects.
    bond_of(trade) returns the underlying FixedRateBond. JPY names are valued
    in USD at spot / USDJPY. Returns {cpty: {"ir": [...], "eq": [...]}}."""
    from capitolis_pricers.daycount import to_date, year_fraction

    def yrs(d):
        return max(year_fraction(ref_date, to_date(d), "ACT/365F"), 0.0)

    out = {}
    for tid, t in trades.items():
        d = out.setdefault(t.counterparty, {"ir": [], "eq": []})
        if hasattr(t, "positions"):                      # equity TRS
            delta = 1.0 if t.direction == "receive_equity" else -1.0
            m = yrs(t.end_date)
            for p in t.positions:
                usd = p.shares * equity_spots[p.isin] / (fx_usdjpy if p.currency == "JPY" else 1.0)
                d["eq"].append({"entity": p.isin, "delta": delta, "notional": usd, "maturity": m, "trade": tid})
        elif hasattr(t, "forward_date"):                 # bond forward
            bond = bond_of(t)
            d["ir"].append({"currency": t.trade_currency, "delta": 1.0 if t.position == "short" else -1.0,
                            "notional": t.notional, "start": yrs(t.forward_date), "end": yrs(bond.maturity),
                            "maturity": yrs(t.forward_date), "trade": tid})
        else:                                            # bond TRS
            bond = bond_of(t)
            d["ir"].append({"currency": t.trade_currency, "delta": 1.0 if t.direction == "pay_tr" else -1.0,
                            "notional": t.notional, "start": yrs(t.end_date), "end": yrs(bond.maturity),
                            "maturity": yrs(t.end_date), "trade": tid})
    return out
