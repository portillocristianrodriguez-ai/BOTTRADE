"""
Análisis histórico de operaciones de BOTTRADE.

Solo lectura: no envía, cancela ni modifica órdenes.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Iterable


@dataclass
class Trade:
    symbol: str
    qty: float
    entry_price: float
    exit_price: float
    pnl: float
    pnl_pct: float
    entry_order_id: str
    exit_order_id: str
    entry_time: str | None = None
    exit_time: str | None = None


def _text(order: Any, field: str) -> str:
    return str(getattr(order, field, "") or "").lower()


def _float(order: Any, field: str) -> float:
    try:
        return float(getattr(order, field, 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _is_filled(order: Any) -> bool:
    return "filled" in _text(order, "status")


def _is_protection_sell(order: Any) -> bool:
    if "sell" not in _text(order, "side"):
        return False
    order_class = _text(order, "order_class")
    if "oco" in order_class or "bracket" in order_class:
        return True
    if "stop" in _text(order, "type"):
        return True
    for leg in getattr(order, "legs", None) or []:
        if "stop" in str(getattr(leg, "type", "") or "").lower():
            return True
    return False


def _symbol(order: Any) -> str:
    return str(getattr(order, "symbol", "") or "").upper().strip()


def _time(order: Any) -> str | None:
    for field in ("filled_at", "submitted_at", "created_at"):
        value = getattr(order, field, None)
        if value is not None:
            return str(value)
    return None


def _time_key(order: Any) -> tuple[int, str]:
    value = _time(order)
    if not value:
        return (1, "")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return (0, parsed.isoformat())
    except ValueError:
        return (0, value)


def reconstruct_trades(orders: Iterable[Any]) -> list[Trade]:
    """Reconstruye BUY -> SELL por FIFO sin modificar la cuenta."""
    buys: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
    trades: list[Trade] = []

    normalized = []
    for order in orders:
        if not _is_filled(order):
            continue
        symbol = _symbol(order)
        qty = _float(order, "filled_qty")
        price = _float(order, "filled_avg_price")
        if symbol and qty > 0 and price > 0:
            normalized.append(order)

    normalized.sort(key=_time_key)

    for order in normalized:
        symbol = _symbol(order)
        side = _text(order, "side")
        qty_remaining = _float(order, "filled_qty")
        price = _float(order, "filled_avg_price")
        order_id = str(getattr(order, "id", "") or "")
        order_time = _time(order)

        if "buy" in side:
            buys[symbol].append({"qty": qty_remaining, "price": price,
                                 "order_id": order_id, "time": order_time})
            continue

        if "sell" not in side or _is_protection_sell(order):
            continue

        while qty_remaining > 1e-12 and buys[symbol]:
            entry = buys[symbol][0]
            matched_qty = min(qty_remaining, entry["qty"])
            pnl = matched_qty * (price - entry["price"])
            cost = matched_qty * entry["price"]
            trades.append(Trade(
                symbol=symbol,
                qty=matched_qty,
                entry_price=entry["price"],
                exit_price=price,
                pnl=pnl,
                pnl_pct=(pnl / cost * 100.0) if cost else 0.0,
                entry_order_id=entry["order_id"],
                exit_order_id=order_id,
                entry_time=entry["time"],
                exit_time=order_time,
            ))
            entry["qty"] -= matched_qty
            qty_remaining -= matched_qty
            if entry["qty"] <= 1e-12:
                buys[symbol].popleft()

    return trades


def calculate_metrics(trades: Iterable[Trade]) -> dict[str, float | int]:
    items = list(trades)
    pnls = [trade.pnl for trade in items]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    net_profit = sum(pnls)
    equity = peak = max_drawdown = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return {
        "trades": len(items),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": len(wins) / len(items) * 100.0 if items else 0.0,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "net_profit_before_fees": net_profit,
        "profit_factor": gross_profit / gross_loss if gross_loss else float("inf"),
        "expectancy_per_trade": net_profit / len(items) if items else 0.0,
        "max_drawdown": max_drawdown,
    }


def analyze_orders(orders: Iterable[Any]) -> dict[str, Any]:
    trades = reconstruct_trades(orders)
    return {"metrics": calculate_metrics(trades),
            "trades": [asdict(trade) for trade in trades]}
