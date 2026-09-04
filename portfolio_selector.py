"""Selección de oportunidades a nivel de cartera.

No envía órdenes. Solo transforma una lista de candidatos en un ranking
más robusto, teniendo en cuenta calidad de señal, volatilidad y redundancia
entre activos.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np


def _f(value, default=0.0):
    try:
        value = float(value)
        return value if np.isfinite(value) else default
    except Exception:
        return default


def _returns(df):
    try:
        close = df["close"].astype(float)
        return close.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    except Exception:
        return None


def _correlacion(a, b):
    ra = _returns(a)
    rb = _returns(b)
    if ra is None or rb is None or len(ra) < 12 or len(rb) < 12:
        return 0.0
    try:
        joined = ra.to_frame("a").join(rb.to_frame("b"), how="inner").dropna()
        if len(joined) < 12:
            return 0.0
        value = float(joined["a"].corr(joined["b"]))
        return value if np.isfinite(value) else 0.0
    except Exception:
        return 0.0


def _calidad(analisis):
    score = _f(analisis.get("score"))
    momentum = _f(analisis.get("momentum_pct"))
    volumen = _f(analisis.get("volumen_ratio"), 1.0)
    atr = _f(analisis.get("atr_pct"))
    breakout = bool(analisis.get("breakout", False))

    # Prima moderada por impulso/flujo y penalización por volatilidad extrema.
    momentum_bonus = min(max(momentum, 0.0), 4.0) * 1.5
    volume_bonus = min(max(volumen - 1.0, 0.0), 3.0) * 1.5
    breakout_bonus = 3.0 if breakout else 0.0
    volatility_penalty = max(0.0, atr - 6.0) * 0.8

    return score + momentum_bonus + volume_bonus + breakout_bonus - volatility_penalty


def seleccionar_oportunidades(
    candidatos: Iterable[tuple],
    max_candidatos: int = 12,
    max_compras: int = 2,
    penalizacion_correlacion: float = 12.0,
):
    """Devuelve candidatos ordenados y diversificados.

    Cada elemento debe ser ``(ticker, df, analisis)``.
    La selección es greedy: primero entra la mejor señal y las siguientes
    pierden puntuación si son muy correlacionadas con las ya seleccionadas.
    """
    candidatos = list(candidatos or [])
    if not candidatos:
        return []

    lim = max(1, int(max_candidatos))
    compras = max(1, int(max_compras))

    preparados = []
    vistos = set()
    for ticker, df, analisis in candidatos:
        simbolo = str(ticker).upper().strip()
        if not simbolo or simbolo in vistos:
            continue
        if df is None or getattr(df, "empty", True):
            continue
        if not isinstance(analisis, dict) or not analisis.get("comprar", False):
            continue
        vistos.add(simbolo)
        base = _calidad(analisis)
        preparados.append([simbolo, df, analisis, base, base])

    preparados.sort(key=lambda x: x[3], reverse=True)
    pool = preparados[:lim]
    seleccionados = []

    while pool and len(seleccionados) < compras:
        mejor = None
        mejor_score = -float("inf")
        for item in pool:
            ticker, df, analisis, base, _ = item
            ajuste = 0.0
            for elegido in seleccionados:
                corr = abs(_correlacion(df, elegido[1]))
                ajuste += penalizacion_correlacion * corr
            final = base - ajuste
            item[4] = final
            if final > mejor_score:
                mejor_score = final
                mejor = item

        if mejor is None:
            break
        seleccionados.append(mejor)
        pool.remove(mejor)

    # Mantener el ranking completo de candidatos, pero con el score de cartera
    # disponible para logging y para que el caller pueda limitar las compras.
    for item in preparados:
        if item not in seleccionados:
            ajuste = sum(
                penalizacion_correlacion * abs(_correlacion(item[1], elegido[1]))
                for elegido in seleccionados
            )
            item[4] = item[3] - ajuste

    preparados.sort(key=lambda x: x[4], reverse=True)
    return [
        (ticker, df, {**analisis, "portfolio_score": float(portfolio_score)})
        for ticker, df, analisis, _, portfolio_score in preparados
    ]
