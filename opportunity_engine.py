"""Motor puro de oportunidad para BOTTRADE.

Convierte señales ya calculadas en un score auditable 0-100. No envía órdenes,
no modifica configuración y no sustituye los guards de riesgo.
"""
from __future__ import annotations

import math
from typing import Any, Mapping


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _num(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def evaluate(signal: Mapping[str, Any], regime: Mapping[str, Any] | None = None,
             execution: Mapping[str, Any] | None = None,
             portfolio: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Evalúa una oportunidad sin tomar ninguna acción de broker.

    La puntuación parte del score de estrategia y aplica ajustes pequeños,
    explícitos y acotados por régimen, volatilidad, liquidez, correlación y
    calidad de datos. Un resultado ``blocked`` siempre es conservador.
    """
    regime = regime or {}
    execution = execution or {}
    portfolio = portfolio or {}

    base = _clamp(_num(signal.get("score"), 0.0))
    score = base
    adjustments: dict[str, float] = {}

    regime_name = str(regime.get("regimen", "neutral")).lower()
    regime_adj = {
        "alcista": 6.0,
        "transicion_alcista": 2.0,
        "neutral": 0.0,
        "transicion_bajista": -6.0,
        "bajista": -14.0,
    }.get(regime_name, 0.0)
    adjustments["regime"] = regime_adj
    score += regime_adj

    atr_pct = max(0.0, _num(signal.get("atr_pct")))
    volatility_penalty = _clamp(max(0.0, atr_pct - 0.06) * 35.0, 0.0, 12.0)
    adjustments["volatility"] = -volatility_penalty
    score -= volatility_penalty

    spread_pct = max(0.0, _num(execution.get("spread_pct")))
    spread_limit = max(0.01, _num(execution.get("max_spread_pct"), 0.90))
    spread_penalty = _clamp((spread_pct / spread_limit) * 8.0, 0.0, 8.0)
    if execution.get("spread_pct") is None:
        spread_penalty = 0.0
    adjustments["spread"] = -spread_penalty
    score -= spread_penalty

    depth_ratio = _num(execution.get("depth_ratio"), 0.0)
    depth_penalty = _clamp(max(0.0, depth_ratio - 0.35) * 12.0, 0.0, 8.0)
    adjustments["depth"] = -depth_penalty
    score -= depth_penalty

    correlation = abs(_num(portfolio.get("correlation"), 0.0))
    correlation_penalty = _clamp(correlation * 10.0, 0.0, 10.0)
    adjustments["correlation"] = -correlation_penalty
    score -= correlation_penalty

    data_quality = _clamp(_num(signal.get("data_quality"), 1.0), 0.0, 1.0)
    quality_penalty = (1.0 - data_quality) * 15.0
    adjustments["data_quality"] = -quality_penalty
    score -= quality_penalty

    score = round(_clamp(score), 2)
    hard_block = bool(signal.get("data_invalid")) or bool(execution.get("blocked")) or execution.get("ok") is False
    if regime_name == "bajista" and base < 84.0:
        hard_block = True

    minimum = _clamp(_num(signal.get("minimum_opportunity_score"), 70.0), 0.0, 100.0)
    eligible = not hard_block and score >= minimum

    return {
        "score": score,
        "base_score": base,
        "eligible": eligible,
        "blocked": hard_block,
        "regime": regime_name,
        "minimum_score": minimum,
        "adjustments": adjustments,
        "reason": "ok" if eligible else ("hard_block" if hard_block else "insufficient_edge"),
        "policy": "decision metadata only; risk/execution guards remain authoritative",
    }
