"""
Punto de entrada del bot.

Gestiona:
- Acciones: velas diarias + bracket orders.
- Posiciones de acciones existentes: comprueba y crea protección
  automáticamente si falta SL/TP.
- Cripto: gestión manual de stop-loss + trailing stop.
- Órdenes ejecutadas: monitorización y avisos por Telegram.
"""

import time
import logging
import threading

import config
import broker
import estrategia
import notificaciones


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

log = logging.getLogger(__name__)


# =========================================================
# MÁXIMOS DE CRIPTO
# =========================================================

_maximos_cripto = {}


# =========================================================
# REVISAR TICKER
# =========================================================

def revisar_ticker(ticker: str):
    """Revisa un ticker y gestiona su posición."""

    try:

        df = broker.obtener_datos(ticker)

        if df.empty:

            log.warning(
                f"{ticker}: sin datos, se omite."
            )

            return

        df = estrategia.calcular_indicadores(df)

        senal = estrategia.generar_senal(df)

        actual = df.iloc[-1]

        precio_actual = float(
            actual["close"]
        )

        atr_actual = (
            float(actual["atr"])
            if not actual.isna().get("atr", True)
            else None
        )

        posicion_abierta = (
            broker.tiene_posicion_abierta(
                ticker
            )
        )

        log.info(
            f"{ticker}: "
            f"precio=${precio_actual:.2f} "
            f"señal={senal} "
            f"posición_abierta={posicion_abierta}"
        )

        # =====================================================
        # ACCIONES: PROTEGER POSICIONES EXISTENTES
        # =====================================================

        if (
            posicion_abierta
            and not broker.es_cripto(ticker)
            and atr_actual is not None
        ):

            try:

                mensaje_proteccion = (
                    broker.proteger_posicion(
                        ticker,
                        atr_actual,
                    )
                )

                if mensaje_proteccion:

                    notificaciones.notificar(
                        mensaje_proteccion
                    )

            except Exception as e:

                log.error(
                    f"{ticker}: error comprobando "
                    f"protección: {e}"
                )

        # =====================================================
        # CRIPTO
        # =====================================================

        if (
            posicion_abierta
            and broker.es_cripto(ticker)
        ):

            # -------------------------------------------------
            # STOP LOSS MANUAL
            # -------------------------------------------------

            perdida_pct = (
                broker.perdida_pct_no_realizada(
                    ticker
                )
            )

            if (
                perdida_pct is not None
                and perdida_pct
                <= -config.STOP_LOSS_PCT
            ):

                log.warning(
                    f"{ticker}: stop-loss manual "
                    f"disparado "
                    f"({perdida_pct:.2%}). "
                    f"Vendiendo."
                )

                mensaje = broker.vender(
                    ticker
                )

                _maximos_cripto.pop(
                    ticker,
                    None,
                )

                if mensaje:

                    notificaciones.notificar(
                        f"🛑 STOP-LOSS manual — "
                        f"{mensaje} "
                        f"(pérdida: "
                        f"{perdida_pct:.2%})"
                    )

                return

            # -------------------------------------------------
            # TRAILING STOP MANUAL
            # -------------------------------------------------

            info_posicion = (
                broker.precio_actual_posicion(
                    ticker
                )
            )

            if info_posicion is not None:

                (
                    precio_entrada,
                    precio_actual_pos,
                ) = info_posicion

                maximo_previo = (
                    _maximos_cripto.get(
                        ticker,
                        precio_entrada,
                    )
                )

                nuevo_maximo = max(
                    maximo_previo,
                    precio_actual_pos,
                )

                _maximos_cripto[ticker] = (
                    nuevo_maximo
                )

                retroceso = (
                    (
                        nuevo_maximo
                        - precio_actual_pos
                    )
                    / nuevo_maximo
                    if nuevo_maximo > 0
                    else 0
                )

                if (
                    retroceso
                    >= config.TRAILING_STOP_PCT
                ):

                    log.warning(
                        f"{ticker}: trailing stop "
                        f"disparado "
                        f"(retroceso "
                        f"{retroceso:.2%} "
                        f"desde "
                        f"${nuevo_maximo:.2f}). "
                        f"Vendiendo."
                    )

                    mensaje = broker.vender(
                        ticker
                    )

                    _maximos_cripto.pop(
                        ticker,
                        None,
                    )

                    if mensaje:

                        notificaciones.notificar(
                            f"📉 TRAILING STOP — "
                            f"{mensaje} "
                            f"(retroceso: "
                            f"{retroceso:.2%})"
                        )

                    return

        # =====================================================
        # COMPRA
        # =====================================================

        if (
            senal == "COMPRAR"
            and not posicion_abierta
        ):

            if atr_actual is None:

                log.warning(
                    f"{ticker}: ATR no disponible, "
                    f"se omite compra."
                )

                return

            if (
                broker.contar_posiciones_abiertas()
                >= config.MAX_POSICIONES_ABIERTAS
            ):

                log.info(
                    "Máximo de posiciones abiertas "
                    "alcanzado, se omite compra."
                )

                return

            mensaje = broker.comprar(
                ticker,
                precio_actual,
                atr_actual,
            )

            if mensaje:

                notificaciones.notificar(
                    mensaje
                )

                if broker.es_cripto(ticker):

                    _maximos_cripto[ticker] = (
                        precio_actual
                    )

        # =====================================================
        # VENTA POR SEÑAL
        # =====================================================

        elif (
            senal == "VENDER"
            and posicion_abierta
        ):

            mensaje = broker.vender(
                ticker
            )

            _maximos_cripto.pop(
                ticker,
                None,
            )

            if mensaje:

                notificaciones.notificar(
                    mensaje
                )

    except Exception as e:

        log.error(
            f"{ticker}: error general en "
            f"revisar_ticker: {e}"
        )


