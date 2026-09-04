"""Motor de decisión para salidas adaptativas de BOTTRADE.

No envía órdenes. Evalúa una posición y devuelve una decisión que la capa
existente de protección puede aplicar de forma controlada.
"""
from __future__ import annotations

import math
from typing import Any


def _num(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, _num(value, low)))


def evaluar_salida(
    pnl_pct: float,
    atr_pct: float,
    momentum_pct: float = 0.0,
    rsi: float = 50.0,
    adx: float = 0.0,
    regimen: str = "neutral",
    breakout: bool = False,
    spread_pct: float | None = None,
    orderbook_imbalance: float | None = None,
    trailing_stop_pct: float = 0.015,
) -> dict[str, Any]:
    """Decide hold/tighten/reduce/exit sin ejecutar ninguna orden.

    La lógica usa confirmaciones múltiples para evitar que una sola lectura
    ruidosa del mercado provoque una salida completa.
    """
    pnl = _num(pnl_pct)
    atr = abs(_num(atr_pct))
    momentum = _num(momentum_pct)
    rsi_value = _num(rsi, 50.0)
    adx_value = _clamp(adx, 0.0, 100.0)
    regime_text = str(regimen or "neutral").lower()
    spread = None if spread_pct is None else abs(_num(spread_pct))
    imbalance = None if orderbook_imbalance is None else _clamp(orderbook_imbalance, -1.0, 1.0)

    result = {
        "action": "hold",
        "reduce_fraction": 0.0,
        "recommended_stop_pct": None,
        "score": 0.0,
        "reasons": [],
    }

    # Pérdida relevante + deterioro confirmado: salida completa.
    if pnl <= -max(0.025, atr * 1.75) and momentum < -0.20:
        result.update(action="exit", reduce_fraction=1.0, score=100.0)
        result["reasons"].append("loss_and_negative_momentum")
        return result

    deterioration = 0.0
    if momentum < -0.15:
        deterioration += 30.0
        result["reasons"].append("negative_momentum")
    if regime_text in {"bajista", "transicion_bajista"}:
        deterioration += 25.0
        result["reasons"].append("bearish_regime")
    if rsi_value < 42:
        deterioration += 15.0
        result["reasons"].append("weak_rsi")
    if adx_value >= 18 and momentum < 0:
        deterioration += 10.0
        result["reasons"].append("trend_confirmed_down")
    if imbalance is not None and imbalance < -0.25:
        deterioration += 15.0
        result["reasons"].append("adverse_orderbook")
    if spread is not None and spread > 0.90:
        deterioration += 10.0
        result["reasons"].append("wide_spread")

    profit = max(0.0, pnl)
    strong_profit = profit >= max(0.012, atr * 0.75)
    very_strong_profit = profit >= max(0.025, atr * 1.50)

    if strong_profit and deterioration >= 45.0:
        result.update(action="reduce", reduce_fraction=0.50, score=deterioration)
        result["reasons"].append("profit_protection")
    elif very_strong_profit and deterioration >= 30.0:
        result.update(action="tighten", score=deterioration)
        result["reasons"].append("tighten_profitable_position")
    elif strong_profit and (regime_text == "alcista" or breakout) and momentum >= 0:
        result.update(action="tighten", score=max(0.0, 20.0 - deterioration))
        result["reasons"].append("protect_profit_while_trend_continues")
    elif deterioration >= 65.0:
        result.update(action="reduce", reduce_fraction=0.35, score=deterioration)
    else:
        result["score"] = round(deterioration, 2)

    # El stop recomendado nunca se hace más holgado que el trailing configurado.
    if result["action"] == "tighten" and profit > 0:
        trail = max(0.0025, abs(_num(trailing_stop_pct, 0.015)))
        result["recommended_stop_pct"] = min(trail, max(0.0025, profit * 0.60))

    return result


__all__ = ["evaluar_salida"]
