"""Protección contra ventanas históricas insuficientes.

Evita que símbolos ilíquidos o con pocas barras lleguen a indicadores que
requieren historial mínimo. No cambia señales, órdenes, SL/TP, riesgo ni
exposición: simplemente omite datos que no pueden producir una evaluación
válida.
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
_warning_lock = threading.Lock()
_last_warning: dict[str, float] = {}


def _min_bars(config_module=None) -> int:
    cfg = config_module
    try:
        configured = int(getattr(cfg, "STRATEGY_MIN_BARS", DEFAULT_MIN_BARS)) if cfg is not None else DEFAULT_MIN_BARS
    except (TypeError, ValueError):
        configured = DEFAULT_MIN_BARS
    return max(DEFAULT_MIN_BARS, configured)


def _es_dataframe_valido(df, minimo: int) -> bool:
    return isinstance(df, pd.DataFrame) and not df.empty and len(df) >= minimo


def _avisar_historial_insuficiente(ticker, actual: int, minimo: int) -> None:
    """Evita inundar los logs cuando el universo contiene símbolos sin histórico."""
    clave = str(ticker)
    ahora = time.monotonic()
    with _warning_lock:
        ultimo = _last_warning.get(clave, 0.0)
        if ahora - ultimo < _WARNING_INTERVAL_SECONDS:
            return
        _last_warning[clave] = ahora
    log.warning(
        "[datos] %s: historial insuficiente (%d/%d barras); se omite evaluación.",
        ticker,
        actual,
        minimo,
    )


def instalar(main_module) -> None:
    """Endurece la entrada de datos de mercado una sola vez."""
    broker_module = getattr(main_module, "broker", None)
    if broker_module is None:
        return

    original = getattr(broker_module, "obtener_datos", None)
    if not callable(original) or getattr(original, "_bottrade_data_quality", False):
        return

    minimo = _min_bars(getattr(main_module, "config", None))

    @functools.wraps(original)
    def obtener_datos_seguro(ticker):
        try:
            df = original(ticker)
            if df is None or getattr(df, "empty", True):
                return pd.DataFrame()
            if len(df) < minimo:
                _avisar_historial_insuficiente(ticker, len(df), minimo)
                return pd.DataFrame()
            return df
        except Exception:
            return pd.DataFrame()

    obtener_datos_seguro._bottrade_data_quality = True
    broker_module.obtener_datos = obtener_datos_seguro
    log.info("[datos] Calidad de histórico endurecida; avisos limitados por símbolo.")
