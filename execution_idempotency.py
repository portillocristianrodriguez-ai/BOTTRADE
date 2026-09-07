"""Idempotencia y reconciliación segura de órdenes para BOTTRADE."""
from __future__ import annotations

import math
import os
import uuid
import threading
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Any, Callable, Optional

_BUY_SUBMISSION_LOCK = threading.RLock()


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
    """Obtiene el mejor ask actual de Alpaca justo antes de enviar un BUY."""
    normalized = str(symbol or "").upper().strip()
    is_crypto = "/" in normalized or normalized.endswith("/USD")
    max_age = max(5.0, float(os.environ.get("BOTTRADE_MAX_BUY_QUOTE_AGE_SECONDS", "60")))

    try:
        if is_crypto:
            from alpaca.data.historical import CryptoHistoricalDataClient
            from alpaca.data.requests import CryptoLatestQuoteRequest
            market_client = CryptoHistoricalDataClient()
            quote = market_client.get_crypto_latest_quote(
                CryptoLatestQuoteRequest(symbol_or_symbols=normalized)
            ).get(normalized)
            price = float(getattr(quote, "ask_price", 0) or 0) if quote else 0.0
            timestamp = getattr(quote, "timestamp", None) if quote else None
        else:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockLatestQuoteRequest
            from alpaca.data.enums import DataFeed
            import config
            market_client = StockHistoricalDataClient(config.API_KEY, config.API_SECRET)
            quote = market_client.get_stock_latest_quote(
                StockLatestQuoteRequest(symbol_or_symbols=normalized, feed=DataFeed.IEX)
            ).get(normalized)
            price = float(getattr(quote, "ask_price", 0) or 0) if quote else 0.0
            timestamp = getattr(quote, "timestamp", None) if quote else None

        if price <= 0 or not math.isfinite(price):
            return None, "no_valid_price"
        parsed = _parse_timestamp(timestamp)
        if parsed is None:
            return None, "missing_quote_timestamp"
        age = (datetime.now(timezone.utc) - parsed).total_seconds()
        if age < -5 or age > max_age:
            return None, f"stale_quote_{age:.1f}s"
        return price, "ok"
    except Exception as exc:
        return None, f"market_data_error:{exc}"


def _replace_qty(order_data: Any, qty: float):
    try:
        order_data.qty = qty
        return order_data
    except Exception:
        dumped = order_data.model_dump()
        dumped["qty"] = qty
        return type(order_data)(**dumped)


