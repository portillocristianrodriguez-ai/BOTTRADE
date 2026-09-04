"""
Análisis histórico de operaciones de BOTTRADE.

IMPORTANTE:
- Este módulo es deliberadamente de solo lectura.
- No envía, cancela ni modifica órdenes.
- No cambia señales, tamaños, SL/TP ni ninguna decisión del bot.
- Recibe órdenes ya cerradas de Alpaca y reconstruye ciclos BUY -> SELL.

Se excluyen las órdenes SELL que sean claramente protecciones OCO/bracket,
para evitar contar SL/TP como operaciones independientes.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, asdict
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
    """Detecta SELLs que representan protección, no una salida estratégica."""
    if "sell" not in _text(order, "side"):
        return False

    order_class = _text(order, "order_class")
    if "oco" in order_class or "bracket" in order_class:
        return True

    order_type = _text(order, "type")
    if "stop" in order_type:
        return True

    # Algunas representaciones de Alpaca exponen la protección en legs.
    legs = getattr(order, "legs", None) or []
    for leg in legs:
        leg_type = str(getattr(leg, "type", "") or "").lower()
        if "stop" in leg_type:
            return True

    return False


def _symbol(order: Any) -> str:
    return str(getattr(order, "symbol", "") or "").upper()


def _time(order: Any) -> str | None:
    for field in ("filled_at", "submitted_at", "created_at"):
        value = getattr(order, field, None)
        if value is not None:
            return str(value)
    return None


def reconstruct_trades(orders: Iterable[Any]) -> list[Trade]:
    """Reconstruye trades cerrados mediante FIFO a partir de órdenes filled.

    Cada BUY crea inventario de entrada. Cada SELL consume ese inventario.
    Las ventas que parecen SL/TP/OCO/bracket se ignoran para no duplicar
    operaciones de protección. Esto es un análisis, no ejecución.
    """
    buys: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
    trades: list[Trade] = []

    normalized = []
    for order in orders:
        if not _is_filled(order):
            continue
        symbol = _symbol(order)
        qty = _float(order, "filled_qty")
        price = _float(order, "filled_avg_price")
        if not symbol or qty <= 0 or price <= 0:
            continue
        normalized.append(order)

    # Alpaca devuelve normalmente las más recientes primero; ordenar por fecha
    # si es posible mejora la reconstrucción FIFO sin depender del orden API.
    def sort_key(order: Any) -> str:
        return _time(order) or ""

    normalized.sort(key=sort_key)

    unmatched_sells = 0.0

    for order in normalized:
        symbol = _symbol(order)
        side = _text(order, "side")
        qty_remaining = _float(order, "filled_qty")
        price = _float(order, "filled_avg_price")
        order_id = str(getattr(order, "id", "") or "")
        order_time = _time(order)

        if "buy" in side:
            buys[symbol].append(
                {
                    "qty": qty_remaining,
                    "price": price,
                    "order_id": order_id,
                    "time": order_time,
                }
            )
            continue

        if "sell" not in side or _is_protection_sell(order):
            continue

        while qty_remaining > 1e-12 and buys[symbol]:
            entry = buys[symbol][0]
            matched_qty = min(qty_remaining, entry["qty"])
            pnl = matched_qty * (price - entry["price"])
            cost = matched_qty * entry["price"]
            pnl_pct = (pnl / cost * 100.0) if cost else 0.0

            trades.append(
                Trade(
                    symbol=symbol,
                    qty=matched_qty,
                    entry_price=entry["price"],
                    exit_price=price,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    entry_order_id=entry["order_id"],
                    exit_order_id=order_id,
                    entry_time=entry["time"],
                    exit_time=order_time,
                )
            )

            entry["qty"] -= matched_qty
            qty_remaining -= matched_qty
            if entry["qty"] <= 1e-12:
                buys[symbol].popleft()

        unmatched_sells += max(qty_remaining, 0.0)

    return trades


def calculate_metrics(trades: Iterable[Trade]) -> dict[str, float | int]:
    """Calcula métricas sobre trades ya reconstruidos."""
    items = list(trades)
    pnls = [trade.pnl for trade in items]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    net_profit = sum(pnls)

    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)

    profit_factor = (
        gross_profit / gross_loss if gross_loss > 0 else float("inf")
    )
    win_rate = len(wins) / len(items) * 100.0 if items else 0.0
    expectancy = net_profit / len(items) if items else 0.0

    return {
        "trades": len(items),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": win_rate,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "net_profit_before_fees": net_profit,
        "profit_factor": profit_factor,
        "expectancy_per_trade": expectancy,
        "max_drawdown": max_drawdown,
    }


def analyze_orders(orders: Iterable[Any]) -> dict[str, Any]:
    """Punto de entrada para un informe read-only."""
    trades = reconstruct_trades(orders)
    metrics = calculate_metrics(trades)
    return {
        "metrics": metrics,
        "trades": [asdict(trade) for trade in trades],
    }
