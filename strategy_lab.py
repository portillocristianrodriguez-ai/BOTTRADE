"""Laboratorio seguro de estrategias para BOTTRADE.

Evalúa candidatos con evidencia histórica/OOS y devuelve una decisión de
promoción auditable. No modifica configuración, no activa estrategias y no
envía órdenes. Cualquier promoción sensible requiere aprobación explícita
externa (p. ej. ``APLICAR``).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class PromotionGate:
    eligible: bool
    score: float
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    action: str = "HOLD"


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number and abs(number) != float("inf") else default


def evaluate_candidate(
    metrics: Mapping[str, Any],
    *,
    min_trades: int = 30,
    min_windows: int = 3,
    min_consistency_pct: float = 60.0,
    min_profit_factor: float = 1.10,
    min_score: float = 10.0,
    max_drawdown_pct: float = -25.0,
    max_oos_degradation_pct: float = 50.0,
) -> PromotionGate:
    """Aplica un gate conservador a evidencia OOS agregada.

    ``oos_degradation_pct`` expresa cuánto cae la métrica de rendimiento OOS
    frente a la referencia/in-sample proporcionada. Un valor ausente no se
    interpreta como aprobado: se marca como advertencia, pero el resto de
    gates sigue siendo obligatorio.
    """
    reasons: list[str] = []
    warnings: list[str] = []
    trades = int(_finite(metrics.get("trades"), 0))
    windows = int(_finite(metrics.get("windows"), 0))
    consistency = _finite(metrics.get("consistency_pct"), 0.0)
    pf = _finite(metrics.get("profit_factor"), 0.0)
    score = _finite(metrics.get("score"), 0.0)
    drawdown = _finite(metrics.get("worst_drawdown_pct"), -100.0)
    degradation = metrics.get("oos_degradation_pct")

    if trades < min_trades:
        reasons.append(f"muestra insuficiente: {trades}<{min_trades}")
    if windows < min_windows:
        reasons.append(f"ventanas OOS insuficientes: {windows}<{min_windows}")
    if consistency < min_consistency_pct:
        reasons.append(f"consistencia OOS insuficiente: {consistency:.1f}%<{min_consistency_pct:.1f}%")
    if pf < min_profit_factor:
        reasons.append(f"profit factor insuficiente: {pf:.2f}<{min_profit_factor:.2f}")
    if score < min_score:
        reasons.append(f"score insuficiente: {score:.2f}<{min_score:.2f}")
    if drawdown < max_drawdown_pct:
        reasons.append(f"drawdown excesivo: {drawdown:.2f}%<{max_drawdown_pct:.2f}%")

    if degradation is None:
        warnings.append("falta degradación OOS vs referencia; requiere revisión antes de promoción")
    elif _finite(degradation, 100.0) > max_oos_degradation_pct:
        reasons.append(
            f"degradación OOS excesiva: {_finite(degradation):.1f}%>{max_oos_degradation_pct:.1f}%"
        )

    eligible = not reasons
    if eligible:
        reasons.append("todos los gates cuantitativos superados")
        action = "REVIEW"
    else:
        action = "HOLD"
    return PromotionGate(eligible, round(score, 4), tuple(reasons), tuple(warnings), action)


def rank_candidates(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Ordena candidatos sin alterar ninguno y adjunta su gate de promoción."""
    ranked: list[dict[str, Any]] = []
    for candidate in candidates:
        gate = evaluate_candidate(candidate)
        row = dict(candidate)
        row["promotion_gate"] = asdict(gate)
        ranked.append(row)
    return sorted(
        ranked,
        key=lambda row: (
            bool(row["promotion_gate"]["eligible"]),
            _finite(row.get("score")),
            _finite(row.get("consistency_pct")),
            _finite(row.get("profit_factor")),
        ),
        reverse=True,
    )


__all__ = ["PromotionGate", "evaluate_candidate", "rank_candidates"]
