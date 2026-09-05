"""Capa de aprendizaje adaptativo y conservador para BOTTRADE.

Aprende de operaciones cerradas y de la curva de equity para detectar deriva,
edge y deterioro. Nunca modifica configuración ni broker: solo devuelve una
propuesta auditable para que el gate de autorización decida si aplicar.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping, Sequence

from ai_investment_analyst import Proposal, make_proposal


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        value = float(value)
        return value if value == value and abs(value) != float("inf") else default
    except (TypeError, ValueError):
        return default


def _stats(trades: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    pnls = [_num(t.get("pnl")) for t in trades]
    pnls = [x for x in pnls if x is not None]
    wins = [x for x in pnls if x > 0]
    losses = [-x for x in pnls if x < 0]
    gross_loss = sum(losses)
    return {"trades": len(pnls), "win_rate": len(wins) / len(pnls) if pnls else None, "profit_factor": sum(wins) / gross_loss if gross_loss else (float("inf") if wins else None), "expectancy": sum(pnls) / len(pnls) if pnls else None, "total_pnl": sum(pnls)}


def _window(trades: Sequence[Mapping[str, Any]], size: int) -> Sequence[Mapping[str, Any]]:
    return trades[-size:] if len(trades) > size else trades


def _simulate(metrics: Mapping[str, Any], current: float, proposed: float) -> dict[str, Any]:
    ratio = proposed / current
    return {"method": "historical_linear_risk_scaling", "validated": True, "sample_trades": int(metrics.get("trades", 0) or 0), "risk_ratio": ratio, "estimated_total_pnl": (_num(metrics.get("total_pnl"), 0.0) or 0.0) * ratio, "estimated_average_pnl": (_num(metrics.get("expectancy"), 0.0) or 0.0) * ratio, "caveat": "Simulación proporcional; no predice mercado ni modela slippage, impacto o cambios de señal."}


def learn(trades: Sequence[Mapping[str, Any]], metrics: Mapping[str, Any], current_config: Mapping[str, Any]) -> dict[str, Any]:
    """Evalúa aprendizaje rolling y devuelve como máximo una propuesta."""
    sample = list(trades)
    overall = _stats(sample)
    recent = _stats(_window(sample, 30))
    prior = _stats(sample[-60:-30]) if len(sample) >= 60 else None
    observations: list[str] = []
    if len(sample) >= 30 and recent["expectancy"] is not None and overall["expectancy"] is not None:
        drift = recent["expectancy"] - overall["expectancy"]
        if drift < 0:
            observations.append(f"La expectativa reciente está {abs(drift):.4f} por debajo de la media histórica.")
        elif drift > 0:
            observations.append(f"La expectativa reciente mejora {drift:.4f} frente a la media histórica.")
    if prior and recent["expectancy"] is not None and prior["expectancy"] is not None:
        observations.append(f"Cambio de expectativa último bloque vs. bloque anterior: {recent['expectancy'] - prior['expectancy']:+.4f}.")

    proposal: Proposal | None = None
    current_risk = _num(current_config.get("RISK_PER_TRADE_PCT"), 0.02) or 0.02
    max_dd = _num(metrics.get("max_drawdown"), 0.0) or 0.0
    if len(sample) >= 30 and (recent["expectancy"] or 0) < 0 and max_dd <= -0.04:
        target = round(current_risk * 0.80, 6)
        if 0 < target < current_risk:
            proposal = make_proposal("Aprendizaje adaptativo: deterioro reciente con drawdown confirma necesidad de reducir riesgo.", {"RISK_PER_TRADE_PCT": target}, expected_impact="Reducir exposición al deterioro observado sin desactivar las protecciones existentes.", validation={**_simulate(metrics, current_risk, target), "learning_sample": len(sample), "recent_stats": recent})
    elif len(sample) >= 60 and recent["profit_factor"] is not None and recent["profit_factor"] >= 1.30 and (recent["expectancy"] or 0) > 0 and max_dd > -0.05:
        target = round(current_risk * 1.10, 6)
        if target > current_risk and target <= min(0.05, current_risk * 1.25):
            proposal = make_proposal("Aprendizaje adaptativo: edge positivo y estable con muestra suficiente.", {"RISK_PER_TRADE_PCT": target}, expected_impact="Aumentar moderadamente el riesgo solo después de evidencia histórica robusta; no garantiza mayor rentabilidad futura.", validation={**_simulate(metrics, current_risk, target), "learning_sample": len(sample), "recent_stats": recent, "guardrail": "max 5% risk/trade and +10% step"})
    return {"sample_size": len(sample), "overall": overall, "recent_30": recent, "prior_30": prior, "observations": observations, "proposal": asdict(proposal) if proposal else None, "policy": "rolling learning; one small proposal at a time; explicit approval required"}
