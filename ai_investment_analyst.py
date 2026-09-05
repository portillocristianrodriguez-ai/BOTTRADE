"""Motor seguro de análisis, memoria y propuestas para BOTTRADE.

Este módulo es deliberadamente independiente del broker: analizar y proponer no
puede enviar órdenes. La aplicación debe llamar a ``apply_proposal`` únicamente
tras una autorización explícita del usuario y pasar por una lista de parámetros
permitidos.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Iterable, Mapping, Sequence


ALLOWED_PARAMETER_GROUPS = {
    "strategy": {"EMA_RAPIDA", "EMA_LENTA", "EMA_TENDENCIA", "RSI_PERIODO", "RSI_SOBRECOMPRA", "RSI_SOBREVENTA", "CRYPTO_SCORE_MINIMO"},
    "risk": {"RISK_PER_TRADE_PCT", "CRYPTO_RISK_PER_TRADE_PCT", "MAX_TOTAL_EXPOSURE_PCT", "MAX_SINGLE_POSITION_PCT"},
    "exit": {"STOP_LOSS_PCT", "TAKE_PROFIT_PCT", "TRAILING_STOP_PCT", "ATR_STOP_MULTIPLICADOR", "ATR_TAKE_PROFIT_MULTIPLICADOR"},
    "exposure": {"MAX_POSICIONES_ABIERTAS", "CRYPTO_MAX_NOTIONAL_PCT", "CRYPTO_MAX_ORDER_NOTIONAL_USD"},
    "filters": {"CRYPTO_MIN_MOMENTUM_PCT", "CRYPTO_VOLUME_MIN_MULTIPLICADOR", "CRYPTO_RSI_MIN", "CRYPTO_RSI_MAX"},
}
ALLOWED_PARAMETERS = frozenset().union(*ALLOWED_PARAMETER_GROUPS.values())


def _num(value: Any) -> float | None:
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _pct(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def _max_drawdown(equity: Sequence[float]) -> float:
    if not equity:
        return 0.0
    peak = float(equity[0])
    worst = 0.0
    for value in equity:
        value = float(value)
        if value > peak:
            peak = value
        if peak > 0:
            worst = min(worst, (value - peak) / peak)
    return worst


def _profit_factor(pnls: Sequence[float]) -> float | None:
    gains = sum(x for x in pnls if x > 0)
    losses = -sum(x for x in pnls if x < 0)
    if losses == 0:
        return math.inf if gains > 0 else None
    return gains / losses


def analyze_performance(
    trades: Iterable[Mapping[str, Any]] = (),
    equity: Iterable[Mapping[str, Any] | float] = (),
    *,
    risk_per_trade: float | None = None,
) -> dict[str, Any]:
    """Calcula métricas auditables sin depender de Alpaca ni enviar órdenes.

    Cada trade puede contener pnl/profit_loss, symbol/ticker, asset_type,
    entry_price, exit_price, risk_amount, stop_loss, take_profit y timestamps.
    Equity acepta números o dicts con ``equity`` y ``timestamp``.
    """
    normalized = []
    for raw in trades:
        pnl = _num(raw.get("pnl", raw.get("profit_loss", raw.get("realized_pnl"))))
        if pnl is None:
            continue
        item = dict(raw)
        item["pnl"] = pnl
        item["symbol"] = str(raw.get("symbol", raw.get("ticker", "UNKNOWN"))).upper()
        item["asset_type"] = str(raw.get("asset_type", raw.get("type", "unknown"))).lower()
        normalized.append(item)

    pnls = [x["pnl"] for x in normalized]
    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x < 0]
    total = sum(pnls)
    avg = mean(pnls) if pnls else 0.0
    win_rate = _pct(len(wins), len(pnls))

    eq_values = []
    for point in equity:
        value = point if isinstance(point, (int, float)) else point.get("equity")
        value = _num(value)
        if value is not None:
            eq_values.append(value)

    by_asset: dict[str, dict[str, Any]] = {}
    groups: dict[str, list[float]] = defaultdict(list)
    for trade in normalized:
        groups[trade["symbol"]].append(trade["pnl"])
    for symbol, values in groups.items():
        w = sum(x > 0 for x in values)
        by_asset[symbol] = {
            "trades": len(values),
            "pnl": round(sum(values), 8),
            "win_rate": _pct(w, len(values)),
            "profit_factor": _profit_factor(values),
            "expectancy": mean(values),
        }

    by_type: dict[str, dict[str, Any]] = {}
    type_groups: dict[str, list[float]] = defaultdict(list)
    for trade in normalized:
        type_groups[trade["asset_type"]].append(trade["pnl"])
    for asset_type, values in type_groups.items():
        by_type[asset_type] = {
            "trades": len(values),
            "pnl": round(sum(values), 8),
            "win_rate": _pct(sum(x > 0 for x in values), len(values)),
            "profit_factor": _profit_factor(values),
            "expectancy": mean(values),
        }

    risk_values = [_num(x.get("risk_amount", x.get("risk"))) for x in normalized]
    risk_values = [x for x in risk_values if x is not None and x > 0]
    realized_risk = mean(risk_values) if risk_values else risk_per_trade
    r_multiples = [t["pnl"] / t["risk_amount"] for t in normalized if _num(t.get("risk_amount")) not in (None, 0)]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trades": len(pnls),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "total_pnl": total,
        "gross_profit": sum(wins),
        "gross_loss": sum(losses),
        "profit_factor": _profit_factor(pnls),
        "expectancy": avg,
        "average_win": mean(wins) if wins else None,
        "average_loss": mean(losses) if losses else None,
        "max_drawdown": _max_drawdown(eq_values),
        "risk_per_trade": realized_risk,
        "average_r_multiple": mean(r_multiples) if r_multiples else None,
        "by_asset": by_asset,
        "by_asset_type": by_type,
    }


@dataclass(frozen=True)
class Proposal:
    proposal_id: str
    created_at: str
    reason: str
    expected_impact: str
    validation: dict[str, Any]
    changes: dict[str, Any]
    reversible: bool = True
    status: str = "PENDING_APPROVAL"


def make_proposal(reason: str, changes: Mapping[str, Any], *, expected_impact: str, validation: Mapping[str, Any] | None = None) -> Proposal:
    """Construye una propuesta, rechazando parámetros fuera de la allowlist."""
    invalid = sorted(set(changes) - ALLOWED_PARAMETERS)
    if invalid:
        raise ValueError(f"Parámetros no permitidos por el AI gate: {', '.join(invalid)}")
    if not changes:
        raise ValueError("Una propuesta debe contener al menos un cambio.")
    return Proposal(
        proposal_id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc).isoformat(),
        reason=str(reason),
        expected_impact=str(expected_impact),
        validation=dict(validation or {}),
        changes=dict(changes),
    )


def authorize_proposal(proposal: Proposal, approval_phrase: str) -> str:
    """Genera un token de autorización explícita; no modifica configuración."""
    if proposal.status != "PENDING_APPROVAL":
        raise ValueError("La propuesta ya no está pendiente de aprobación.")
    if str(approval_phrase).strip().upper() != "APLICAR":
        raise PermissionError("Se requiere aprobación explícita con la palabra APLICAR.")
    payload = f"{proposal.proposal_id}|{proposal.created_at}|{proposal.changes}".encode()
    return hashlib.sha256(payload).hexdigest()


def apply_proposal(proposal: Proposal, token: str, current_config: Mapping[str, Any]) -> dict[str, Any]:
    """Aplica solo cambios autorizados a una copia de configuración.

    No toca el broker. El llamador decide cuándo persistir esta copia y debe
    conservar el snapshot retornado para rollback.
    """
    expected = authorize_proposal(proposal, "APLICAR")
    if not token or not __import__("hmac").compare_digest(expected, token):
        raise PermissionError("Token de autorización inválido.")
    updated = dict(current_config)
    before = {key: updated.get(key) for key in proposal.changes}
    updated.update(proposal.changes)
    return {"config": updated, "rollback": before, "proposal_id": proposal.proposal_id}


class AnalystMemory:
    """Memoria append-only en JSONL para decisiones y contexto del analista."""

    def __init__(self, path: str):
        self.path = path

    def append(self, kind: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "kind": str(kind),
            "payload": dict(payload),
        }
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return record

    def recent(self, *, kind: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if limit < 1:
            return []
        if not os.path.exists(self.path):
            return []
        records = []
        with open(self.path, "r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if kind is None or record.get("kind") == kind:
                    records.append(record)
        return records[-limit:]


def audit_proposal(memory: AnalystMemory, proposal: Proposal, result: Mapping[str, Any]) -> dict[str, Any]:
    return memory.append("proposal_audit", {"proposal": asdict(proposal), "result": dict(result)})
