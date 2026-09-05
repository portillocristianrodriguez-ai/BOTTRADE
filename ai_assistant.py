"""Read-only AI analyst for the BOTTRADE dashboard.

The assistant can inspect the same Alpaca/account/strategy data shown by the
terminal and explain statistics or propose strategy experiments. It never
places, cancels, or modifies orders and never mutates strategy configuration.
"""
from __future__ import annotations

import json
import os
from typing import Any

import requests


OPENAI_API_URL = os.environ.get("AI_BASE_URL", "https://api.openai.com/v1/responses").rstrip("/")
AI_MODEL = os.environ.get("AI_MODEL", "gpt-5.6-luna")
AI_TIMEOUT = max(10, int(os.environ.get("AI_TIMEOUT_SECONDS", "45")))


def _strategy_snapshot() -> dict[str, Any]:
    """Expose only non-secret strategy/risk parameters to the analyst."""
    try:
        import config
    except Exception:
        return {}
    names = [
        "STOP_LOSS_PCT",
        "TAKE_PROFIT_PCT",
        "TRAILING_STOP_PCT",
        "ATR_STOP_MULTIPLICADOR",
        "ATR_TAKE_PROFIT_MULTIPLICADOR",
        "ATR_PERIODO",
        "MAX_BUYING_POWER_USAGE_PCT",
        "MAX_POSICIONES_ABIERTAS",
        "MAX_SINGLE_POSITION_PCT",
        "MAX_TOTAL_EXPOSURE_PCT",
        "ORDER_BUYING_POWER_BUFFER",
        "REQUIRE_PROTECTION_FOR_NEW_ENTRIES",
        "WATCHDOG_INTERVAL_SECONDS",
        "CRYPTO_PROTECTION_INTERVAL_SECONDS",
        "DYNAMIC_EXIT_COOLDOWN_SECONDS",
        "DYNAMIC_EXIT_MICROSTRUCTURE_MIN_SAMPLES",
        "DYNAMIC_EXIT_MICROSTRUCTURE_WINDOW_SECONDS",
        "DYNAMIC_EXIT_MICROSTRUCTURE_SCORE_REDUCE",
        "DYNAMIC_EXIT_MICROSTRUCTURE_SCORE_EXIT",
    ]
    out: dict[str, Any] = {}
    for name in names:
        if hasattr(config, name):
            value = getattr(config, name)
            if isinstance(value, (str, int, float, bool)) or value is None:
                out[name] = value
    return out


def _clean_history(history: dict[str, Any]) -> list[dict[str, Any]]:
    points = history.get("points") or []
    # Keep the context bounded while preserving the full shape of the chart.
    if len(points) > 360:
        points = points[-360:]
    return [{"time": p.get("label"), "equity": p.get("equity")} for p in points]


def build_context(snapshot: dict[str, Any], question: str) -> str:
    data = {
        "account": snapshot.get("account", {}),
        "positions": snapshot.get("positions", []),
        "risk": snapshot.get("risk", {}),
        "execution": snapshot.get("execution", {}),
        "open_orders": snapshot.get("open_orders"),
        "orders": snapshot.get("orders", [])[-50:],
        "fills": snapshot.get("fills", [])[-50:],
        "clock": snapshot.get("clock", {}),
        "history": {
            "status": snapshot.get("history", {}).get("status"),
            "return_pct": snapshot.get("history", {}).get("return_pct"),
            "max_drawdown_pct": snapshot.get("history", {}).get("max_drawdown_pct"),
            "peak": snapshot.get("history", {}).get("peak"),
            "points": _clean_history(snapshot.get("history", {})),
        },
        "strategy_parameters": _strategy_snapshot(),
    }
    return json.dumps({"question": question, "data": data}, ensure_ascii=False, separators=(",", ":"))


def _extract_text(payload: dict[str, Any]) -> str:
    # Responses API JSON shape: output -> message -> content -> text.
    chunks: list[str] = []
    for item in payload.get("output", []) or []:
        for content in item.get("content", []) or []:
            text = content.get("text")
            if isinstance(text, str) and text:
                chunks.append(text)
    if chunks:
        return "\n".join(chunks).strip()
    return str(payload.get("output_text") or "").strip()


def ask(snapshot: dict[str, Any], question: str, history: list[dict[str, str]] | None = None) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("IA no configurada: falta OPENAI_API_KEY en Railway. El terminal y sus datos siguen funcionando sin ella.")

    messages: list[dict[str, str]] = []
    for item in (history or [])[-8:]:
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": str(content)[:5000]})

    instructions = (
        "Eres el analista de datos de BOTTRADE. Responde en español, de forma clara y cuantitativa. "
        "Tu trabajo es analizar estadísticas, riesgo, posiciones, ejecuciones, histórico de equity y "
        "parámetros de estrategia que aparecen en los datos. Puedes proponer hipótesis y cambios para "
        "backtesting, pero NO puedes ejecutar operaciones, cambiar parámetros, tocar archivos, ni dar a "
        "entender que has hecho un cambio. Distingue siempre hechos observados de inferencias. Si faltan "
        "datos, dilo. Para evaluar rentabilidad usa retorno, drawdown, frecuencia de operaciones y, cuando "
        "estén disponibles, wins/losses y fills; no inventes métricas. Si propones ajustar SL/TP/trailing, "
        "explica el motivo, el riesgo y qué periodo/backtest habría que comparar antes de aplicarlo. "
        "No pidas ni reveles API keys, secretos o credenciales."
    )
    context = build_context(snapshot, question)
    user_content = "CONTEXTO ACTUAL DEL TERMINAL (fuente Alpaca + configuración no secreta):\n" + context
    messages.append({"role": "user", "content": user_content})

    body = {
        "model": AI_MODEL,
        "instructions": instructions,
        "input": messages,
        "max_output_tokens": 1400,
    }
    response = requests.post(
        OPENAI_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=body,
        timeout=AI_TIMEOUT,
    )
    response.raise_for_status()
    text = _extract_text(response.json())
    if not text:
        raise RuntimeError("La IA no devolvió texto.")
    return text
