"""Entrypoint endurecido para BOTTRADE en Render."""
from __future__ import annotations

import main as bot
import estrategia
import safety_hardening
import after_hours_hardening
import data_quality_hardening
import persistence_hardening
import strategy_data_hardening
import volume_data_hardening
import telegram_hardening
import telegram_startup_summary
import telegram_webhook
import worker


if __name__ == "__main__":
    # Instalar antes de worker.main(): los refuerzos quedan activos durante
    # toda la vida del proceso sin modificar la lógica de órdenes.
    safety_hardening.instalar(bot)
    after_hours_hardening.instalar(bot)
    data_quality_hardening.instalar(bot)
    persistence_hardening.instalar(bot)
    strategy_data_hardening.instalar(estrategia)
    volume_data_hardening.instalar(estrategia)
    telegram_hardening.instalar(bot)
    telegram_webhook.instalar(bot)
    worker.main()
