"""Limpieza segura del dataset de observaciones de patrones."""
from __future__ import annotations

import json
import math
import os


_MIN_REFERENCE_VOLUME = 1e-12
_MAX_NUMERIC_RATIO = 1_000_000.0
_RATIO_KEYS = ("volumen_ratio", "aceleracion_volumen", "volume_ratio", "volume_ratio_short")
_MEAN_KEYS = ("volumen_media", "volumen_media_corta")


def _valid_number(value):
    try:
        number = float(value)
        return math.isfinite(number) and number >= 0.0
    except (TypeError, ValueError):
        return False


def _valid_ratio(value):
    if not _valid_number(value):
        return False
    return float(value) <= _MAX_NUMERIC_RATIO


def _valid_mean(value):
    try:
        number = float(value)
        return math.isfinite(number) and number > _MIN_REFERENCE_VOLUME
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

        for key in _RATIO_KEYS:
            if key in row and not _valid_ratio(row.get(key)):
                if row.get(key) is not None:
                    row[key] = None
                    changed += 1

        for key in _MEAN_KEYS:
            if key in row and row.get(key) is not None and not _valid_mean(row.get(key)):
                row[key] = None
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
