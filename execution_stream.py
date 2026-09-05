"""Monitor de ejecuciones Alpaca por WebSocket.

Complementa el monitor REST existente con eventos trade_updates en tiempo real.
No crea ni modifica órdenes: solo observa y registra cambios de estado.
"""
from __future__ import annotations

import logging
import threading
import time

import config
from crypto_quantity import normalizar_cantidad_crypto

log = logging.getLogger(__name__)

_STREAM_THREAD = None
_STREAM_LOCK = threading.Lock()
_PRECISION_PATCH_LOCK = threading.Lock()
_PRECISION_PATCH_INSTALLED = False


def _texto(valor):
    return str(valor) if valor is not None else ""


def _instalar_proteccion_qty_crypto():
    """Corrige qty SELL crypto justo antes de llegar a Alpaca.

    Las posiciones crypto pueden contener pequeñas diferencias de precisión
    entre el saldo local y el saldo liquidable del broker. El wrapper redondea
    hacia abajo usando el incremento del activo y evita pedir exactamente el
    último múltiplo cuando este puede estar unos decimales por encima del saldo.
    """
    global _PRECISION_PATCH_INSTALLED
    with _PRECISION_PATCH_LOCK:
        if _PRECISION_PATCH_INSTALLED:
            return
        try:
            from alpaca.trading.client import TradingClient
        except Exception as exc:
            log.debug("[precision] Alpaca TradingClient no disponible: %s", exc)
            return

        original = getattr(TradingClient, "submit_order", None)
        if not callable(original) or getattr(original, "_bottrade_crypto_precision", False):
            _PRECISION_PATCH_INSTALLED = True
            return

        def submit_order_safe(self, *args, **kwargs):
            order_data = kwargs.get("order_data")
            if order_data is None and args:
                order_data = args[0]

            try:
                side = _texto(getattr(order_data, "side", "")).lower()
                symbol = _texto(getattr(order_data, "symbol", "")).upper()
                qty = getattr(order_data, "qty", None)
                es_crypto = "/" in symbol or symbol.endswith("USD")

                if es_crypto and "sell" in side and qty is not None:
                    incremento = None
                    try:
                        asset = self.get_asset(symbol=symbol)
                        incremento = getattr(asset, "min_trade_increment", None)
                    except Exception as exc:
                        log.debug("[precision] no se pudo consultar incremento de %s: %s", symbol, exc)

                    qty_segura = normalizar_cantidad_crypto(qty, incremento)
                    if qty_segura <= 0:
                        raise ValueError(f"qty SELL crypto inválida tras normalización: {symbol} qty={qty}")
                    if str(qty_segura) != str(qty):
                        log.warning(
                            "[precision] %s SELL qty ajustada %s -> %s (incremento=%s)",
                            symbol,
                            qty,
                            qty_segura,
                            incremento,
                        )
                        order_data.qty = qty_segura
            except Exception:
                raise

            return original(self, *args, **kwargs)

        submit_order_safe._bottrade_crypto_precision = True
        TradingClient.submit_order = submit_order_safe
        _PRECISION_PATCH_INSTALLED = True
        log.info("[precision] Protección de qty crypto instalada.")


_instalar_proteccion_qty_crypto()


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

        # El analista recibe únicamente eventos de ejecución observados.
        # Este hook está aislado para que un fallo del analista nunca afecte
        # al stream ni al motor de trading.
        try:
            from ai_analyst_live import record_trade_update
            record_trade_update(data)
        except Exception as exc:
            log.debug("[AI] no se pudo registrar trade_update: %s", exc)

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
