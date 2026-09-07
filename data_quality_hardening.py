"""Protección contra ventanas históricas insuficientes.

Evita que símbolos ilíquidos o con pocas barras lleguen a indicadores que
requieren historial mínimo. Además aplica una cuarentena temporal a símbolos
que acaban de devolver datos insuficientes o vacíos para no repetir llamadas
inútiles en cada ciclo.

No cambia señales, órdenes, SL/TP, riesgo ni exposición. Los símbolos se
reintentan automáticamente al expirar su cuarentena.
"""
from __future__ import annotations

import functools
import logging
import threading
import time

import pandas as pd


log = logging.getLogger(__name__)

DEFAULT_MIN_BARS = 50
_WARNING_INTERVAL_SECONDS = 15 * 60
DEFAULT_EMPTY_COOLDOWN_SECONDS = 5 * 60
DEFAULT_SHORT_HISTORY_COOLDOWN_SECONDS = 15 * 60

_warning_lock = threading.Lock()
_last_warning: dict[str, float] = {}

_cooldown_lock = threading.RLock()
_data_cooldown_until: dict[str, float] = {}
_data_cooldown_reason: dict[str, str] = {}


def _min_bars(config_module=None) -> int:
    cfg = config_module
    try:
        configured = int(getattr(cfg, "STRATEGY_MIN_BARS", DEFAULT_MIN_BARS)) if cfg is not None else DEFAULT_MIN_BARS
    except (TypeError, ValueError):
        configured = DEFAULT_MIN_BARS
    return max(DEFAULT_MIN_BARS, configured)


def _cooldown_seconds(config_module, attr: str, default: int) -> int:
    try:
        value = int(getattr(config_module, attr, default)) if config_module is not None else default
    except (TypeError, ValueError):
        value = default
    return max(0, value)


def _es_dataframe_valido(df, minimo: int) -> bool:
    return isinstance(df, pd.DataFrame) and not df.empty and len(df) >= minimo


def _avisar_historial_insuficiente(ticker, actual: int, minimo: int) -> None:
    """Evita inundar los logs cuando el universo contiene símbolos sin histórico."""
    clave = str(ticker)
    ahora = time.monotonic()
    with _warning_lock:
        ultimo = _last_warning.get(clave)
        if ultimo is not None and ahora - ultimo < _WARNING_INTERVAL_SECONDS:
            return
        _last_warning[clave] = ahora
    log.warning(
        "[datos] %s: historial insuficiente (%d/%d barras); se omite evaluación.",
        ticker,
        actual,
        minimo,
    )


def _poner_cooldown(ticker, segundos: int, razon: str) -> None:
    if segundos <= 0:
        return
    clave = str(ticker).strip().upper()
    if not clave:
        return
    with _cooldown_lock:
        _data_cooldown_until[clave] = time.monotonic() + segundos
        _data_cooldown_reason[clave] = razon


def _en_cooldown(ticker) -> bool:
    clave = str(ticker).strip().upper()
    ahora = time.monotonic()
    with _cooldown_lock:
        hasta = _data_cooldown_until.get(clave)
        if hasta is None:
            return False
        if ahora >= hasta:
            _data_cooldown_until.pop(clave, None)
            _data_cooldown_reason.pop(clave, None)
            return False
        return True


def _limpiar_cooldown(ticker) -> None:
    clave = str(ticker).strip().upper()
    with _cooldown_lock:
        _data_cooldown_until.pop(clave, None)
        _data_cooldown_reason.pop(clave, None)


def estado_cooldowns() -> dict:
    """Estado diagnóstico de cuarentenas activas, sin alterar su duración."""
    ahora = time.monotonic()
    activos = {}
    with _cooldown_lock:
        expirados = []
        for ticker, hasta in _data_cooldown_until.items():
            restante = hasta - ahora
            if restante <= 0:
                expirados.append(ticker)
                continue
            activos[ticker] = {
                "segundos_restantes": int(restante),
                "razon": _data_cooldown_reason.get(ticker, "datos_invalidos"),
            }
        for ticker in expirados:
            _data_cooldown_until.pop(ticker, None)
            _data_cooldown_reason.pop(ticker, None)
    return activos


def instalar(main_module) -> None:
    """Endurece la entrada de datos de mercado una sola vez."""
    broker_module = getattr(main_module, "broker", None)
    if broker_module is None:
        return

    original = getattr(broker_module, "obtener_datos", None)
    if not callable(original) or getattr(original, "_bottrade_data_quality", False):
        return

    config_module = getattr(main_module, "config", None)
    minimo = _min_bars(config_module)
    empty_cooldown = _cooldown_seconds(
        config_module,
        "STOCK_EMPTY_DATA_COOLDOWN_SECONDS",
        DEFAULT_EMPTY_COOLDOWN_SECONDS,
    )
    short_history_cooldown = _cooldown_seconds(
        config_module,
        "STOCK_SHORT_HISTORY_COOLDOWN_SECONDS",
        DEFAULT_SHORT_HISTORY_COOLDOWN_SECONDS,
    )

    @functools.wraps(original)
    def obtener_datos_seguro(ticker):
        # Crypto se gestiona 24/7 y no debe heredar la cuarentena del universo
        # masivo de acciones.
        symbol = str(ticker or "").strip().upper()
        es_crypto = "/" in symbol

        if not es_crypto and _en_cooldown(symbol):
            return pd.DataFrame()

        try:
            df = original(ticker)
            if df is None or getattr(df, "empty", True):
                if not es_crypto:
                    _poner_cooldown(symbol, empty_cooldown, "sin_datos")
                return pd.DataFrame()

            if len(df) < minimo:
                _avisar_historial_insuficiente(ticker, len(df), minimo)
                if not es_crypto:
                    _poner_cooldown(
                        symbol,
                        short_history_cooldown,
                        f"historial_insuficiente:{len(df)}/{minimo}",
                    )
                return pd.DataFrame()

            if not es_crypto:
                _limpiar_cooldown(symbol)
            return df
        except Exception:
            if not es_crypto:
                _poner_cooldown(symbol, empty_cooldown, "error_datos")
            return pd.DataFrame()

    obtener_datos_seguro._bottrade_data_quality = True
    broker_module.obtener_datos = obtener_datos_seguro
    log.info(
        "[datos] Calidad de histórico endurecida; cuarentena acciones activa "
        "(sin datos=%ss, histórico corto=%ss).",
        empty_cooldown,
        short_history_cooldown,
    )
