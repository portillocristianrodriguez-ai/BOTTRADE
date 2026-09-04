"""Capa pasiva de evaluación para el motor de patrones.

No genera señales ni envía órdenes. Completa, con observaciones posteriores,
los resultados forward de las observaciones ya almacenadas. Se instala de forma
transparente desde usercustomize.py para no modificar el flujo de ejecución.
"""
from __future__ import annotations

import json
import math
import os
import threading
from datetime import datetime, timezone

_LOCK = threading.RLock()
_INSTALLED = False


def _parse_ts(value):
    try:
        if not value:
            return None
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _finite(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _resolve_records(ticker, current_price, now, config_module):
    """Resuelve observaciones antiguas usando solo una observación posterior.

    Una observación se considera válida para un horizonte cuando la siguiente
    observación disponible del mismo ticker ocurre después de dicho horizonte.
    Nunca mira barras futuras desde el momento de la observación.
    """
    path = getattr(config_module, "PATTERN_DATA_FILE", "pattern_observations.jsonl")
    if not os.path.exists(path):
        return 0

    horizons = getattr(config_module, "PATTERN_FORWARD_HORIZONS_MINUTES", [5, 15, 30, 60])
    try:
        horizons = sorted({int(x) for x in horizons if int(x) > 0})
    except Exception:
        horizons = [5, 15, 30, 60]

    now_dt = _parse_ts(now)
    price_now = _finite(current_price)
    if now_dt is None or price_now is None or price_now <= 0:
        return 0

    try:
        with open(path, "r", encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh if line.strip()]
    except Exception:
        return 0

    changed = 0
    target_ticker = str(ticker).upper()

    for row in rows:
        if not isinstance(row, dict) or str(row.get("ticker", "")).upper() != target_ticker:
            continue
        ts = _parse_ts(row.get("timestamp_utc"))
        entry = _finite(row.get("price"))
        if ts is None or entry is None or entry <= 0 or ts >= now_dt:
            continue

        results = row.get("future_returns")
        if not isinstance(results, dict):
            results = {}
            row["future_returns"] = results

        elapsed_minutes = (now_dt - ts).total_seconds() / 60.0
        for horizon in horizons:
            key = str(horizon)
            if key in results:
                continue
            if elapsed_minutes + 1e-9 < horizon:
                continue
            result_pct = ((price_now - entry) / entry) * 100.0
            results[key] = {
                "return_pct": round(result_pct, 6),
                "resolved_at_utc": now_dt.isoformat(),
                "resolution_price": price_now,
                "status": "resolved",
            }
            changed += 1

        if changed:
            row["forward_status"] = "resolved"
            row["forward_last_update_utc"] = now_dt.isoformat()

    if not changed:
        return 0

    temporary = path + ".tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        os.replace(temporary, path)
        return changed
    except Exception:
        try:
            if os.path.exists(temporary):
                os.remove(temporary)
        except Exception:
            pass
        return 0


def install(main_module):
    """Instala la capa de feedback sin alterar señales ni ejecución."""
    global _INSTALLED
    if _INSTALLED:
        return
    original = getattr(main_module, "registrar_observacion_pattern", None)
    if not callable(original):
        return
    if getattr(original, "_pattern_feedback_wrapped", False):
        _INSTALLED = True
        return

    def wrapped(ticker, df, analisis_scanner=None, senal=None):
        result = original(ticker, df, analisis_scanner, senal)
        try:
            if df is not None and not getattr(df, "empty", True):
                row = df.iloc[-1]
                price = row.get("close")
                now = datetime.now(timezone.utc).isoformat()
                with _LOCK:
                    resolved = _resolve_records(ticker, price, now, main_module.config)
                if resolved:
                    main_module.log.info(
                        "[patrones-feedback] %s: %s resultados forward resueltos",
                        ticker,
                        resolved,
                    )
        except Exception as exc:
            main_module.log.debug("[patrones-feedback] %s: feedback omitido: %s", ticker, exc)
        return result

    wrapped._pattern_feedback_wrapped = True
    main_module.registrar_observacion_pattern = wrapped
    _INSTALLED = True
