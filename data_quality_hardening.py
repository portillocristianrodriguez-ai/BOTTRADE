"""Protección contra ventanas históricas insuficientes.

Evita que símbolos ilíquidos o con pocas barras lleguen a indicadores que
requieren historial mínimo. No cambia señales, órdenes, SL/TP, riesgo ni
exposición: simplemente omite datos que no pueden producir una evaluación
válida.
"""
from __future__ import annotations

import functools
import logging

import pandas as pd


log = logging.getLogger(__name__)

DEFAULT_MIN_BARS = 50


def _min_bars(config_module=None) -> int:
    cfg = config_module
    try:
        # La estrategia de impulso actual necesita 50 barras como mínimo.
        # Permitimos elevar el umbral por configuración, nunca reducirlo.
        configured = int(getattr(cfg, "STRATEGY_MIN_BARS", DEFAULT_MIN_BARS)) if cfg is not None else DEFAULT_MIN_BARS
    except (TypeError, ValueError):
        configured = DEFAULT_MIN_BARS
    return max(DEFAULT_MIN_BARS, configured)


def _es_dataframe_valido(df, minimo: int) -> bool:
    return isinstance(df, pd.DataFrame) and not df.empty and len(df) >= minimo


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
                log.warning(
                    "[datos] %s: historial insuficiente (%d/%d barras); se omite evaluación.",
                    ticker,
                    len(df),
                    minimo,
                )
                return pd.DataFrame()
            return df
        except Exception:
            # Mantener la semántica existente de broker.obtener_datos:
            # los fallos de datos no deben propagarse al scanner.
            return pd.DataFrame()

    obtener_datos_seguro._bottrade_data_quality = True
    broker_module.obtener_datos = obtener_datos_seguro
