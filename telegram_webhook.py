"""Recepción Telegram por webhook para Render, evitando conflictos de getUpdates."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import requests

import config
import notificaciones

log = logging.getLogger(__name__)
_SERVER = None
_THREAD = None
_CALLBACK = None
_SECRET = None
_PATH = None


def _secret() -> str:
    token = str(getattr(config, "TELEGRAM_BOT_TOKEN", "") or "")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:48]


def webhook_path() -> str:
    return "/telegram/" + _secret()


def _procesar_update(update: dict) -> None:
    mensaje = update.get("message") or {}
    chat = mensaje.get("chat") or {}
    if str(chat.get("id", "")) != str(getattr(config, "TELEGRAM_CHAT_ID", "")):
        log.warning("[Telegram] Webhook: comando ignorado de chat no autorizado.")
        return
    texto = str(mensaje.get("text", "")).strip()
    if not texto or not texto.startswith("/"):
        return
    comando = texto.split()[0].lower()
    if "@" in comando:
        comando = comando.split("@")[0]
    log.info("[Telegram] Comando recibido por webhook: %s", comando)
    try:
        respuesta = _CALLBACK(comando)
        if respuesta:
            notificaciones.notificar(respuesta)
        else:
            log.warning("[Telegram] El comando %s no devolvió respuesta.", comando)
    except Exception as exc:
        log.error("[Telegram] Error ejecutando %s por webhook: %s", comando, exc)
        notificaciones.notificar(f"❌ Error ejecutando {comando}.")


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        parsed = urlparse(self.path)
        expected_header = str(self.headers.get("X-Telegram-Bot-Api-Secret-Token", ""))
        if parsed.path != _PATH or expected_header != _SECRET:
            self.send_response(404)
            self.end_headers()
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = self.rfile.read(length)
            update = json.loads(payload.decode("utf-8"))
            _procesar_update(update)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        except Exception as exc:
            log.error("[Telegram] Webhook inválido: %s", exc)
            self.send_response(400)
            self.end_headers()

    def log_message(self, format, *args):
        return


def _registrar_webhook_publico() -> bool:
    base = str(os.environ.get("RENDER_EXTERNAL_URL", "") or "").rstrip("/")
    if not base or not config.TELEGRAM_BOT_TOKEN:
        log.warning("[Telegram] Webhook no activado: falta RENDER_EXTERNAL_URL o token.")
        return False
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/setWebhook"
    destino = base + webhook_path()
    try:
        response = requests.post(
            url,
            json={
                "url": destino,
                "secret_token": _secret(),
                "allowed_updates": ["message"],
                "max_connections": 1,
                "drop_pending_updates": False,
            },
            timeout=15,
        )
        response.raise_for_status()
        datos = response.json()
        if not datos.get("ok"):
            log.error("[Telegram] No se pudo registrar webhook: %s", datos)
            return False
        log.info("[Telegram] Webhook activo; getUpdates queda deshabilitado.")
        return True
    except Exception as exc:
        log.error("[Telegram] Error registrando webhook: %s", exc)
        return False


def _desactivar_webhook_legacy() -> bool:
    """Elimina el webhook de una instancia Render que ya no debe recibir Telegram."""
    token = str(getattr(config, "TELEGRAM_BOT_TOKEN", "") or "").strip()
    if not token:
        log.info("[Telegram] Receiver Render legacy desactivado; no hay token para eliminar webhook.")
        return True
    url = f"https://api.telegram.org/bot{token}/deleteWebhook"
    try:
        response = requests.post(
            url,
            json={"drop_pending_updates": False},
            timeout=15,
        )
        response.raise_for_status()
        datos = response.json()
        if not datos.get("ok"):
            log.error("[Telegram] No se pudo eliminar el webhook legacy: %s", datos)
            return False
        log.info("[Telegram] Webhook legacy de Render eliminado; Railway queda como receptor único.")
        return True
    except Exception as exc:
        log.error("[Telegram] Error eliminando webhook legacy: %s", exc)
        return False


def instalar(main_module) -> None:
    """En Render sustituye polling por webhook, salvo cuando Render se ha retirado."""
    global _SERVER, _THREAD, _CALLBACK, _SECRET, _PATH

    if str(os.environ.get("RENDER_DISABLE_TELEGRAM", "")).strip().lower() in {"1", "true", "yes", "si", "sí", "on"}:
        _desactivar_webhook_legacy()
        main_module.log.info("[Telegram] Receiver Telegram de Render desactivado por configuración.")
        return

    if not os.environ.get("RENDER_EXTERNAL_URL") or not config.TELEGRAM_BOT_TOKEN:
        return
    if getattr(notificaciones.iniciar_comandos, "_bottrade_webhook", False):
        return
    original = notificaciones.iniciar_comandos

    def iniciar_comandos_webhook(callback):
        global _SERVER, _THREAD, _CALLBACK, _SECRET, _PATH
        _CALLBACK = callback
        _SECRET = _secret()
        _PATH = webhook_path()
        if _SERVER is None:
            port = int(os.environ.get("BOTTRADE_TELEGRAM_WEBHOOK_INTERNAL_PORT", "18080"))
            _SERVER = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
            _THREAD = threading.Thread(target=_SERVER.serve_forever, daemon=True, name="TelegramWebhook")
            _THREAD.start()
        if _registrar_webhook_publico():
            log.info("[Telegram] Receptor webhook iniciado en %s", _PATH)
            return True
        log.warning("[Telegram] Webhook no disponible; se conserva polling como respaldo.")
        return original(callback)

    iniciar_comandos_webhook._bottrade_webhook = True
    notificaciones.iniciar_comandos = iniciar_comandos_webhook
    main_module.log.info("[Telegram] Modo webhook preparado para Render.")
