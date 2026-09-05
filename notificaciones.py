"""
Notificaciones y comandos por Telegram.
"""

import logging
import os
import threading
import time

import requests

import config


log = logging.getLogger(__name__)

_comandos_lock = threading.Lock()
_comandos_iniciado = False
_lockfile_fd = None
TELEGRAM_MAX_MESSAGE = 4096


def _receptor_telegram_deshabilitado() -> bool:
    """Evita que servicios retirados compitan por el receptor de Telegram."""
    valores = (
        os.environ.get("TELEGRAM_DISABLE_RECEIVER", ""),
        os.environ.get("RENDER_DISABLE_TELEGRAM", ""),
    )
    return any(
        str(valor).strip().lower()
        in {"1", "true", "yes", "si", "sí", "on"}
        for valor in valores
    )


def notificar(mensaje: str):
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        log.warning("[Telegram] Token o Chat ID no configurados.")
        return False
    if not mensaje:
        log.warning("[Telegram] Se intentó enviar un mensaje vacío.")
        return False
    try:
        mensaje_final = (
            f"🤖 {config.BOT_NOMBRE}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{mensaje}"
        )
        if len(mensaje_final) > TELEGRAM_MAX_MESSAGE:
            aviso = "\n\n⚠️ Mensaje truncado por límite de Telegram."
            limite = TELEGRAM_MAX_MESSAGE - len(aviso)
            mensaje_final = mensaje_final[:limite] + aviso
            log.warning(
                "[Telegram] Mensaje demasiado largo; truncado a %s caracteres.",
                TELEGRAM_MAX_MESSAGE,
            )
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        respuesta = requests.post(
            url,
            json={"chat_id": config.TELEGRAM_CHAT_ID, "text": mensaje_final},
            timeout=10,
        )
        respuesta.raise_for_status()
        datos = respuesta.json()
        if not datos.get("ok"):
            log.error(f"[Telegram] Error de API: {datos}")
            return False
        log.info(f"[Telegram] Notificación enviada correctamente ({config.BOT_NOMBRE}).")
        return True
    except requests.exceptions.Timeout:
        log.warning("[Telegram] Timeout enviando notificación.")
        return False
    except requests.exceptions.RequestException as e:
        log.warning(f"[Telegram] Error de conexión: {e}")
        return False
    except Exception as e:
        log.warning(f"[Telegram] Error inesperado: {e}")
        return False


def _adquirir_lock_receptor():
    global _lockfile_fd
    ruta = "/tmp/bottrade_telegram_getupdates.lock"
    try:
        flags = os.O_CREAT | os.O_EXCL | os.O_RDWR
        _lockfile_fd = os.open(ruta, flags, 0o600)
        os.write(_lockfile_fd, str(os.getpid()).encode("ascii"))
        return True
    except FileExistsError:
        return False
    except Exception as e:
        log.warning(f"[Telegram] No se pudo crear lock de receptor: {e}")
        return True


def _liberar_lock_receptor():
    global _lockfile_fd
    if _lockfile_fd is None:
        return
    ruta = "/tmp/bottrade_telegram_getupdates.lock"
    try:
        os.close(_lockfile_fd)
    except Exception:
        pass
    _lockfile_fd = None
    try:
        os.unlink(ruta)
    except FileNotFoundError:
        pass
    except Exception:
        pass


def iniciar_comandos(callback):
    """Inicia exactamente un receptor getUpdates por servicio habilitado."""
    global _comandos_iniciado

    if _receptor_telegram_deshabilitado():
        log.info(
            "[Telegram] Receptor de comandos deshabilitado por configuración. "
            "Las notificaciones salientes permanecen activas."
        )
        return False

    with _comandos_lock:
        if _comandos_iniciado:
            log.warning(
                "[Telegram] El receptor de comandos ya está activo; se ignora el segundo arranque."
            )
            return False
        if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
            log.warning(
                "[Telegram] No se inicia el receptor: Token o Chat ID no configurados."
            )
            return False
        if not _adquirir_lock_receptor():
            log.warning(
                "[Telegram] Ya existe otro receptor local de getUpdates; este proceso no iniciará un segundo receptor."
            )
            return False
        _comandos_iniciado = True

    hilo = threading.Thread(
        target=_loop_comandos,
        args=(callback,),
        daemon=True,
        name="TelegramComandos",
    )
    hilo.start()
    log.info("[Telegram] Monitor de comandos iniciado. Receptor único activo.")
    return True


def _loop_comandos(callback):
    offset = None
    conflictos_409 = 0
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates"
    log.info("[Telegram] Escuchando comandos...")
    try:
        while True:
            try:
                parametros = {"timeout": 25, "allowed_updates": ["message"]}
                if offset is not None:
                    parametros["offset"] = offset
                respuesta = requests.get(url, params=parametros, timeout=35)
                if respuesta.status_code == 409:
                    conflictos_409 += 1
                    espera = min(60, 15 * conflictos_409)
                    log.warning(
                        "[Telegram] Conflicto 409: existe otro receptor de getUpdates fuera de este proceso. "
                        f"Reintentando en {espera}s (intento {conflictos_409})."
                    )
                    time.sleep(espera)
                    continue
                conflictos_409 = 0
                if respuesta.status_code == 404:
                    log.error(
                        "[Telegram] getUpdates devolvió 404. El token del bot no es válido/está revocado. "
                        "Receptor detenido; las notificaciones salientes permanecen independientes."
                    )
                    return
                if respuesta.status_code != 200:
                    log.error(f"[Telegram] Error getUpdates: {respuesta.status_code}")
                    time.sleep(5)
                    continue
                datos = respuesta.json()
                if not datos.get("ok"):
                    log.error(f"[Telegram] Error API getUpdates: {datos}")
                    time.sleep(5)
                    continue
                for update in datos.get("result", []):
                    offset = update["update_id"] + 1
                    mensaje = update.get("message")
                    if not mensaje:
                        continue
                    chat = mensaje.get("chat", {})
                    chat_id = str(chat.get("id", ""))
                    if chat_id != str(config.TELEGRAM_CHAT_ID):
                        log.warning("[Telegram] Comando ignorado de chat no autorizado.")
                        continue
                    texto = str(mensaje.get("text", "")).strip()
                    if not texto or not texto.startswith("/"):
                        continue
                    comando = texto.split()[0].lower()
                    if "@" in comando:
                        comando = comando.split("@")[0]
                    log.info(f"[Telegram] Comando recibido: {comando}")
                    try:
                        respuesta_comando = callback(comando)
                        if respuesta_comando:
                            notificar(respuesta_comando)
                        else:
                            log.warning(f"[Telegram] El comando {comando} no devolvió respuesta.")
                    except Exception as e:
                        log.error(f"[Telegram] Error ejecutando {comando}: {e}")
                        notificar(f"❌ Error ejecutando {comando}.")
            except Exception as e:
                log.error(f"[Telegram] Error en receptor getUpdates: {e}")
                time.sleep(5)
    finally:
        global _comandos_iniciado
        _comandos_iniciado = False
        _liberar_lock_receptor()
