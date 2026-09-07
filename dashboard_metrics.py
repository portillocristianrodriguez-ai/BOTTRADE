"""Pure read-only metrics from broker positions and executions."""
import math


def number(value, default=None):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (ValueError, TypeError):
        return default


def active_positions(positions):
    return [p for p in positions if number(p.get("qty"), 0) != 0]


def flatten_orders(orders):
    result, seen = [], set()
    def visit(order):
        key = order.get("id") or id(order)
        if key in seen:
            return
        seen.add(key)
        result.append(order)
        for leg in order.get("legs") or []:
            visit(leg)
    for order in orders:
        visit(order)
    return result


def stop_risk(positions, orders, complete=True):
    """Estimated loss from current marks to stop prices, excluding slippage.

    Stop-limit orders do not guarantee an exit. Missing/partial protection
    leaves the portfolio total unknown, while covered loss stays visible.
    Overlapping stops are capped at position quantity, worst price first.
    """
    loss, uncovered = 0.0, []
    for p in positions:
        qty = abs(number(p.get("qty"), 0))
        mark = number(p.get("current_price"))
        short = str(p.get("side", "")).lower() == "short" or number(p.get("qty"), 0) < 0
        remaining = qty
        stops = []
        for o in flatten_orders(orders):
            if str(o.get("symbol", "")).replace("/", "") != str(p.get("symbol", "")).replace("/", ""):
                continue
            if o.get("side") != ("buy" if short else "sell") or o.get("type") not in {"stop", "stop_limit", "trailing_stop"}:
                continue
            if o.get("status") not in {"new", "accepted", "partially_filled"}:
                continue
            stop = number(o.get("stop_price"))
            available = number(o.get("qty"), 0) - number(o.get("filled_qty"), 0)
            if stop is not None and stop > 0 and available > 0:
                stops.append((stop, available))
        if mark is not None and mark > 0:
            for stop, available in sorted(stops, reverse=short):
                covered = min(remaining, available)
                loss += covered * max(0, stop - mark if short else mark - stop)
                remaining -= covered
                if remaining <= qty * 1e-12:
                    break
        if remaining > qty * 1e-12:
            uncovered.append(p.get("symbol"))
    return {"max_loss_if_all_stops_hit": loss if complete and not uncovered else None,
            "covered_stop_loss": loss, "uncovered_symbols": uncovered,
            "stop_risk_status": "estimated" if complete and not uncovered else "incomplete",
            "stop_risk_note": "Estimación desde precio actual; sin deslizamiento. Stop-limit no garantiza ejecución."}
