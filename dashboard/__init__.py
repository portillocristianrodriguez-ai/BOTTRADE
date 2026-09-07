"""Compatibility package that decorates the existing dashboard without changing trading logic.

Python resolves a regular package before a same-directory module, so the existing
``dashboard.py`` remains the source of truth while this package adds presentation
UX at import time. All dashboard functions/state are re-exported unchanged.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_BASE_PATH = Path(__file__).resolve().parent.parent / "dashboard.py"
_SPEC = importlib.util.spec_from_file_location("_bottrade_dashboard_base", _BASE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"Unable to load dashboard base: {_BASE_PATH}")
_BASE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_BASE)

# Re-export the complete original dashboard API.
for _name, _value in vars(_BASE).items():
    if _name not in {"__name__", "__package__", "__loader__", "__spec__"}:
        globals()[_name] = _value
