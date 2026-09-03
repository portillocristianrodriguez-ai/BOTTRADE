"""Notificaciones por Telegram."""

import logging
import requests
import config

log = logging.getLogger(__name__)


def notificar(mensaje: str):
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        log.warning("[Telegram] Token o Chat ID no configurados.")
        return False

    try:
        # Añadir identificación de la cuenta/bot
        mensaje_final = (
            f"🤖 {config.BOT_NOMBRE}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{mensaje}"
        )

        url = (
            f"https://api.telegram.org/"
            f"bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        )

        respuesta = requests.post(
            url,
            json={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": mensaje_final,
            },
            timeout=10,
        )

        respuesta.raise_for_status()

        datos = respuesta.json()

        if not datos.get("ok"):
            log.error(
                f"[Telegram] Error de API: {datos}"
            )
            return False

        log.info(
            f"[Telegram] Notificación enviada correctamente "
            f"({config.BOT_NOMBRE})."
        )

        return True

    except Exception as e:
        log.warning(
            f"[Telegram] No se pudo enviar notificación: {e}"
        )
        return False
