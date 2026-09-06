"""Idempotencia y reconciliación segura de órdenes para BOTTRADE."""
from __future__ import annotations

import math
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
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
    """Genera un ID único por objeto lógico de orden."""
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


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _latest_buy_price(cliente: Any, symbol: str):
    """Obtiene el mejor ask actual de Alpaca justo antes de enviar un BUY.

    Para acciones se usa IEX, coherente con el feed utilizado por el bot.
    Para crypto se usa la cotización US de Alpaca. Si no hay ask válido,
    se intenta el último trade como fallback. Una cotización demasiado vieja
    bloquea la orden en lugar de utilizar un precio histórico.
    """
    normalized = str(symbol or "").upper().strip()
    is_crypto = "/" in normalized or normalized.endswith("/USD")
    max_age = max(5.0, float(os.environ.get("BOTTRADE_MAX_BUY_QUOTE_AGE_SECONDS", "60")))

    try:
        if is_crypto:
            from alpaca.data.historical import CryptoHistoricalDataClient
            from alpaca.data.requests import CryptoLatestQuoteRequest, CryptoLatestTradeRequest
            market_client = CryptoHistoricalDataClient()
            quote = market_client.get_crypto_latest_quote(
                CryptoLatestQuoteRequest(symbol_or_symbols=normalized)
            ).get(normalized)
            price = float(getattr(quote, "ask_price", 0) or 0) if quote else 0.0
            timestamp = getattr(quote, "timestamp", None) if quote else None
            if price <= 0:
                trade = market_client.get_crypto_latest_trade(
                    CryptoLatestTradeRequest(symbol_or_symbols=normalized)
                ).get(normalized)
                price = float(getattr(trade, "price", 0) or 0) if trade else 0.0
                timestamp = getattr(trade, "timestamp", None) if trade else None
        else:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockLatestQuoteRequest, StockLatestTradeRequest
            from alpaca.data.enums import DataFeed
            market_client = StockHistoricalDataClient(
                getattr(cliente, "_api_key", None),
                getattr(cliente, "_secret_key", None),
            )
            quote = market_client.get_stock_latest_quote(
                StockLatestQuoteRequest(symbol_or_symbols=normalized, feed=DataFeed.IEX)
            ).get(normalized)
            price = float(getattr(quote, "ask_price", 0) or 0) if quote else 0.0
            timestamp = getattr(quote, "timestamp", None) if quote else None
            if price <= 0:
                trade = market_client.get_stock_latest_trade(
                    StockLatestTradeRequest(symbol_or_symbols=normalized, feed=DataFeed.IEX)
                ).get(normalized)
                price = float(getattr(trade, "price", 0) or 0) if trade else 0.0
                timestamp = getattr(trade, "timestamp", None) if trade else None

        if price <= 0 or not math.isfinite(price):
            return None, "no_valid_price"
        parsed = _parse_timestamp(timestamp)
        if parsed is not None:
            age = (datetime.now(timezone.utc) - parsed).total_seconds()
            if age < -5 or age > max_age:
                return None, f"stale_quote_{age:.1f}s"
        else:
            return None, "missing_quote_timestamp"
        return price, "ok"
    except Exception as exc:
        return None, f"market_data_error:{exc}"


def _refresh_buy_quantity(cliente: Any, order_data: Any):
    """Recalcula la cantidad BUY usando el precio actual de Alpaca.

    Mantiene como techo el notional que ya había pasado las barreras de riesgo.
    Si el precio sube, reduce cantidad; nunca aumenta exposición por esta capa.
    """
    side = str(getattr(order_data, "side", "") or "").lower()
    if "buy" not in side:
        return order_data

    original_qty = float(getattr(order_data, "qty", 0) or 0)
    if original_qty <= 0:
        raise ValueError("BUY sin cantidad válida")

    symbol = str(getattr(order_data, "symbol", "") or "").upper().strip()
    current_price, reason = _latest_buy_price(cliente, symbol)
    if current_price is None:
        raise ValueError(f"precio BUY no disponible: {reason}")

    # El orden ya fue dimensionado y validado con un precio anterior. Ese
    # notional es el techo: el precio fresco solo puede reducir la cantidad.
    reference_price = float(getattr(order_data, "_bottrade_reference_price", 0) or 0)
    if reference_price <= 0:
        reference_price = current_price

    max_notional = original_qty * reference_price
    if max_notional <= 0 or not math.isfinite(max_notional):
        raise ValueError("notional BUY inválido")

    raw_qty = min(original_qty, max_notional / current_price)
    is_crypto = "/" in symbol or symbol.endswith("/USD")

    if is_crypto:
        # Alpaca permite fracciones crypto; 6 decimales mantienen compatibilidad
        # con el sizing existente y el normalizador de cantidades del bot.
        qty = float(Decimal(str(raw_qty)).quantize(Decimal("0.000001"), rounding=ROUND_DOWN))
    else:
        qty = int(raw_qty)

    if qty <= 0:
        raise ValueError(f"cantidad BUY nula tras refrescar precio=${current_price:.8f}")

    try:
        order_data.qty = qty
    except Exception:
        dumped = order_data.model_dump()
        dumped["qty"] = qty
        order_data = type(order_data)(**dumped)

    return order_data


def submit_order_idempotente(
    cliente: Any,
    order_data: Any,
    submit_callable: Optional[Callable[..., Any]] = None,
):
    """Envía una orden y reconcilia el resultado si el submit falla.

    Los BUY pasan por una última consulta de mercado a Alpaca justo antes del
    submit. No se usan barras históricas para decidir la cantidad final.
    """
    if order_data is None:
        raise ValueError("order_data es obligatorio")

    client_order_id = preparar_client_order_id(order_data)
    order_data = aplicar_client_order_id(order_data, client_order_id)

    existente = buscar_orden_por_client_id(cliente, client_order_id)
    if existente is not None and estado_no_reintentable(existente):
        return existente

    order_data = _refresh_buy_quantity(cliente, order_data)

    submit = submit_callable or cliente.submit_order
    try:
        return submit(order_data=order_data)
    except Exception:
        reconciliada = buscar_orden_por_client_id(cliente, client_order_id)
        if reconciliada is not None and estado_no_reintentable(reconciliada):
            return reconciliada
        raise
