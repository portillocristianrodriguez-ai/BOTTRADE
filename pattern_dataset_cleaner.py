"""Limpieza segura del dataset de observaciones de patrones."""
from __future__ import annotations

import json
import math
import os


def _valid_number(value):
    try:
        return math.isfinite(float(value)) and float(value) >= 0.0
    except (TypeError, ValueError):
        return False


def limpiar(config_module):
    path = getattr(config_module, "PATTERN_DATA_FILE", "pattern_observations.jsonl")
    if not os.path.exists(path):
        return 0

    try:
        with open(path, "r", encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh if line.strip()]
    except Exception:
        return 0

    changed = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in ("volumen_ratio", "aceleracion_volumen", "volume_ratio", "volume_ratio_short"):
            if key in row and not _valid_number(row.get(key)):
                row[key] = None
                changed += 1
        # Un ratio positivo pero generado sin referencia fiable debe quedar
        # marcado como no disponible si el registro conserva esa evidencia.
        for mean_key in ("volumen_media", "volumen_media_corta"):
            if mean_key in row and not _valid_number(row.get(mean_key)) or (mean_key in row and float(row.get(mean_key)) <= 0):
                if row.get(mean_key) is not None:
                    row[mean_key] = None
                    changed += 1

    if not changed:
        return 0
    temp = path + ".clean.tmp"
    try:
        with open(temp, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        os.replace(temp, path)
        return changed
    except Exception:
        try:
            os.remove(temp)
        except OSError:
            pass
        return 0
