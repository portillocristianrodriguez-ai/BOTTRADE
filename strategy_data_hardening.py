"""Endurece los datos derivados usados por la estrategia sin cambiar reglas de trading.

Corrige métricas de volumen no finitas o matemáticamente no informativas cuando
la media histórica es cero/casi cero. En esos casos el ratio queda neutral (0),
evita rankings absurdos y obliga a que los filtros de volumen fallen de forma
segura en vez de premiar datos corruptos.
"""
from __future__ import annotations

import functools
import logging
import math

import pandas as pd

log = logging.getLogger(__name__)
_EPSILON = 1e-12


def _sanear_ratio(serie: pd.Series, media: pd.Series) -> pd.Series:
    numerador = pd.to_numeric(serie, errors="coerce")
    denominador = pd.to_numeric(media, errors="coerce")
    ratio = numerador / denominador.where(denominador.abs() > _EPSILON)
    ratio = ratio.where(ratio.map(lambda value: isinstance(value, (int, float)) and math.isfinite(float(value))), 0.0)
    return pd.to_numeric(ratio, errors="coerce").fillna(0.0)


def _sanear_indicadores(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return df
    salida = df.copy()
    if "volume" not in salida.columns:
        return salida
    if "volumen_media" in salida.columns:
        salida["volumen_ratio"] = _sanear_ratio(salida["volume"], salida["volumen_media"])
    if "volumen_media_corta" in salida.columns:
        salida["aceleracion_volumen"] = _sanear_ratio(salida["volume"], salida["volumen_media_corta"])
    for columna in ("volumen_ratio", "aceleracion_volumen"):
        if columna in salida.columns:
            salida[columna] = salida[columna].clip(lower=0.0, upper=100.0)
    return salida


def instalar(estrategia_module) -> None:
    """Envuelve `calcular_indicadores` para impedir ratios de volumen absurdos."""
    original = getattr(estrategia_module, "calcular_indicadores", None)
    if not callable(original) or getattr(original, "_bottrade_strategy_data_hardening", False):
        return

    @functools.wraps(original)
    def calcular_indicadores_seguro(df):
        try:
            return _sanear_indicadores(original(df))
        except Exception:
            return pd.DataFrame()

    calcular_indicadores_seguro._bottrade_strategy_data_hardening = True
    estrategia_module.calcular_indicadores = calcular_indicadores_seguro
    log.info("[datos] Endurecimiento de indicadores de volumen activo.")
