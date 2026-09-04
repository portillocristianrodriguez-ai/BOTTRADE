"""Idempotencia y reconciliación segura de órdenes para BOTTRADE."""
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
    """Genera un ID estable para la misma operación dentro de una ventana."""
    symbol = str(ticker or "ORDER").upper().replace("/", "")
    bucket_size = max(1, int(operation_bucket_seconds))
    bucket = int(time.time() // bucket_size)
    raw = "|".join(
        (symbol, str(side or "buy").lower(), str(qty or ""), str(notional or ""), str(bucket))
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
    status = str(getattr(order, "status", "") or "").lower()
    return status in _RETRYABLE_FINAL_STATUSES


def estado_no_reintentable(order: Any) -> bool:
    if order is None:
        return False
    return not estado_reintentable(order)


def preparar_client_order_id(order_data: Any, operation_bucket_seconds: int = 300) -> str:
    """Asigna un client_order_id estable al objeto de orden y lo devuelve."""
    existente = getattr(order_data, "client_order_id", None)
    if existente:
        return str(existente)
    return crear_client_order_id(
        getattr(order_data, "symbol", "ORDER"),
        getattr(order_data, "side", "buy"),
        getattr(order_data, "qty", ""),
        getattr(order_data, "notional", ""),
        operation_bucket_seconds,
    )


def aplicar_client_order_id(order_data: Any, client_order_id: str):
    """Devuelve la orden con el ID aplicado, incluso si el modelo es inmutable."""
    try:
        order_data.client_order_id = client_order_id
        return order_data
    except Exception:
        dumped = order_data.model_dump()
        dumped["client_order_id"] = client_order_id
        return type(order_data)(**dumped)


def submit_order_idempotente(cliente: Any, order_data: Any):
    """Envía una orden sin duplicarla si el resultado del submit es incierto.

    Antes del envío se consulta el client_order_id. Si el submit lanza una
    excepción, se vuelve a consultar ese mismo ID antes de considerar fallido
    el intento. Así un timeout o error de red no provoca un reenvío ciego.
    """
    client_order_id = preparar_client_order_id(order_data)
    order_data = aplicar_client_order_id(order_data, client_order_id)

    existente = buscar_orden_por_client_id(cliente, client_order_id)
    if existente is not None and estado_no_reintentable(existente):
        return existente

    try:
        return cliente.submit_order(order_data=order_data)
    except Exception:
        reconciliada = buscar_orden_por_client_id(cliente, client_order_id)
        if reconciliada is not None and estado_no_reintentable(reconciliada):
            return reconciliada
        raise
