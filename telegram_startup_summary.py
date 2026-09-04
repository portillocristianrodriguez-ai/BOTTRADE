"""Compacta la notificación de arranque de Telegram sin tocar la lógica de trading."""
from __future__ import annotations

import config
import notificaciones


_original_notificar = notificaciones.notificar


def _notificar_resumido(mensaje, *args, **kwargs):
    try:
        if isinstance(mensaje, str) and mensaje.startswith("🤖 Bot iniciado"):
            mensaje = (
                mensaje.replace(
                    f"Acciones: {', '.join(config.TICKERS) or '(ninguna)'}",
                    f"📈 Universo acciones: {len(config.TICKERS):,} acciones",
                    1,
                )
                if "Acciones:" in mensaje
                else mensaje
            )
            if "₿ Universo crypto:" not in mensaje and "₿ Scanner crypto:" in mensaje:
                mensaje = mensaje.replace(
                    "₿ Scanner crypto:",
                    "₿ Universo crypto: completo\n₿ Scanner crypto:",
                    1,
                )
    except Exception:
        pass
    return _original_notificar(mensaje, *args, **kwargs)


notificaciones.notificar = _notificar_resumido
