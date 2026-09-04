"""Execution hardening loaded automatically by Python at startup.

Adds a deterministic client_order_id to every Alpaca order that does not
already have one. The same logical request retried during the same UTC minute
therefore reaches Alpaca with the same client ID, giving the API a second
layer of duplicate protection across bot instances/retries.

This module intentionally does not change position sizing, stop levels or
live/paper permissions.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def _normalizar(valor):
    if valor is None:
        return ""
    return str(valor).strip().upper().replace("/", "")


def _fingerprint(order_data) -> str:
    partes = [
        _normalizar(getattr(order_data, "symbol", "")),
        _normalizar(getattr(order_data, "side", "")),
        _normalizar(getattr(order_data, "type", "")),
        _normalizar(getattr(order_data, "qty", "")),
        _normalizar(getattr(order_data, "notional", "")),
        _normalizar(getattr(order_data, "limit_price", "")),
        _normalizar(getattr(order_data, "stop_price", "")),
        _normalizar(getattr(order_data, "order_class", "")),
        datetime.now(timezone.utc).strftime("%Y%m%d%H%M"),
    ]
    return hashlib.sha256("|".join(partes).encode("utf-8")).hexdigest()[:24]


def _construir_client_order_id(order_data) -> str:
    simbolo = _normalizar(getattr(order_data, "symbol", "ORDER"))[:24]
    lado = _normalizar(getattr(order_data, "side", "NA"))[:8]
    return f"BOTTRADE-{simbolo}-{lado}-{_fingerprint(order_data)}"


def _instalar_guard():
    try:
        from alpaca.trading.client import TradingClient
    except Exception:
        return

    original = getattr(TradingClient, "submit_order", None)
    if original is None or getattr(original, "_bottrade_guard", False):
        return

    def submit_order_guarded(self, order_data, *args, **kwargs):
        try:
            client_order_id = getattr(order_data, "client_order_id", None)
            if not client_order_id:
                # alpaca-py usa modelos Pydantic. model_copy preserva el tipo
                # concreto (MarketOrderRequest, LimitOrderRequest, OCO, etc.).
                nuevo_id = _construir_client_order_id(order_data)
                if hasattr(order_data, "model_copy"):
                    order_data = order_data.model_copy(update={"client_order_id": nuevo_id})
                else:
                    try:
                        setattr(order_data, "client_order_id", nuevo_id)
                    except Exception:
                        pass
                log.info(
                    "[execution] client_order_id=%s | symbol=%s | side=%s",
                    getattr(order_data, "client_order_id", nuevo_id),
                    getattr(order_data, "symbol", "?"),
                    getattr(order_data, "side", "?"),
                )
        except Exception as exc:
            # Nunca bloqueamos una orden válida por el guard de identificación.
            log.warning("[execution] No se pudo asignar client_order_id: %s", exc)

        return original(self, order_data, *args, **kwargs)

    submit_order_guarded._bottrade_guard = True
    TradingClient.submit_order = submit_order_guarded
    log.info("[execution] Guard client_order_id instalado.")


_instalar_guard()
