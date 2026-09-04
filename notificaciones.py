"""
Notificaciones y comandos por Telegram.
"""

import logging
import threading
import time

import requests

import config


log = logging.getLogger(__name__)


# ============================================================
# ENVIAR NOTIFICACIÓN
# ============================================================

def notificar(mensaje: str):
    if (
        not config.TELEGRAM_BOT_TOKEN
        or not config.TELEGRAM_CHAT_ID
    ):
        log.warning(
            "[Telegram] Token o Chat ID no configurados."
        )
        return False

    if not mensaje:
        log.warning(
            "[Telegram] Se intentó enviar un mensaje vacío."
        )
        return False

    try:
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

    except requests.exceptions.Timeout:
        log.warning(
            "[Telegram] Timeout enviando notificación."
        )
        return False

    except requests.exceptions.RequestException as e:
        log.warning(
            f"[Telegram] Error de conexión: {e}"
        )
        return False

    except Exception as e:
        log.warning(
            f"[Telegram] Error inesperado: {e}"
        )
        return False


# ============================================================
# MONITOR DE COMANDOS TELEGRAM
# ============================================================

def iniciar_comandos(callback):
    """
    Inicia un hilo independiente que escucha comandos
    enviados por Telegram.
    """

    hilo = threading.Thread(
        target=_loop_comandos,
        args=(callback,),
        daemon=True,
        name="TelegramComandos",
    )

    hilo.start()

    log.info(
        "[Telegram] Monitor de comandos iniciado."
    )


# ============================================================
# LOOP DE COMANDOS
# ============================================================

def _loop_comandos(callback):

    offset = None
    conflictos_409 = 0

    url = (
        f"https://api.telegram.org/"
        f"bot{config.TELEGRAM_BOT_TOKEN}/getUpdates"
    )

    log.info(
        "[Telegram] Escuchando comandos..."
    )

    while True:

        try:

            parametros = {
                "timeout": 25,
                "allowed_updates": ["message"],
            }

            if offset is not None:
                parametros["offset"] = offset

            respuesta = requests.get(
                url,
                params=parametros,
                timeout=35,
            )

            # ====================================================
            # CONFLICTO 409
            # ====================================================
            #
            # Telegram solo permite un receptor mediante
            # getUpdates. Durante un redeploy de Railway puede
            # existir solapamiento temporal entre la instancia
            # anterior y la nueva. No matamos el listener ante
            # el primer 409: esperamos y recuperamos el polling.
            # ====================================================

            if respuesta.status_code == 409:

                conflictos_409 += 1

                espera = min(
                    60,
                    15 * conflictos_409,
                )

                log.warning(
                    "[Telegram] Conflicto 409: existe "
                    "otro receptor de getUpdates. "
                    f"Reintentando en {espera}s "
                    f"(intento {conflictos_409})."
                )

                time.sleep(espera)
                continue

            # Cualquier respuesta correcta rompe la racha de
            # conflictos y devuelve el listener a funcionamiento
            # normal.
            conflictos_409 = 0

            if respuesta.status_code != 200:

                log.error(
                    "[Telegram] "
                    f"Error getUpdates: "
                    f"{respuesta.status_code}"
                )

                time.sleep(5)
                continue

            datos = respuesta.json()

            if not datos.get("ok"):

                log.error(
                    f"[Telegram] Error API getUpdates: "
                    f"{datos}"
                )

                time.sleep(5)
                continue

            for update in datos.get(
                "result",
                [],
            ):

                offset = (
                    update["update_id"]
                    + 1
                )

                mensaje = update.get(
                    "message"
                )

                if not mensaje:
                    continue

                chat = mensaje.get(
                    "chat",
                    {}
                )

                chat_id = str(
                    chat.get(
                        "id",
                        ""
                    )
                )

                if chat_id != str(
                    config.TELEGRAM_CHAT_ID
                ):

                    log.warning(
                        "[Telegram] "
                        "Comando ignorado de "
                        "chat no autorizado."
                    )

                    continue

                texto = str(
                    mensaje.get(
                        "text",
                        ""
                    )
                ).strip()

                if not texto:
                    continue

                if not texto.startswith("/"):
                    continue

                comando = (
                    texto
                    .split()[0]
                    .lower()
                )

                if "@" in comando:
                    comando = comando.split(
                        "@"
                    )[0]

                log.info(
                    "[Telegram] "
                    f"Comando recibido: "
                    f"{comando}"
                )

                try:

                    respuesta_comando = callback(
                        comando
                    )

                    if respuesta_comando:

                        notificar(
                            respuesta_comando
                        )

                    else:

                        log.warning(
                            "[Telegram] "
                            f"El comando {comando} "
                            "no devolvió respuesta."
                        )

                except Exception as e:

                    log.error(
                        "[Telegram] "
                        f"Error ejecutando "
                        f"{comando}: {e}"
                    )

                    notificar(
                        f"❌ Error ejecutando "
                        f"{comando}."
                    )

        except requests.exceptions.Timeout:
            continue

        except requests.exceptions.RequestException as e:

            log.error(
                "[Telegram] "
                f"Error de conexión "
                f"monitorizando comandos: {e}"
            )

            time.sleep(5)

        except Exception as e:

            log.error(
                "[Telegram] "
                f"Error monitorizando comandos: {e}"
            )

            time.sleep(5)
