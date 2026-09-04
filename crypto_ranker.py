"""Ranking de oportunidades crypto a nivel de cartera."""
from __future__ import annotations

import math


def _num(value, default=0.0):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def _clamp(value, low=0.0, high=100.0):
    return max(low, min(high, _num(value, low)))


def calcular_score_cartera(analisis, volumen_dolar_medio=0.0):
    """Combina señal, momentum, liquidez, volatilidad y régimen sin sustituir el score de entrada."""
    a = analisis or {}
    signal = _clamp(a.get("score", 0))
    momentum = _num(a.get("momentum_pct", 0))
    volume_ratio = _num(a.get("volumen_ratio", 0))
    atr_pct = abs(_num(a.get("atr_pct", 0)))
    adx = _clamp(a.get("adx", 0))
    breakout = 1.0 if a.get("breakout", False) else 0.0
    regime = str(a.get("regimen_local", "neutral")).lower()

    momentum_score = _clamp(50 + momentum * 25, 0, 100)
    volume_score = _clamp(50 + min(volume_ratio, 5) * 10, 0, 100)
    liquidity_score = _clamp(math.log10(max(_num(volumen_dolar_medio), 1.0)) * 12, 0, 100)
    trend_score = _clamp(50 + adx * 0.5 + breakout * 15, 0, 100)

    if regime == "alcista":
        regime_score = 100
    elif regime == "transicion":
        regime_score = 70
    elif regime == "bajista":
        regime_score = 15
    else:
        regime_score = 50

    # Evita premiar volatilidad extrema sin confirmación.
    volatility_score = 100 if 0.004 <= atr_pct <= 0.035 else (65 if atr_pct < 0.004 else 35)

    total = (
        signal * 0.50
        + momentum_score * 0.15
        + volume_score * 0.10
        + liquidity_score * 0.10
        + trend_score * 0.07
        + regime_score * 0.05
        + volatility_score * 0.03
    )
    return round(_clamp(total), 3)


def enriquecer_candidatos(candidatos):
    """Añade portfolio_score y ordena sin eliminar candidatos."""
    enriquecidos = []
    for ticker, df, analisis in candidatos:
        analisis = dict(analisis)
        analisis["portfolio_score"] = calcular_score_cartera(
            analisis,
            analisis.get("volumen_dolar_medio", 0),
        )
        enriquecidos.append((ticker, df, analisis))
    enriquecidos.sort(
        key=lambda item: (
            item[2].get("portfolio_score", 0),
            item[2].get("score", 0),
            item[2].get("volumen_dolar_medio", 0),
        ),
        reverse=True,
    )
    return enriquecidos
