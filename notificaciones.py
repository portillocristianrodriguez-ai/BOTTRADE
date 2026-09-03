"""
Notificaciones por Telegram.

Si no hay token/chat_id configurados,
no se envían notificaciones.
"""

import logging

import requests

import config


log = logging.getLogger(__name__)


# ============================================================
# TELEGRAM
# ============================================================

def notificar(
    mensaje: str,
):
    """
    Envía un mensaje a Telegram.

    Devuelve:
        True  -> enviado correctamente
        False -> error o configuración incompleta
    """

    # ========================================================
    # COMPROBAR CONFIGURACIÓN
    # ========================================================

    if (
        not config.TELEGRAM_BOT_TOKEN
        or not config.TELEGRAM_CHAT_ID
    ):

        log.warning(
            "[Telegram] "
            "TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID "
            "no están configurados."
        )

        return False

    # ========================================================
    # COMPROBAR MENSAJE
    # ========================================================

    if not mensaje:

        log.warning(
            "[Telegram] "
            "Se intentó enviar un mensaje vacío."
        )

        return False

    try:

        url = (
            "https://api.telegram.org/bot"
            f"{config.TELEGRAM_BOT_TOKEN}"
            "/sendMessage"
        )

        respuesta = requests.post(
            url,
            json={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": str(mensaje),
            },
            timeout=10,
        )

        # ====================================================
        # RESPUESTA HTTP
        # ====================================================

        if respuesta.status_code != 200:

            log.error(
                "[Telegram] "
                f"Error HTTP {respuesta.status_code}: "
                f"{respuesta.text}"
            )

            return False

        # ====================================================
        # RESPUESTA JSON
        # ====================================================

        try:

            datos = respuesta.json()

        except Exception:

            log.error(
                "[Telegram] "
                f"Respuesta no válida: "
                f"{respuesta.text}"
            )

            return False

        # ====================================================
        # OK TELEGRAM
        # ====================================================

        if datos.get("ok") is True:

            log.info(
                "[Telegram] "
                "Notificación enviada correctamente."
            )

            return True

        # ====================================================
        # ERROR TELEGRAM
        # ====================================================

        log.error(
            "[Telegram] "
            f"Telegram rechazó el mensaje: "
            f"{datos}"
        )

        return False

    except requests.exceptions.Timeout:

        log.error(
            "[Telegram] "
            "Timeout esperando respuesta de Telegram."
        )

        return False

    except requests.exceptions.RequestException as e:

        log.error(
            "[Telegram] "
            f"Error de conexión: {e}"
        )

        return False

    except Exception as e:

        log.error(
            "[Telegram] "
            f"Error inesperado: {e}"
        )

        return False
