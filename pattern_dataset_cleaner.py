"""Repair only invalid fields, preserving records and an exact backup."""
from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path

_MIN_REFERENCE_VOLUME = 1e-12
_MAX_NUMERIC_RATIO = 1_000_000.0
_RATIO_KEYS = ("volumen_ratio", "aceleracion_volumen", "volume_ratio", "volume_ratio_short")
_MEAN_KEYS = ("volumen_media", "volumen_media_corta")


def _valid_number(value):
    try:
        return math.isfinite(float(value)) and float(value) >= 0
    except (TypeError, ValueError):
        return False


def _valid_ratio(value):
    return _valid_number(value) and float(value) <= _MAX_NUMERIC_RATIO


def _valid_mean(value):
    return _valid_number(value) and float(value) > _MIN_REFERENCE_VOLUME


def sanitize_record(row):
    """Sanitize nested metrics in place, leaving valid fields untouched."""
    changed = 0
    if isinstance(row, list):
        return sum(sanitize_record(item) for item in row)
    if not isinstance(row, dict):
        return 0
    for key, value in row.items():
        invalid = (key in _RATIO_KEYS and not _valid_ratio(value)) or (key in _MEAN_KEYS and not _valid_mean(value))
        # A known invalid reference invalidates its associated ratio too.
        mean_key = {"volume_ratio": "volumen_media", "volumen_ratio": "volumen_media", "aceleracion_volumen": "volumen_media_corta", "volume_ratio_short": "volumen_media_corta"}.get(key)
        if mean_key in row and not _valid_mean(row[mean_key]):
            invalid = True
        if isinstance(value, float) and not math.isfinite(value):
            invalid = True
        if invalid and value is not None:
            row[key] = None
            changed += 1
        else:
            changed += sanitize_record(value)
    return changed


def limpiar(config_module):
    """Run with the writer stopped (also used before worker startup).

    Malformed lines are preserved verbatim for manual recovery; they do not
    prevent repair of other lines. An exclusive backup precedes atomic replace.
    """
    path = Path(getattr(config_module, "PATTERN_DATA_FILE", "pattern_observations.jsonl"))
    if not path.exists():
        return 0
    original = path.read_bytes()
    changed = 0
    lines = []
    for line in original.splitlines(keepends=True):
        try:
            row = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            lines.append(line)
            continue
        count = sanitize_record(row)
        changed += count
        lines.append((json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n").encode() if count else line)
    if not changed:
        return 0
    backup_fd, backup = tempfile.mkstemp(prefix=path.name + ".backup-", dir=path.parent)
    with os.fdopen(backup_fd, "wb") as fh:
        fh.write(original)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".clean-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(b"".join(lines))
            fh.flush()
            os.fsync(fh.fileno())
        if path.read_bytes() != original:
            raise RuntimeError("Dataset changed during cleanup; stop the writer and retry")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return changed


if __name__ == "__main__":
    import argparse
    from types import SimpleNamespace
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Dataset path; stop its writer first")
    args = parser.parse_args()
    print(limpiar(SimpleNamespace(PATTERN_DATA_FILE=args.path)))
