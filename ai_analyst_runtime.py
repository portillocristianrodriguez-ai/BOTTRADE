"""Integración segura del analista de inversión con el runtime de BOTTRADE.

El módulo es deliberadamente desacoplado del broker: recibe snapshots/trades,
calcula diagnóstico y genera propuestas. Aplicar una propuesta solo modifica
parámetros permitidos; nunca llama a submit_order ni cancela/modifica órdenes.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from ai_investment_analyst import AnalystMemory, Proposal, analyze_performance, audit_proposal, make_proposal


DEFAULT_MEMORY_FILE = os.environ.get("AI_ANALYST_MEMORY_FILE", "ai_analyst_memory.jsonl")
DEFAULT_OVERRIDE_FILE = os.environ.get("AI_ANALYST_OVERRIDE_FILE", "ai_analyst_overrides.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _num(value: Any) -> float | None:
    try:
        value = float(value)
        return value if value == value and abs(value) != float("inf") else None
    except (TypeError, ValueError):
        return None


def portfolio_risk(positions: Sequence[Mapping[str, Any]], equity: float | None) -> dict[str, Any]:
    """Calcula exposición y concentración desde posiciones normalizadas."""
    values = []
    for raw in positions:
        value = _num(raw.get("market_value", raw.get("value", raw.get("notional"))))
        if value is None:
            qty = _num(raw.get("qty", raw.get("quantity")))
            price = _num(raw.get("current_price", raw.get("price")))
            if qty is not None and price is not None:
                value = qty * price
        if value is None:
            continue
        values.append((str(raw.get("symbol", raw.get("ticker", "UNKNOWN"))).upper(), value, raw))

    gross = sum(abs(value) for _, value, _ in values)
    concentration = []
    for symbol, value, raw in sorted(values, key=lambda item: abs(item[1]), reverse=True):
        concentration.append({
            "symbol": symbol,
            "market_value": value,
            "portfolio_pct": abs(value) / equity if equity and equity > 0 else None,
            "asset_type": str(raw.get("asset_type", raw.get("type", "unknown"))).lower(),
        })

    by_type: dict[str, float] = {}
    for _, value, raw in values:
        kind = str(raw.get("asset_type", raw.get("type", "unknown"))).lower()
        by_type[kind] = by_type.get(kind, 0.0) + abs(value)

    return {
        "gross_exposure": gross,
        "gross_exposure_pct": gross / equity if equity and equity > 0 else None,
        "largest_position": concentration[0] if concentration else None,
        "concentration": concentration,
        "by_asset_type": {
            kind: {"market_value": value, "portfolio_pct": value / equity if equity and equity > 0 else None}
            for kind, value in by_type.items()
        },
    }


def diagnose(metrics: Mapping[str, Any], risk: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """Produce hallazgos deterministas y explicables, sin afirmar causalidad no observada."""
    findings: list[dict[str, Any]] = []
    trades = int(metrics.get("trades", 0) or 0)
    if trades == 0:
        findings.append({"severity": "info", "code": "NO_TRADES", "message": "No hay suficientes operaciones cerradas para evaluar rendimiento."})
        return findings

    pf = _num(metrics.get("profit_factor"))
    win_rate = _num(metrics.get("win_rate"))
    drawdown = _num(metrics.get("max_drawdown"))
    expectancy = _num(metrics.get("expectancy"))
    if pf is not None and pf < 1.0:
        findings.append({"severity": "critical", "code": "NEGATIVE_EDGE", "message": "El profit factor está por debajo de 1; las pérdidas brutas superan a las ganancias brutas."})
    if expectancy is not None and expectancy < 0:
        findings.append({"severity": "critical", "code": "NEGATIVE_EXPECTANCY", "message": "La esperanza matemática por operación es negativa en la muestra analizada."})
    if drawdown is not None and drawdown <= -0.05:
        findings.append({"severity": "warning", "code": "DRAWDOWN", "message": f"Drawdown máximo de {drawdown:.2%} en la curva de equity suministrada."})
    if win_rate is not None and win_rate < 0.40:
        findings.append({"severity": "warning", "code": "LOW_WIN_RATE", "message": f"Win rate de {win_rate:.2%}; debe interpretarse junto con payoff y profit factor."})
    if risk:
        gross_pct = _num(risk.get("gross_exposure_pct"))
        if gross_pct is not None and gross_pct > 0.80:
            findings.append({"severity": "warning", "code": "HIGH_EXPOSURE", "message": f"Exposición bruta de {gross_pct:.2%} del equity."})
        largest = risk.get("largest_position") or {}
        largest_pct = _num(largest.get("portfolio_pct")) if isinstance(largest, Mapping) else None
        if largest_pct is not None and largest_pct > 0.25:
            findings.append({"severity": "warning", "code": "CONCENTRATION", "message": f"La posición mayor representa {largest_pct:.2%} del equity."})
    if not findings:
        findings.append({"severity": "info", "code": "NO_MAJOR_ALERT", "message": "No se detectó una anomalía de riesgo principal con los datos suministrados."})
    return findings


def simulate_risk_change(metrics: Mapping[str, Any], current_risk_pct: float, proposed_risk_pct: float) -> dict[str, Any]:
    """Simulación conservadora de riesgo: escala pérdidas/ganancias por el ratio de riesgo.

    No es backtest ni predicción de mercado. Solo cuantifica cómo cambiaría el
    P&L histórico si el tamaño de riesgo hubiera escalado proporcionalmente.
    """
    current = float(current_risk_pct)
    proposed = float(proposed_risk_pct)
    if current <= 0 or proposed <= 0:
        raise ValueError("Los riesgos deben ser positivos.")
    ratio = proposed / current
    total_pnl = _num(metrics.get("total_pnl")) or 0.0
    return {
        "method": "historical_linear_risk_scaling",
        "validated": True,
        "sample_trades": int(metrics.get("trades", 0) or 0),
        "risk_ratio": ratio,
        "estimated_total_pnl": total_pnl * ratio,
        "estimated_average_pnl": (_num(metrics.get("expectancy")) or 0.0) * ratio,
        "caveat": "Simulación proporcional; no modela slippage, fills, impacto, cambios de señal ni no linealidades.",
    }


def propose_risk_reduction(metrics: Mapping[str, Any], current_risk_pct: float, *, target_risk_pct: float | None = None) -> Proposal | None:
    trades = int(metrics.get("trades", 0) or 0)
    drawdown = _num(metrics.get("max_drawdown"))
    expectancy = _num(metrics.get("expectancy"))
    if trades < 20 or (drawdown is None or drawdown > -0.05) or (expectancy is not None and expectancy >= 0):
        return None
    current = float(current_risk_pct)
    target = float(target_risk_pct if target_risk_pct is not None else current * 0.75)
    if not 0 < target < current:
        return None
    simulation = simulate_risk_change(metrics, current, target)
    return make_proposal(
        "Reducir riesgo después de drawdown y expectativa negativa observados.",
        {"RISK_PER_TRADE_PCT": target},
        expected_impact="Reducir proporcionalmente el tamaño de pérdidas y ganancias por operación, preservando los límites de seguridad existentes.",
        validation=simulation,
    )


def read_overrides(path: str = DEFAULT_OVERRIDE_FILE) -> dict[str, Any]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return dict(data) if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def write_overrides(changes: Mapping[str, Any], path: str = DEFAULT_OVERRIDE_FILE) -> dict[str, Any]:
    """Persiste solo parámetros previamente validados por el AI gate."""
    current = read_overrides(path)
    current.update(dict(changes))
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".ai_overrides_", dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(current, handle, indent=2, ensure_ascii=False, sort_keys=True)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    return current


class AIAnalystRuntime:
    """Fachada de producción: memoria + análisis + propuestas + auditoría."""

    def __init__(self, memory_path: str = DEFAULT_MEMORY_FILE, override_path: str = DEFAULT_OVERRIDE_FILE):
        self.memory = AnalystMemory(memory_path)
        self.override_path = override_path

    def analyze(self, trades: Sequence[Mapping[str, Any]], equity: Sequence[Any] = (), positions: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
        metrics = analyze_performance(trades, equity)
        equity_now = None
        if equity:
            last = equity[-1]
            equity_now = _num(last if isinstance(last, (int, float)) else last.get("equity"))
        risk = portfolio_risk(positions, equity_now)
        findings = diagnose(metrics, risk)
        report = {"generated_at": _now(), "metrics": metrics, "risk": risk, "findings": findings}
        self.memory.append("analysis", report)
        return report

    def apply(self, proposal: Proposal, token: str, current_config: Mapping[str, Any]) -> dict[str, Any]:
        from ai_investment_analyst import apply_proposal
        result = apply_proposal(proposal, token, current_config)
        write_overrides(proposal.changes, self.override_path)
        audit_proposal(self.memory, proposal, result)
        return result
