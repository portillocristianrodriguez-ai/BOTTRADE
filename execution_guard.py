"""Guardas explícitas para ejecución de órdenes de BOTTRADE.

Este módulo no toca el SDK de Alpaca globalmente. La capa de broker puede
usarlo justo antes de enviar una orden para:

- generar un client_order_id único por operación lógica;
- comprobar si ya existe una orden BUY abierta para el símbolo;
- calcular exposición actual + compras BUY abiertas;
- aplicar límites de posición individual y exposición total.

Diseñado para permanecer en PAPER mientras se valida el comportamiento.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from typing import Iterable


def normalizar_simbolo(symbol: str) -> str:
    return str(symbol or "").strip().upper().replace("/", "")


def crear_client_order_id(symbol: str, side: str, strategy: str = "MOM") -> str:
    """Crea un ID corto, único y trazable por operación."""
    simbolo = normalizar_simbolo(symbol)[:18] or "ORDER"
    lado = str(side or "NA").strip().upper()[:5]
    estrategia = str(strategy or "BOT").strip().upper()[:8]
    # UUID4 evita colisiones entre procesos; el hash añade trazabilidad sin
    # depender de una ventana temporal que pueda bloquear una orden legítima.
    nonce = uuid.uuid4().hex[:12]
    return f"BT-{estrategia}-{simbolo}-{lado}-{nonce}"


def fingerprint_orden(
    symbol: str,
    side: str,
    qty: float | str,
    order_type: str = "market",
) -> str:
    """Huella estable para logs/telemetría, no para reutilizar como ID."""
    payload = "|".join(
        (
            normalizar_simbolo(symbol),
            str(side or "").lower(),
            str(order_type or "").lower(),
            str(qty),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _float(value, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if result == result and result not in (float("inf"), float("-inf")) else default
    except (TypeError, ValueError):
        return default


def posicion_notional(position) -> float:
    """Obtiene el valor de mercado de una posición Alpaca de forma defensiva."""
    market_value = _float(getattr(position, "market_value", 0))
    if market_value > 0:
        return market_value

    qty = abs(_float(getattr(position, "qty", 0)))
    price = _float(getattr(position, "current_price", 0))
    return qty * price


def orden_buy_notional(order) -> float:
    """Estima el capital reservado por una BUY abierta."""
    notional = _float(getattr(order, "notional", 0))
    if notional > 0:
        return notional

    qty = abs(_float(getattr(order, "qty", 0)))
    price = _float(getattr(order, "limit_price", 0))
    return qty * price


def exposicion_actual(positions: Iterable) -> float:
    return sum(posicion_notional(p) for p in positions)


def compras_abiertas_notional(orders: Iterable) -> float:
    total = 0.0
    for order in orders:
        side = str(getattr(order, "side", "")).lower()
        if "buy" in side:
            total += orden_buy_notional(order)
    return total


def validar_exposicion_compra(
    *,
    equity: float,
    proposed_notional: float,
    positions: Iterable,
    open_orders: Iterable,
    max_single_position_pct: float,
    max_total_exposure_pct: float,
) -> tuple[bool, str]:
    """Aplica límites sobre exposición existente + órdenes BUY pendientes."""
    equity = _float(equity)
    proposed_notional = _float(proposed_notional)

    if equity <= 0 or proposed_notional <= 0:
        return False, "equity/notional inválido"

    max_single = equity * max(0.0, min(1.0, _float(max_single_position_pct)))
    max_total = equity * max(0.0, min(1.0, _float(max_total_exposure_pct)))

    if proposed_notional > max_single + 0.01:
        return False, f"notional ${proposed_notional:,.2f} > máximo individual ${max_single:,.2f}"

    existing = exposicion_actual(positions)
    pending = compras_abiertas_notional(open_orders)
    total_after = existing + pending + proposed_notional

    if total_after > max_total + 0.01:
        return False, (
            f"exposición futura ${total_after:,.2f} > máximo total ${max_total:,.2f} "
            f"(actual=${existing:,.2f}, pendientes=${pending:,.2f})"
        )

    return True, "OK"


def backoff_seconds(attempt: int, base: float = 0.5, maximum: float = 4.0) -> float:
    """Backoff pequeño para consultas de confirmación, nunca para reemitir órdenes."""
    attempt = max(0, int(attempt))
    return min(maximum, base * (2 ** attempt))


__all__ = [
    "normalizar_simbolo",
    "crear_client_order_id",
    "fingerprint_orden",
    "posicion_notional",
    "orden_buy_notional",
    "exposicion_actual",
    "compras_abiertas_notional",
    "validar_exposicion_compra",
    "backoff_seconds",
]
