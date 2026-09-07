"""Endurece los datos derivados usados por la estrategia sin cambiar reglas de trading.

Corrige métricas de volumen no finitas o matemáticamente no informativas cuando
la media histórica es cero/casi cero. En esos casos el ratio queda neutral (0),
evita rankings absurdos y obliga a que los filtros de volumen fallen de forma
segura en vez de premiar datos corruptos.
"""
from __future__ import annotations

import functools
import logging

import pandas as pd

log = logging.getLogger(__name__)


def _sanear_ratio(serie: pd.Series, media: pd.Series) -> pd.Series:
    from volume_data_hardening import safe_volume_ratio
    return safe_volume_ratio(serie, media).fillna(0.0)


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
    return salida


def instalar(estrategia_module) -> None:
    """Compatibility wrapper; ratios are now validated at their origin."""
    original = getattr(estrategia_module, "calcular_indicadores", None)
    if not callable(original) or getattr(original, "_bottrade_strategy_data_hardening", False):
        return

    @functools.wraps(original)
    def calcular_indicadores_seguro(df):
        try:
            return original(df)
        except Exception:
            return pd.DataFrame()

    calcular_indicadores_seguro._bottrade_strategy_data_hardening = True
    estrategia_module.calcular_indicadores = calcular_indicadores_seguro
    log.info("[datos] Endurecimiento de indicadores de volumen activo.")
