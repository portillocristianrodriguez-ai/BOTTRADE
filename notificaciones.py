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

    Los comandos son enviados a:

        callback(comando)

    Ejemplos:

        /saldo
        /posiciones
        /estado
        /scanner
        /help
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

            if respuesta.status_code == 409:

                log.error(
                    "[Telegram] ERROR 409: "
                    "otro programa o instancia está utilizando "
                    "el mismo bot para recibir mensajes "
                    "mediante getUpdates."
                )

                log.error(
                    "[Telegram] Los comandos NO podrán recibirse "
                    "hasta que exista una sola instancia "
                    "escuchando los mensajes."
                )

                time.sleep(10)
                continue

            # ====================================================
            # OTROS ERRORES HTTP
            # ====================================================

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

            # ====================================================
            # PROCESAR ACTUALIZACIONES
            # ====================================================

            for update in datos.get(
                "result",
                [],
            ):

                # ====================================================
                # ACTUALIZAR OFFSET
                # ====================================================

                offset = (
                    update["update_id"]
                    + 1
                )

                mensaje = update.get(
                    "message"
                )

                if not mensaje:
                    continue

                # ====================================================
                # OBTENER CHAT
                # ====================================================

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

                # ====================================================
                # SEGURIDAD
                # ====================================================

                if chat_id != str(
                    config.TELEGRAM_CHAT_ID
                ):

                    log.warning(
                        "[Telegram] "
                        "Comando ignorado de "
                        "chat no autorizado."
                    )

                    continue

                # ====================================================
                # OBTENER TEXTO
                # ====================================================

                texto = str(
                    mensaje.get(
                        "text",
                        ""
                    )
                ).strip()

                if not texto:
                    continue

                # ====================================================
                # SOLO COMANDOS
                # ====================================================

                if not texto.startswith("/"):
                    continue

                # ====================================================
                # EXTRAER COMANDO
                # ====================================================

                comando = (
                    texto
                    .split()[0]
                    .lower()
                )

                # Permite comandos tipo:
                #
                # /saldo@MiBot
                #
                if "@" in comando:
                    comando = comando.split(
                        "@"
                    )[0]

                log.info(
                    "[Telegram] "
                    f"Comando recibido: "
                    f"{comando}"
                )

                # ====================================================
                # EJECUTAR COMANDO
                # ====================================================

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

        # ========================================================
        # TIMEOUT NORMAL
        # ========================================================

        except requests.exceptions.Timeout:

            # El timeout es normal porque estamos utilizando
            # long polling con getUpdates.
            continue

        # ========================================================
        # ERROR DE CONEXIÓN
        # ========================================================

        except requests.exceptions.RequestException as e:

            log.error(
                "[Telegram] "
                f"Error de conexión "
                f"monitorizando comandos: {e}"
            )

            time.sleep(5)

        # ========================================================
        # ERROR GENERAL
        # ========================================================

        except Exception as e:

            log.error(
                "[Telegram] "
                f"Error monitorizando comandos: {e}"
            )

            time.sleep(5)
