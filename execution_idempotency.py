"""Idempotencia y reconciliación segura de órdenes para BOTTRADE.

Este módulo no envía órdenes. Proporciona identidad determinista y helpers
para que la capa de ejecución pueda comprobar una orden existente antes de
reintentar una operación cuyo resultado sea incierto.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any


_RETRYABLE_FINAL_STATUSES = {
    "canceled",
    "cancelled",
    "rejected",
    "expired",
    "done_for_day",
}


def crear_client_order_id(
    ticker: str,
    side: str = "buy",
    qty: Any = "",
    notional: Any = "",
    operation_bucket_seconds: int = 300,
) -> str:
    """Genera un ID estable para la misma operación dentro de una ventana.

    El bucket evita que una señal legítimamente nueva reutilice el mismo ID
    indefinidamente, mientras que reintentos cercanos conservan la identidad.
    """
    symbol = str(ticker or "ORDER").upper().replace("/", "")
    bucket_size = max(1, int(operation_bucket_seconds))
    bucket = int(time.time() // bucket_size)
    raw = "|".join(
        (
            symbol,
            str(side or "buy").lower(),
            str(qty or ""),
            str(notional or ""),
            str(bucket),
        )
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    return f"BT-{symbol[:12]}-{digest}"


def buscar_orden_por_client_id(cliente: Any, client_order_id: str):
    """Devuelve una orden existente o None si no se puede localizar."""
    if cliente is None or not client_order_id:
        return None
    try:
        return cliente.get_order_by_client_id(client_order_id)
    except Exception:
        return None


def estado_reintentable(order: Any) -> bool:
    """Indica si el estado terminal permite considerar una nueva operación."""
    status = str(getattr(order, "status", "") or "").lower()
    return status in _RETRYABLE_FINAL_STATUSES


def estado_no_reintentable(order: Any) -> bool:
    """Indica si existe una orden activa o ya ejecutada que impide duplicar."""
    if order is None:
        return False
    status = str(getattr(order, "status", "") or "").lower()
    return status not in _RETRYABLE_FINAL_STATUSES