def _refresh_buy_quantity(cliente: Any, order_data: Any):
    """Usa el ask actual para que la cantidad final sea coherente con el mercado.

    La capa nunca aumenta la cantidad original. Si el precio ha subido, reduce
    cantidad para mantener la orden dentro de los límites actuales de equity,
    buying power y caps crypto. Si el precio no está disponible o está obsoleto,
    bloquea el BUY en vez de usar una referencia histórica.
    """
    side = str(getattr(order_data, "side", "") or "").lower()
    if "buy" not in side:
        return order_data

    original_qty = float(getattr(order_data, "qty", 0) or 0)
    if original_qty <= 0 or not math.isfinite(original_qty):
        raise ValueError("BUY sin cantidad válida")

    symbol = str(getattr(order_data, "symbol", "") or "").upper().strip()
    current_price, reason = _latest_buy_price(cliente, symbol)
    if current_price is None:
        raise ValueError(f"precio BUY no disponible: {reason}")

    account = cliente.get_account()
    equity = float(getattr(account, "equity", 0) or 0)
    buying_power = float(getattr(account, "buying_power", 0) or 0)
    if equity <= 0 or buying_power <= 0 or not all(map(math.isfinite, (equity, buying_power))):
        raise ValueError("cuenta BUY inválida")

    try:
        import config
        buying_power_buffer = min(0.99, max(0.10, float(getattr(config, "ORDER_BUYING_POWER_BUFFER", 0.85))))
        max_notional = min(buying_power * buying_power_buffer,
                           equity * float(config.MAX_SINGLE_POSITION_PCT))
        is_crypto = "/" in symbol or symbol.endswith("/USD")
        if is_crypto:
            equity_cap = equity * float(getattr(config, "CRYPTO_MAX_NOTIONAL_PCT", 0.10))
            hard_cap = float(getattr(config, "CRYPTO_HARD_MAX_NOTIONAL", 100000.0))
            internal_cap = float(getattr(config, "CRYPTO_INTERNAL_MAX_ORDER_NOTIONAL_USD", hard_cap))
            max_notional = min(max_notional, equity_cap, hard_cap, internal_cap)
    except Exception as exc:
        raise ValueError(f"config BUY inválida: {exc}")

    if max_notional <= 0 or not math.isfinite(max_notional):
        raise ValueError("límite de notional BUY inválido")

    safe_qty = min(original_qty, max_notional / current_price)
    if is_crypto:
        asset = cliente.get_asset(symbol)
        increment = Decimal(str(getattr(asset, 'min_trade_increment', None)))
        minimum = Decimal(str(getattr(asset, 'min_order_size', None)))
        if not increment.is_finite() or increment <= 0 or not minimum.is_finite() or minimum <= 0:
            raise ValueError('Metadatos de cantidad crypto inválidos')
        rounded = (Decimal(str(safe_qty)) / increment).to_integral_value(rounding=ROUND_DOWN) * increment
        if rounded < minimum:
            raise ValueError('Cantidad crypto inferior al mínimo del activo')
        qty = float(rounded)
    else:
        qty = int(safe_qty)

    if qty <= 0:
        raise ValueError(f"cantidad BUY nula con precio actual ${current_price:.8f}")

    # Re-read portfolio and pending orders at the final quote, not the scanner's
    # earlier price. Never liquidates or resizes an existing position.
    import execution_guard
    from alpaca.trading.enums import QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest
    positions = cliente.get_all_positions()
    pending = cliente.get_orders(filter=GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=500, nested=True))
    if positions is None or pending is None or len(pending) >= 500:
        raise ValueError('Snapshot de exposición incompleto')
    normalized = execution_guard.normalizar_simbolo(symbol)
    for position in positions:
        if (execution_guard.normalizar_simbolo(getattr(position, 'symbol', '')) == normalized
                and execution_guard.posicion_notional(position) > 0):
            raise ValueError('Ya existe posición para esta compra')
    for order in pending:
        if execution_guard.normalizar_simbolo(getattr(order, 'symbol', '')) == normalized:
            raise ValueError('Ya existe orden pendiente para este activo')
    ok, reason = execution_guard.validar_exposicion_compra(
        equity=equity, proposed_notional=qty * current_price, positions=positions,
        open_orders=pending, max_single_position_pct=config.MAX_SINGLE_POSITION_PCT,
        max_total_exposure_pct=config.MAX_TOTAL_EXPOSURE_PCT)
    if not ok:
        raise ValueError('Exposición final bloqueada: ' + reason)

    if qty != original_qty:
        try:
            import logging
            logging.getLogger(__name__).info(
                f"[MARKET_PRICE] {symbol}: precio BUY actualizado=${current_price:.8f}; "
                f"qty {original_qty}->{qty}; notional<=${max_notional:,.2f}"
            )
        except Exception:
            pass

    return _replace_qty(order_data, qty)


def _submit_order_idempotente(
    cliente: Any,
    order_data: Any,
    submit_callable: Optional[Callable[..., Any]] = None,
):
    """Envía una orden y reconcilia el resultado si el submit falla.

    Los BUY pasan por una última consulta de mercado a Alpaca justo antes del
    submit. Se utiliza el ask más reciente (IEX en acciones) y se bloquea la
    orden si la cotización está obsoleta.
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


def submit_order_idempotente(cliente, order_data, submit_callable=None):
    """Serialize BUY check/send pairs in this worker; SELL exits never wait on it.

    Broker-side snapshots and client IDs remain required. This process lock is
    not a distributed lock and is not a guarantee against external traders.
    """
    side = str(getattr(order_data, 'side', '') or '').lower()
    if 'buy' in side:
        with _BUY_SUBMISSION_LOCK:
            return _submit_order_idempotente(cliente, order_data, submit_callable)
    return _submit_order_idempotente(cliente, order_data, submit_callable)
