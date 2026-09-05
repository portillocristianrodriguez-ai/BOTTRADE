"""Validación defensiva de ratios de volumen.

Este módulo no cambia umbrales de estrategia ni genera señales. Solo impide
que ratios de volumen calculados con denominadores no fiables (histórico
insuficiente, media cero/casi cero, NaN o infinito) se utilicen o persistan.
"""
from __future__ import annotations

import math
from functools import wraps

import pandas as pd

_INSTALLED = False


def _finite_positive(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0.0


def _sanitize(df, config_module):
    if df is None or getattr(df, "empty", True):
        return df
    out = df.copy()
    periodo = max(5, int(getattr(config_module, "VOLUMEN_SMA_PERIODO", 20)))

    # Los ratios solo son fiables cuando existen exactamente los datos que
    # requiere su ventana y la media de referencia es positiva y finita.
    for ratio_col, mean_col, min_periods in (
        ("volumen_ratio", "volumen_media", periodo),
        ("aceleracion_volumen", "volumen_media_corta", 3),
    ):
        if ratio_col not in out.columns or mean_col not in out.columns or "volume" not in out.columns:
            continue

        volume = pd.to_numeric(out["volume"], errors="coerce")
        mean = pd.to_numeric(out[mean_col], errors="coerce")
        ratio = pd.to_numeric(out[ratio_col], errors="coerce")

        # Recalcular disponibilidad de histórico a partir de la serie real,
        # evitando depender de un valor numérico residual de una media.
        window = min_periods
        valid_count = volume.shift(1).rolling(window, min_periods=window).count()
        valid_mean = mean.where(valid_count >= window)
        valid_mean = valid_mean.where(valid_mean.map(_finite_positive))

        valid_ratio = ratio.where(valid_mean.notna())
        valid_ratio = valid_ratio.where(valid_ratio.map(lambda x: math.isfinite(float(x)) if pd.notna(x) else False))
        valid_ratio = valid_ratio.where(valid_ratio >= 0.0)

        out[mean_col] = valid_mean
        out[ratio_col] = valid_ratio

    if "volumen_valido" in out.columns:
        volume = pd.to_numeric(out["volume"], errors="coerce")
        out["volumen_valido"] = volume.gt(0) & volume.map(lambda x: math.isfinite(float(x)) if pd.notna(x) else False)
    return out


def instalar(estrategia_module):
    """Instala la validación sin modificar la lógica económica."""
    global _INSTALLED
    if _INSTALLED or getattr(estrategia_module.calcular_indicadores, "_volume_hardening", False):
        _INSTALLED = True
        return

    original_calcular = estrategia_module.calcular_indicadores
    config_module = estrategia_module.config

    @wraps(original_calcular)
    def calcular_indicadores_seguro(df):
        resultado = original_calcular(df)
        return _sanitize(resultado, config_module)

    calcular_indicadores_seguro._volume_hardening = True
    estrategia_module.calcular_indicadores = calcular_indicadores_seguro
    _INSTALLED = True
