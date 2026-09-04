"""Entrypoint endurecido para BOTTRADE en Render."""
from __future__ import annotations

import main as bot
import safety_hardening
import worker


if __name__ == "__main__":
    # Instalar antes de worker.main(): así los errores de observación
    # no disparan el circuit breaker y el watchdog universal empieza
    # a vigilar todas las posiciones abiertas.
    safety_hardening.instalar(bot)
    worker.main()
