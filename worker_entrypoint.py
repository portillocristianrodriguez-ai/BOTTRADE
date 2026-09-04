"""Entrypoint endurecido para BOTTRADE en Render."""
from __future__ import annotations

import main as bot
import safety_hardening
import after_hours_hardening
import telegram_hardening
import worker


if __name__ == "__main__":
    # Instalar antes de worker.main(): los refuerzos quedan activos durante
    # toda la vida del proceso sin modificar la lógica de órdenes.
    safety_hardening.instalar(bot)
    after_hours_hardening.instalar(bot)
    telegram_hardening.instalar(bot)
    worker.main()
