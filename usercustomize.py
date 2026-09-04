"""Extensión segura de BOTTRADE cargada por Python después de sitecustomize."""
from __future__ import annotations

import builtins

try:
    import pattern_feedback

    _previous_import = builtins.__import__

    def _import_hook(name, globals=None, locals=None, fromlist=(), level=0):
        module = _previous_import(name, globals, locals, fromlist, level)
        if name.split(".", 1)[0] == "main":
            try:
                pattern_feedback.install(module)
            except Exception:
                pass
        return module

    builtins.__import__ = _import_hook
except Exception:
    pass
