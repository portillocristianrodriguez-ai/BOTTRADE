"""Monitor de ejecuciones Alpaca por WebSocket.

Complementa el monitor REST existente con eventos trade_updates en tiempo real.
No crea ni modifica órdenes: solo observa y registra cambios de estado.
"""
from __future__ import annotations

import logging
import threading
import time

import config

log = logging.getLogger(__name__)

_STREAM_THREAD = None
_STREAM_LOCK = threading.Lock()


def _texto(valor):
    return str(valor) if valor is not None else ""


def _callback_factory():
    async def on_trade_update(data):
        event = _texto(getattr(data, "event", "unknown"))
        order = getattr(data, "order", None)
        symbol = _texto(getattr(order, "symbol", ""))
        side = _texto(getattr(order, "side", ""))
        status = _texto(getattr(order, "status", ""))
        qty = _texto(getattr(order, "qty", ""))
        filled_qty = _texto(getattr(order, "filled_qty", ""))
        client_order_id = _texto(getattr(order, "client_order_id", ""))
        order_id = _texto(getattr(order, "id", ""))
        price = _texto(getattr(data, "price", ""))

        log.info(
            "[stream] trade_update event=%s symbol=%s side=%s status=%s "
            "qty=%s filled=%s price=%s order_id=%s client_order_id=%s",
            event,
            symbol,
            side,
            status,
            qty,
            filled_qty,
            price,
            order_id,
            client_order_id,
        )

    return on_trade_update


def _run_forever():
    try:
        from alpaca.trading.stream import TradingStream
    except Exception as exc:
        log.error("[stream] Alpaca TradingStream no disponible: %s", exc)
        return

    minimo = max(5, int(getattr(config, "EXECUTION_STREAM_RECONNECT_MIN_SECONDS", 5)))
    maximo = max(minimo, int(getattr(config, "EXECUTION_STREAM_RECONNECT_MAX_SECONDS", 60)))
    espera = minimo

    while True:
        try:
            stream = TradingStream(
                config.API_KEY,
                config.API_SECRET,
                paper=config.PAPER,
            )
            stream.subscribe_trade_updates(_callback_factory())
            log.info("[stream] trade_updates conectado.")
            espera = minimo
            stream.run()
            log.warning("[stream] trade_updates terminó; reconectando.")
        except Exception as exc:
            log.warning("[stream] conexión perdida: %s", exc)

        time.sleep(espera)
        espera = min(maximo, espera * 2)


def lanzar_stream_ejecuciones():
    """Arranca un único listener WebSocket en segundo plano."""
    global _STREAM_THREAD

    if not bool(getattr(config, "EXECUTION_STREAM_ENABLED", True)):
        log.info("[stream] Monitor WebSocket desactivado por configuración.")
        return None

    with _STREAM_LOCK:
        if _STREAM_THREAD is not None and _STREAM_THREAD.is_alive():
            return _STREAM_THREAD

        _STREAM_THREAD = threading.Thread(
            target=_run_forever,
            name="ExecutionTradeStream",
            daemon=True,
        )
        _STREAM_THREAD.start()
        log.info("[stream] Monitor de ejecuciones iniciado.")
        return _STREAM_THREAD
