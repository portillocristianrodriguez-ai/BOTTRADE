"""Descubrimiento conservador del universo de acciones de BOTTRADE.

Esta capa SOLO actualiza la lista de símbolos que se observan/escanean.
No genera señales, no modifica órdenes y no toca la gestión de posiciones.

Los tickers configurados manualmente siempre tienen prioridad y se conservan.
El universo descubierto se limita a acciones estadounidenses activas y
negociables en bolsas principales, con un tope configurable para evitar una
explosión de llamadas a datos.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

_LOCK = threading.RLock()
_CACHE = []
_UPDATED = None

_EXCHANGES = {
    "NYSE",
    "NASDAQ",
    "NASDAQOM",
    "NASDAQGS",
    "NASDAQCM",
    "NASDAQGM",
    "NYSEARCA",
    "NYSEAMERICAN",
    "AMEX",
    "ARCA",
    "BATS",
    "IEXG",
}


def _text(value):
    return str(value or "").strip().upper()


def _manuales(config_module):
    values = getattr(config_module, "TICKERS", [])
    result = []
    for value in values:
        ticker = _text(value)
        if ticker and "/" not in ticker and ticker not in result:
            result.append(ticker)
    return result


def obtener_universo(broker_module, config_module):
    """Devuelve el universo de acciones activo, negociable y acotado."""
    global _CACHE, _UPDATED

    manuales = _manuales(config_module)
    enabled = bool(getattr(config_module, "STOCK_AUTO_UNIVERSE_ENABLED", True))
    if not enabled:
        return manuales

    now = datetime.now(timezone.utc)
    refresh = max(1, int(getattr(config_module, "STOCK_UNIVERSE_REFRESH_MINUTES", 60)))
    maximum = max(1, int(getattr(config_module, "STOCK_MAX_SYMBOLS_SCAN", 500)))

    with _LOCK:
        if _CACHE and _UPDATED and now - _UPDATED < timedelta(minutes=refresh):
            discovered = list(_CACHE)
        else:
            try:
                assets = broker_module.cliente_trading.get_all_assets()
            except Exception as exc:
                log.warning("[acciones] No se pudo actualizar universo: %s", exc)
                discovered = list(_CACHE)

            if not discovered and 'assets' in locals():
                candidates = []
                for asset in assets:
                    try:
                        symbol = _text(getattr(asset, "symbol", ""))
                        if not symbol or "/" in symbol:
                            continue
                        if not bool(getattr(asset, "tradable", False)):
                            continue
                        status = _text(getattr(asset, "status", ""))
                        if status and status not in {"ACTIVE", "ACTIVO"}:
                            continue
                        asset_class = _text(getattr(asset, "asset_class", ""))
                        if asset_class and asset_class not in {"US_EQUITY", "US_EQUITY".upper()}:
                            continue
                        exchange = _text(getattr(asset, "exchange", ""))
                        if exchange and exchange not in _EXCHANGES:
                            continue
                        candidates.append(symbol)
                    except Exception:
                        continue

                # Orden estable para que una actualización del universo no produzca
                # churn innecesario. Los tickers manuales se añaden después como prioridad.
                discovered = sorted(set(candidates))[:maximum]
                _CACHE = list(discovered)
                _UPDATED = now
                log.info("[acciones] Universo descubierto: %s acciones negociables", len(discovered))

    ordered = []
    for ticker in manuales + discovered:
        if ticker not in ordered:
            ordered.append(ticker)
    return ordered[: max(maximum, len(manuales))]


def instalar(config_module, broker_module):
    """Actualiza config.TICKERS una vez al importar el bot.

    Si Alpaca no responde, conserva exactamente los tickers configurados.
    """
    try:
        universo = obtener_universo(broker_module, config_module)
        if universo:
            config_module.TICKERS = universo
            log.info("[acciones] Monitor ampliado: %s símbolos", len(universo))
    except Exception as exc:
        log.warning("[acciones] Universo automático omitido: %s", exc)
