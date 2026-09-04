"""Evita un bucle de errores Telegram cuando faltan credenciales.

No toca notificaciones ni trading. Si TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no
están configurados, se desactiva únicamente el polling de comandos. Al añadir
las variables válidas en Render, el polling vuelve a quedar disponible.
"""
from __future__ import annotations

import os


def instalar(main_module):
    token = str(getattr(main_module.config, "TELEGRAM_BOT_TOKEN", "") or "").strip()
    chat_id = str(getattr(main_module.config, "TELEGRAM_CHAT_ID", "") or "").strip()

    if token and chat_id:
        main_module.log.info("[Telegram] Credenciales presentes; comandos habilitados.")
        return

    os.environ["TELEGRAM_COMMANDS_ENABLED"] = "false"
    main_module.log.info(
        "[Telegram] Comandos desactivados: faltan TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID. "
        "Las notificaciones no se modifican."
    )
