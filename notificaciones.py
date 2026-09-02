"""Notificaciones por Telegram (opcional). Si no hay token/chat_id configurados, no hace nada."""

import logging
import requests
import config

log = logging.getLogger(__name__)


def notificar(mensaje: str):
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": config.TELEGRAM_CHAT_ID, "text": mensaje}, timeout=10)
    except Exception as e:
        log.warning(f"No se pudo enviar notificación a Telegram: {e}")
