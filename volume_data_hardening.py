"""Validación defensiva de ratios de volumen.

Este módulo no cambia umbrales de estrategia ni genera señales. Solo impide
que ratios de volumen calculados con denominadores no fiables (histórico
insuficiente, media cero/casi cero, NaN, infinito o ratio inconsistente)
se utilicen o persistan.
"""
from __future__ import annotations

import math
from functools import wraps

import pandas as pd

_INSTALLED = False

_MIN_REFERENCE_VOLUME = 1e-12
_MAX_NUMERIC_RATIO = 1_000_000.0


def _finite_positive(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > _MIN_REFERENCE_VOLUME


def _ratio_consistente(volume, reference_mean, ratio):
    """Comprueba que el ratio recibido coincide con volume / media previa."""
    try:
        v = float(volume)
        base = float(reference_mean)
        r = float(ratio)
    except (TypeError, ValueError):
        return False
    if not (math.isfinite(v) and math.isfinite(base) and math.isfinite(r)):
        return False
    if v < 0 or base <= _MIN_REFERENCE_VOLUME or r < 0 or r > _MAX_NUMERIC_RATIO:
        return False
    esperado = v / base
    if not math.isfinite(esperado) or esperado > _MAX_NUMERIC_RATIO:
        return False
    return math.isclose(r, esperado, rel_tol=1e-9, abs_tol=1e-12)


def _sanitize(df, config_module):
    if df is None or getattr(df, "empty", True):
        return df
    out = df.copy()
    periodo = max(5, int(getattr(config_module, "VOLUMEN_SMA_PERIODO", 20)))

    for ratio_col, mean_col, min_periods in (
        ("volumen_ratio", "volumen_media", periodo),
        ("aceleracion_volumen", "volumen_media_corta", 3),
    ):
        if ratio_col not in out.columns or mean_col not in out.columns or "volume" not in out.columns:
            continue

        volume = pd.to_numeric(out["volume"], errors="coerce")
        mean = pd.to_numeric(out[mean_col], errors="coerce")
        ratio = pd.to_numeric(out[ratio_col], errors="coerce")

        valid_count = volume.shift(1).rolling(min_periods, min_periods=min_periods).count()
        valid_mean = mean.where(valid_count >= min_periods)
        valid_mean = valid_mean.where(valid_mean.map(_finite_positive))

        consistent = pd.Series(
            [
                _ratio_consistente(v, m, r)
                if pd.notna(v) and pd.notna(m) and pd.notna(r)
                else False
                for v, m, r in zip(volume, valid_mean, ratio)
            ],
            index=out.index,
        )
        valid_ratio = ratio.where(consistent)

        out[mean_col] = valid_mean
        out[ratio_col] = valid_ratio

    if "volumen_valido" in out.columns:
        volume = pd.to_numeric(out["volume"], errors="coerce")
        out["volumen_valido"] = volume.gt(0) & volume.map(
            lambda x: math.isfinite(float(x)) if pd.notna(x) else False
        )
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
