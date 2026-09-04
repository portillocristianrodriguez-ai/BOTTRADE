"""Endurece la persistencia de estado sin tocar la lógica de trading.

El guardado original usa un único archivo temporal (`bot_state.json.tmp`).
Como varias rutas del bot pueden solicitar un guardado desde hilos distintos,
una carrera entre escritores podía hacer que uno de ellos intentara renombrar
un temporal que ya había sido reemplazado por otro hilo. Este módulo serializa
los guardados y garantiza que el directorio destino exista.
"""
from __future__ import annotations

import functools
import logging
import os
import threading

log = logging.getLogger(__name__)

_lock_guardado = threading.Lock()


def instalar(main_module) -> None:
    """Envuelve `_guardar_estado` para hacer sus escrituras seguras ante carreras."""
    original = getattr(main_module, "_guardar_estado", None)
    if not callable(original) or getattr(original, "_bottrade_persistence_hardening", False):
        return

    @functools.wraps(original)
    def guardar_estado_seguro(*args, **kwargs):
        ruta = getattr(getattr(main_module, "config", None), "STATE_FILE", "bot_state.json")
        try:
            directorio = os.path.dirname(os.path.abspath(os.fspath(ruta)))
            os.makedirs(directorio, exist_ok=True)
        except Exception as exc:
            log.warning("[estado] No se pudo preparar el directorio de persistencia: %s", exc)

        with _lock_guardado:
            return original(*args, **kwargs)

    guardar_estado_seguro._bottrade_persistence_hardening = True
    main_module._guardar_estado = guardar_estado_seguro
    log.info("[estado] Persistencia endurecida: escrituras serializadas.")
