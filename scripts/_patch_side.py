p = "src/risk_engine/exposure/spec_exposure.py"
s = open(p, encoding="utf-8").read()


def rep(a, b, count=1):
    global s
    assert a in s, a[:70]
    s = s.replace(a, b, count)


rep('def window_exposure(net_npv, node_map, prev_node=None):',
    'def window_exposure(net_npv, node_map, prev_node=None, side="pos"):')
rep('''    Returns (n_reporting, n_scenarios).
    """
    n_reporting = len(node_map)''', '''    side: "pos" (default) is the exposure to the counterparty,
    max(V(t+10bd) - VM, 0); "neg" is the mirror image, the counterparty's
    exposure to us, max(VM - V(t+10bd), 0), used for DVA and funding benefit.

    Returns (n_reporting, n_scenarios).
    """
    n_reporting = len(node_map)''')
rep('''        out[i, :] = np.maximum(v_close_out - vm, 0.0)
    return out''', '''        move = v_close_out - vm
        out[i, :] = np.maximum(move if side == "pos" else -move, 0.0)
    return out''')
rep('''def exposure_by_counterparty(trade_ids, trade_counterparty, npv, node_map,
                              prev_node=None, trade_expiry=None,
                              exclude_maturing=False, dates=None):''', '''def exposure_by_counterparty(trade_ids, trade_counterparty, npv, node_map,
                              prev_node=None, trade_expiry=None,
                              exclude_maturing=False, dates=None, side="pos"):''')
rep('''            out[cpty] = window_exposure(_net_npv(npv, idx), node_map, prev_node)
            continue''', '''            out[cpty] = window_exposure(_net_npv(npv, idx), node_map, prev_node, side)
            continue''')
rep('''            exposure[i, :] = window_exposure(_net_npv(npv, live), single, None
                                              if prev_node is None else {0: prev_node[i]})[0, :]''', '''            exposure[i, :] = window_exposure(_net_npv(npv, live), single, None
                                              if prev_node is None else {0: prev_node[i]}, side)[0, :]''')
open(p, "w", encoding="utf-8").write(s)
print("side ok")
