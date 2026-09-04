"""Descubrimiento completo del universo de acciones negociables de BOTTRADE."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)
_LOCK = threading.RLock()
_CACHE = []
_UPDATED = None
_REFRESH_THREAD_STARTED = False


def _text(value):
    value = getattr(value, "value", value)
    return str(value or "").strip().upper()


def _manuales(config_module):
    values = getattr(config_module, "TICKERS", [])
    result = []
    for value in values:
        ticker = _text(value)
        if ticker and "/" not in ticker and ticker not in result:
            result.append(ticker)
    return result


def _es_accion_us_tradable(asset):
    symbol = _text(getattr(asset, "symbol", ""))
    if not symbol or "/" in symbol:
        return False
    if not bool(getattr(asset, "tradable", False)):
        return False
    status = _text(getattr(asset, "status", ""))
    if status and status not in {"ACTIVE", "ACTIVO"}:
        return False
    asset_class = _text(getattr(asset, "asset_class", ""))
    if asset_class and asset_class != "US_EQUITY":
        return False
    return True


def obtener_universo(broker_module, config_module):
    """Devuelve todas las acciones US activas/tradables disponibles en Alpaca."""
    global _CACHE, _UPDATED
    if not bool(getattr(config_module, "STOCK_AUTO_UNIVERSE_ENABLED", True)):
        return sorted(set(_manuales(config_module)))
    now = datetime.now(timezone.utc)
    refresh = max(1, int(getattr(config_module, "STOCK_UNIVERSE_REFRESH_MINUTES", 60)))
    with _LOCK:
        if _CACHE and _UPDATED and now - _UPDATED < timedelta(minutes=refresh):
            discovered = list(_CACHE)
        else:
            try:
                assets = broker_module.cliente_trading.get_all_assets()
                discovered = sorted({
                    _text(getattr(asset, "symbol", ""))
                    for asset in assets
                    if _es_accion_us_tradable(asset)
                })
                if discovered:
                    _CACHE = list(discovered)
                    _UPDATED = now
                    log.info("[acciones] Universo completo actualizado: %s acciones negociables", len(discovered))
                else:
                    discovered = list(_CACHE)
                    log.warning("[acciones] Alpaca devolvió 0 acciones filtradas; se conserva el último universo conocido.")
            except Exception as exc:
                log.warning("[acciones] No se pudo actualizar universo: %s", exc)
                discovered = list(_CACHE)
    # Sin prioridad: todo el universo forma un conjunto único y ordenado.
    return sorted(set(_manuales(config_module) + discovered))


def _refrescar_loop(config_module, broker_module):
    while True:
        try:
            universo = obtener_universo(broker_module, config_module)
            if universo:
                config_module.TICKERS = universo
        except Exception as exc:
            log.debug("[acciones] Refresco automático omitido: %s", exc)
        refresh = max(1, int(getattr(config_module, "STOCK_UNIVERSE_REFRESH_MINUTES", 60)))
        threading.Event().wait(refresh * 60)


def instalar(config_module, broker_module):
    """Actualiza y mantiene el universo completo sin alterar la ejecución."""
    global _REFRESH_THREAD_STARTED
    try:
        universo = obtener_universo(broker_module, config_module)
        if universo:
            config_module.TICKERS = universo
            log.info("[acciones] Monitor ampliado a %s símbolos", len(universo))
        if not _REFRESH_THREAD_STARTED and bool(getattr(config_module, "STOCK_AUTO_UNIVERSE_ENABLED", True)):
            _REFRESH_THREAD_STARTED = True
            thread = threading.Thread(target=_refrescar_loop, args=(config_module, broker_module), name="stock-universe-refresh", daemon=True)
            thread.start()
    except Exception as exc:
        log.warning("[acciones] Universo automático omitido: %s", exc)


def estado_universo():
    with _LOCK:
        return {"acciones": len(_CACHE), "actualizado": _UPDATED, "tickers": list(_CACHE)}
