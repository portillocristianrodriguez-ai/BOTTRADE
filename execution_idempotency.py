"""Idempotencia y reconciliación segura de órdenes para BOTTRADE."""
from __future__ import annotations

import uuid
from typing import Any, Callable, Optional


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
    """Genera un ID único por objeto lógico de orden.

    El UUID evita reutilizar el mismo client_order_id para dos operaciones
    legítimas posteriores. Si un submit falla con resultado incierto, el mismo
    objeto de orden conserva el ID y puede reconciliarse sin reenviar a ciegas.
    """
    symbol = str(ticker or "ORDER").upper().replace("/", "")[:12] or "ORDER"
    side_text = str(side or "buy").lower()[:1] or "b"
    nonce = uuid.uuid4().hex[:16]
    return f"BT-{symbol}-{side_text}-{nonce}"


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
    """Obtiene el ID existente o genera uno nuevo para esta orden."""
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


def submit_order_idempotente(
    cliente: Any,
    order_data: Any,
    submit_callable: Optional[Callable[..., Any]] = None,
):
    """Envía una orden y reconcilia el resultado si el submit falla.

    No hace reintentos ciegos. El client_order_id queda pegado al objeto de
    orden durante toda la operación, por lo que una llamada de reconciliación
    puede consultar exactamente la misma identidad en Alpaca.
    """
    if order_data is None:
        raise ValueError("order_data es obligatorio")

    client_order_id = preparar_client_order_id(order_data)
    order_data = aplicar_client_order_id(order_data, client_order_id)

    existente = buscar_orden_por_client_id(cliente, client_order_id)
    if existente is not None and estado_no_reintentable(existente):
        return existente

    submit = submit_callable or cliente.submit_order
    try:
        return submit(order_data=order_data)
    except Exception:
        reconciliada = buscar_orden_por_client_id(cliente, client_order_id)
        if reconciliada is not None and estado_no_reintentable(reconciliada):
            return reconciliada
        raise
