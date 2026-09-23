p = "src/risk_engine/simulation/engine.py"
s = open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert a in s, a[:70]
    s = s.replace(a, b, 1)


rep('''        self.calib = calib
        self.trades = trades
        self.method = method''', '''        self.calib = calib
        self.trades = trades
        # {issuer: (tenors_years, spreads, recovery)}: issuer credit for RISKY bonds (extra credit).
        # Spreads are held deterministic: at every node the issuer curve is re-anchored at the node
        # date with the same spread term structure (a constant-spread scenario), disclosed in the report.
        self.issuer_spreads = calib.get("issuer_spreads") or {}
        self.method = method''')
rep('''            market = MarketState(
                ref_date=node_date, reporting_ccy="USD",
                discount_curves=curves,''', '''            credit = ({iss: CreditCurve(node_date, tn, sp, rec) for iss, (tn, sp, rec) in self.issuer_spreads.items()}
                      if self.issuer_spreads else {})
            market = MarketState(
                ref_date=node_date, reporting_ccy="USD",
                discount_curves=curves,
                credit_curves=credit,''')
rep("from capitolis_pricers.curves import FxCurve\n", "from capitolis_pricers.curves import FxCurve\nfrom capitolis_pricers.credit import CreditCurve\n")
open(p, "w", encoding="utf-8").write(s)
print("credit patched")