# =========================================================
# LOOP ACCIONES
# =========================================================

def loop_acciones():

    if not config.TICKERS:
        return

    while True:

        try:

            if broker.mercado_abierto():

                for ticker in config.TICKERS:

                    try:

                        revisar_ticker(
                            ticker
                        )

                    except Exception as e:

                        log.error(
                            f"[acciones] Error "
                            f"procesando "
                            f"{ticker}: {e}"
                        )

            else:

                log.info(
                    "[acciones] Mercado cerrado, "
                    "se omite este ciclo."
                )

        except Exception as e:

            log.error(
                f"[acciones] Error en el loop: {e}"
            )

            try:

                notificaciones.notificar(
                    f"⚠️ Error en el loop "
                    f"de acciones: {e}"
                )

            except Exception:

                pass

        time.sleep(
            60
            * config.CHECK_INTERVAL_MINUTES
        )


# =========================================================
# MONITOR DE EJECUCIONES
# =========================================================

def loop_ejecuciones():

    log.info(
        "[ejecuciones] Monitor de órdenes iniciado."
    )

    while True:

        try:

            mensajes = (
                broker.detectar_ejecuciones()
            )

            for mensaje in mensajes:

                try:

                    notificaciones.notificar(
                        mensaje
                    )

                    log.info(
                        "[ejecuciones] "
                        "Notificación enviada: "
                        f"{mensaje}"
                    )

                except Exception as e:

                    log.error(
                        f"[ejecuciones] "
                        f"Error enviando "
                        f"Telegram: {e}"
                    )

        except Exception as e:

            log.error(
                f"[ejecuciones] "
                f"Error monitorizando "
                f"órdenes: {e}"
            )

        # Comprobar cada 30 segundos
        time.sleep(30)


# =========================================================
# LOOP CRIPTO
# =========================================================

def loop_cripto():

    if not config.CRYPTO_TICKERS:
        return

    while True:

        try:

            for ticker in config.CRYPTO_TICKERS:

                try:

                    revisar_ticker(
                        ticker
                    )

                except Exception as e:

                    log.error(
                        f"[cripto] Error "
                        f"procesando "
                        f"{ticker}: {e}"
                    )

        except Exception as e:

            log.error(
                f"[cripto] Error en "
                f"el loop de cripto: {e}"
            )

            try:

                notificaciones.notificar(
                    f"⚠️ Error en el loop "
                    f"de cripto: {e}"
                )

            except Exception:

                pass

        time.sleep(
            60
            * config.CRYPTO_CHECK_INTERVAL_MINUTES
        )


# =========================================================
# MAIN
# =========================================================

def main():

    config.validar()

    log.info(
        f"Iniciando bot — modo "
        f"{'PAPER (simulado)' if config.PAPER else 'REAL'}"
    )

    log.info(
        f"Acciones: {config.TICKERS} "
        f"(cada "
        f"{config.CHECK_INTERVAL_MINUTES} min) | "
        f"Cripto: {config.CRYPTO_TICKERS} "
        f"(cada "
        f"{config.CRYPTO_CHECK_INTERVAL_MINUTES} min)"
    )

    try:

        notificaciones.notificar(
            f"🤖 Bot iniciado "
            f"({'paper' if config.PAPER else 'REAL'}) — "
            f"acciones: "
            f"{', '.join(config.TICKERS) or '(ninguna)'} "
            f"— cripto: "
            f"{', '.join(config.CRYPTO_TICKERS) or '(ninguna)'}"
        )

    except Exception as e:

        log.warning(
            f"No se pudo enviar "
            f"notificación de inicio: {e}"
        )

    # =====================================================
    # CREAR HILOS
    # =====================================================

    hilos = []

    # Monitor de ejecuciones
    hilos.append(
        threading.Thread(
            target=loop_ejecuciones,
            daemon=True,
        )
    )

    # Acciones
    if config.TICKERS:

        hilos.append(
            threading.Thread(
                target=loop_acciones,
                daemon=True,
            )
        )

    # Cripto
    if config.CRYPTO_TICKERS:

        hilos.append(
            threading.Thread(
                target=loop_cripto,
                daemon=True,
            )
        )

    # =====================================================
    # COMPROBAR QUE HAY ALGO QUE EJECUTAR
    # =====================================================

    if not hilos:

        log.error(
            "No hay TICKERS ni "
            "CRYPTO_TICKERS configurados. "
            "Nada que hacer."
        )

        return

    # =====================================================
    # ARRANCAR HILOS
    # =====================================================

    for hilo in hilos:

        hilo.start()

    log.info(
        "Todos los procesos del bot "
        "han sido iniciados correctamente."
    )

    # =====================================================
    # MANTENER VIVO EL PROCESO PRINCIPAL
    # =====================================================

    while True:

        time.sleep(60)


# =========================================================
# EJECUCIÓN
# =========================================================

if __name__ == "__main__":
    main()
