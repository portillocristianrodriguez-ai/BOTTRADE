"""AI analyst and tightly-scoped strategy editor for BOTTRADE.

The analyst reads Alpaca/strategy data. Strategy changes are opt-in: the user
must explicitly prefix a request with ``APLICA:``. Only a whitelist of numeric
strategy parameters can be changed, the requested values are range-validated,
and the change is committed to GitHub so the worker's normal deployment path
and Git history remain the audit trail. No order execution is exposed.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

OPENAI_API_URL = os.environ.get("AI_BASE_URL", "https://api.openai.com/v1/responses").rstrip("/")
AI_MODEL = os.environ.get("AI_MODEL", "gpt-5.5")
AI_TIMEOUT = max(10, int(os.environ.get("AI_TIMEOUT_SECONDS", "45")))
GITHUB_API_URL = os.environ.get("AI_GITHUB_API_URL", "https://api.github.com").rstrip("/")
GITHUB_REPO = os.environ.get("AI_GITHUB_REPO", "portillocristianrodriguez-ai/BOTTRADE")
GITHUB_BRANCH = os.environ.get("AI_GITHUB_BRANCH", "main")
AI_EDIT_ENABLED = os.environ.get("AI_EDIT_ENABLED", "true").strip().lower() in {"1", "true", "yes", "si", "sí", "on"}

EDITABLE = {
    "STOP_LOSS_PCT": (0.001, 0.25), "TAKE_PROFIT_PCT": (0.001, 1.00), "TRAILING_STOP_PCT": (0.001, 0.50),
    "ATR_STOP_MULTIPLICADOR": (0.25, 8.0), "ATR_TAKE_PROFIT_MULTIPLICADOR": (0.25, 12.0), "ATR_PERIODO": (2, 100),
    "RISK_PER_TRADE_PCT": (0.001, 0.20), "MAX_TOTAL_EXPOSURE_PCT": (0.05, 1.00), "MAX_SINGLE_POSITION_PCT": (0.01, 1.00),
    "MAX_BUYING_POWER_USAGE_PCT": (0.10, 1.00), "ORDER_BUYING_POWER_BUFFER": (0.10, 0.99), "DAILY_LOSS_LIMIT_PCT": (0.005, 0.50),
    "EARLY_SIGNAL_MIN_SCORE": (0, 100), "CRYPTO_SCORE_MINIMO": (0, 100), "CRYPTO_MAX_COMPRAS_POR_CICLO": (1, 20),
    "CRYPTO_COOLDOWN_MINUTES": (0, 1440), "DYNAMIC_EXIT_COOLDOWN_SECONDS": (0, 3600),
}


def _strategy_snapshot() -> dict[str, Any]:
    try: import config
    except Exception: return {}
    names = list(EDITABLE) + ["MAX_POSICIONES_ABIERTAS", "REQUIRE_PROTECTION_FOR_NEW_ENTRIES", "WATCHDOG_INTERVAL_SECONDS", "CRYPTO_PROTECTION_INTERVAL_SECONDS", "DYNAMIC_EXIT_MICROSTRUCTURE_MIN_SAMPLES", "DYNAMIC_EXIT_MICROSTRUCTURE_WINDOW_SECONDS", "DYNAMIC_EXIT_MICROSTRUCTURE_SCORE_REDUCE", "DYNAMIC_EXIT_MICROSTRUCTURE_SCORE_EXIT"]
    return {name: getattr(config, name) for name in names if hasattr(config, name) and isinstance(getattr(config, name), (str, int, float, bool, type(None)))}


def _clean_history(history: dict[str, Any]) -> list[dict[str, Any]]:
    points = (history or {}).get("points") or []
    if len(points) > 360: points = points[-360:]
    return [{"time": p.get("label"), "equity": p.get("equity")} for p in points]


def build_context(snapshot: dict[str, Any], question: str) -> str:
    data = {"account": snapshot.get("account", {}), "positions": snapshot.get("positions", []), "risk": snapshot.get("risk", {}), "execution": snapshot.get("execution", {}), "open_orders": snapshot.get("open_orders"), "orders": snapshot.get("orders", [])[-50:], "fills": snapshot.get("fills", [])[-50:], "clock": snapshot.get("clock", {}), "history": {"status": snapshot.get("history", {}).get("status"), "return_pct": snapshot.get("history", {}).get("return_pct"), "max_drawdown_pct": snapshot.get("history", {}).get("max_drawdown_pct"), "peak": snapshot.get("history", {}).get("peak"), "points": _clean_history(snapshot.get("history", {}))}, "strategy_parameters": _strategy_snapshot()}
    return json.dumps({"question": question, "data": data}, ensure_ascii=False, separators=(",", ":"))


def _extract_text(payload: dict[str, Any]) -> str:
    chunks = []
    for item in payload.get("output", []) or []:
        for content in item.get("content", []) or []:
            if isinstance(content.get("text"), str) and content["text"]: chunks.append(content["text"])
    return "\n".join(chunks).strip() or str(payload.get("output_text") or "").strip()


def _openai(question: str, context: str, history: list[dict[str, str]] | None = None, *, edit_mode: bool = False) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key: raise RuntimeError("IA no configurada: falta OPENAI_API_KEY en Railway.")
    messages = []
    for item in (history or [])[-8:]:
        role, content = item.get("role"), item.get("content")
        if role in {"user", "assistant"} and content: messages.append({"role": role, "content": str(content)[:5000]})
    instructions = "Eres el analista de BOTTRADE. Responde en español, separa hechos de inferencias, analiza equity, drawdown, riesgo, posiciones, ejecuciones, histórico y parámetros, y no inventes métricas. No pidas ni reveles secretos. "
    if edit_mode:
        instructions += "El usuario ha dado permiso explícito porque su mensaje empieza por APLICA:. Devuelve SOLO JSON con {\"changes\":[{\"name\":\"PARAMETRO\",\"value\":0.0}],\"reason\":\"...\"}. Usa solo los parámetros permitidos que aparecen en EDITABLE. No cambies código, credenciales, ejecución ni protecciones de seguridad."
    else: instructions += "Puedes proponer cambios para backtesting, pero no afirmes haber aplicado ninguno."
    messages.append({"role": "user", "content": "CONTEXTO ACTUAL:\n" + context})
    body: dict[str, Any] = {"model": AI_MODEL, "instructions": instructions, "input": messages, "max_output_tokens": 1400}
    if edit_mode:
        body["text"] = {"format": {"type": "json_schema", "name": "strategy_change", "strict": True, "schema": {"type": "object", "properties": {"changes": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "value": {"type": "number"}}, "required": ["name", "value"], "additionalProperties": False}}, "reason": {"type": "string"}}, "required": ["changes", "reason"], "additionalProperties": False}}}
    response = requests.post(OPENAI_API_URL, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json=body, timeout=AI_TIMEOUT)
    response.raise_for_status()
    return _extract_text(response.json())


def _github_get_config() -> tuple[str, str]:
    token = os.environ.get("BOTTRADE_AI_GITHUB_TOKEN", "").strip()
    if not token: raise RuntimeError("Falta BOTTRADE_AI_GITHUB_TOKEN para permitir cambios de estrategia.")
    r = requests.get(f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/contents/config.py?ref={GITHUB_BRANCH}", headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}, timeout=AI_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    import base64
    return base64.b64decode(data["content"]).decode("utf-8"), data["sha"]


def _apply_changes(changes: list[dict[str, Any]], reason: str) -> str:
    if not AI_EDIT_ENABLED: raise RuntimeError("Los cambios de estrategia por IA están desactivados (AI_EDIT_ENABLED=false).")
    config_text, sha = _github_get_config()
    applied = []
    for change in changes:
        name = str(change.get("name", "")); value = change.get("value")
        if name not in EDITABLE: raise ValueError(f"Parámetro no permitido por la IA: {name}")
        if not isinstance(value, (int, float)) or isinstance(value, bool): raise ValueError(f"Valor inválido para {name}")
        low, high = EDITABLE[name]
        if not (low <= float(value) <= high): raise ValueError(f"Valor fuera de rango para {name}: {value}")
        literal = str(int(value)) if float(value).is_integer() else str(value)
        config_text, count = re.subn(rf"(?m)^{re.escape(name)}\s*=\s*[^\n]+$", f"{name} = {literal}", config_text, count=1)
        if count != 1: raise RuntimeError(f"No se encontró exactamente una definición de {name} en config.py")
        applied.append(f"{name}={literal}")
    import base64
    encoded = base64.b64encode(config_text.encode("utf-8")).decode("ascii")
    token = os.environ["BOTTRADE_AI_GITHUB_TOKEN"].strip()
    r = requests.put(f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/contents/config.py", headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}, json={"message": "ai: apply approved strategy change", "content": encoded, "sha": sha, "branch": GITHUB_BRANCH}, timeout=AI_TIMEOUT)
    r.raise_for_status()
    commit = r.json().get("commit", {}).get("sha", "unknown")
    return f"Cambio aplicado y registrado en GitHub. {', '.join(applied)}. Commit: {commit[:12]}. Motivo: {reason}"


def ask(snapshot: dict[str, Any], question: str, history: list[dict[str, str]] | None = None) -> str:
    context = build_context(snapshot, question)
    if question.strip().upper().startswith("APLICA:"):
        if not AI_EDIT_ENABLED: return "El modo de cambios está desactivado. Activa AI_EDIT_ENABLED=true y configura BOTTRADE_AI_GITHUB_TOKEN en Railway."
        raw = _openai(question, context, history, edit_mode=True)
        try: plan = json.loads(raw)
        except json.JSONDecodeError as exc: raise RuntimeError("La IA no devolvió un plan de cambio válido.") from exc
        changes = plan.get("changes") or []
        if not changes: return "La IA no encontró un cambio concreto y seguro que aplicar."
        return _apply_changes(changes, str(plan.get("reason") or "Sin motivo indicado"))
    return _openai(question, context, history, edit_mode=False)
