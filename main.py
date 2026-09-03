"""
main.py

Punto de entrada del bot.

Gestiona:

- Acciones
- Cripto
- Señales de estrategia
- Control de posiciones
- Protección automática SL/TP
- Monitor de ejecuciones
- Trailing stop de cripto
- Recuperación tras reinicios
- Bloqueo contra operaciones duplicadas
- Comandos de Telegram
"""

import time
import logging
import threading

import config
import broker
import estrategia
import notificaciones


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

log = logging.getLogger(__name__)


# ============================================================
# ESTADO
# ============================================================

_maximos_cripto = {}

# Evita que dos hilos intenten operar simultáneamente.
_lock_operaciones = threading.Lock()


# ============================================================
# OBTENER ATR ACTUAL
# ============================================================

def obtener_atr_actual(
    ticker: str,
):

    try:

        df = broker.obtener_datos(
            ticker
        )

        if df.empty:

            log.warning(
                f"{ticker}: no hay datos "
                f"para calcular ATR."
            )

            return None

        df = estrategia.calcular_indicadores(
            df
        )

        if "atr" not in df.columns:

            log.warning(
                f"{ticker}: la estrategia "
                f"no contiene columna ATR."
            )

            return None

        atr = df.iloc[-1]["atr"]

        if atr is None:

            return None

        try:

            atr = float(atr)

        except Exception:

            return None

        if atr <= 0:

            return None

        return atr

    except Exception as e:

        log.error(
            f"{ticker}: error obteniendo ATR: {e}"
        )

        return None


# ============================================================
# PROTEGER COMPRA EJECUTADA
# ============================================================

def proteger_compra_ejecutada(
    ticker: str,
):

    """
    Después de una compra de acciones:

    1. Espera a que Alpaca registre la posición.
    2. Obtiene ATR actualizado.
    3. Comprueba la protección.
    4. Crea SL + TP OCO.
    5. Verifica que la protección existe.

    Esto protege también después de reinicios.
    """

    if broker.es_cripto(ticker):

        return

    log.info(
        f"{ticker}: esperando confirmación "
        f"de posición para protección."
    )

    posicion = None

    for intento in range(6):

        try:

            posicion = broker.obtener_posicion(
                ticker
            )

            if posicion is not None:

                log.info(
                    f"{ticker}: posición confirmada "
                    f"en Alpaca."
                )

                break

        except Exception as e:

            log.warning(
                f"{ticker}: error comprobando "
                f"posición: {e}"
            )

        time.sleep(2)

    if posicion is None:

        log.error(
            f"{ticker}: compra ejecutada pero "
            f"la posición todavía no aparece."
        )

        notificaciones.notificar(
            f"⚠️ {ticker}: COMPRA EJECUTADA "
            f"pero no se pudo confirmar "
            f"la posición."
        )

        return

    atr = obtener_atr_actual(
        ticker
    )

    if atr is None:

        log.error(
            f"{ticker}: no se pudo obtener "
            f"ATR para protección."
        )

        notificaciones.notificar(
            f"⚠️ {ticker}: posición abierta "
            f"pero no se pudo calcular ATR "
            f"para SL/TP."
        )

        return

    mensaje_proteccion = None

    for intento in range(3):

        try:

            mensaje_proteccion = (
                broker.proteger_posicion(
                    ticker,
                    atr,
                )
            )

            if mensaje_proteccion:

                log.info(
                    f"{ticker}: protección "
                    f"creada correctamente."
                )

                break

            analisis = (
                broker.analizar_proteccion(
                    ticker
                )
            )

            if analisis[
                "tiene_proteccion"
            ]:

                log.info(
                    f"{ticker}: protección "
                    f"ya estaba activa."
                )

                return

        except Exception as e:

            log.error(
                f"{ticker}: error creando "
                f"protección "
                f"(intento {intento + 1}/3): {e}"
            )

        time.sleep(2)

    for intento in range(5):

        try:

            analisis = (
                broker.analizar_proteccion(
                    ticker
                )
            )

            if analisis[
                "tiene_proteccion"
            ]:

                log.info(
                    f"{ticker}: "
                    f"SL + TP verificados correctamente."
                )

                if mensaje_proteccion:

                    notificaciones.notificar(
                        mensaje_proteccion
                    )

                return

        except Exception as e:

            log.warning(
                f"{ticker}: error verificando "
                f"protección: {e}"
            )

        time.sleep(2)

    log.error(
        f"{ticker}: NO SE PUDO VERIFICAR "
        f"LA PROTECCIÓN."
    )

    notificaciones.notificar(
        f"🚨 ALERTA {ticker}\n"
        f"Posición abierta pero no se pudo "
        f"verificar SL + TP."
    )


# ============================================================
# REVISAR TICKER
# ============================================================

def revisar_ticker(
    ticker: str,
):

    try:

        df = broker.obtener_datos(
            ticker
        )

        if df.empty:

            log.warning(
                f"{ticker}: sin datos, se omite."
            )

            return

        df = estrategia.calcular_indicadores(
            df
        )

        senal = estrategia.generar_senal(
            df,
            ticker,
        )

        actual = df.iloc[-1]

        precio_actual = float(
            actual["close"]
        )

        atr_actual = None

        try:

            valor_atr = actual["atr"]

            if valor_atr is not None:

                atr_actual = float(
                    valor_atr
                )

                if atr_actual <= 0:

                    atr_actual = None

        except Exception:

            atr_actual = None

        posicion_abierta = (
            broker.tiene_posicion_abierta(
                ticker
            )
        )

        log.info(
            f"{ticker}: "
            f"precio=${precio_actual:.2f} "
            f"señal={senal} "
            f"posición_abierta="
            f"{posicion_abierta}"
        )

        # ====================================================
        # PROTECCIÓN DE ACCIONES
        # ====================================================

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
                    f"{ticker}: error protegiendo "
                    f"posición existente: {e}"
                )

        # ====================================================
        # GESTIÓN DE CRIPTO
        # ====================================================

        if (
            posicion_abierta
            and broker.es_cripto(ticker)
        ):

            perdida_pct = (
                broker.perdida_pct_no_realizada(
                    ticker
                )
            )

            # -----------------------------------------------
            # STOP LOSS MANUAL
            # -----------------------------------------------

            if (
                perdida_pct is not None
                and perdida_pct
                <= -config.STOP_LOSS_PCT
            ):

                log.warning(
                    f"{ticker}: stop-loss manual "
                    f"disparado "
                    f"({perdida_pct:.2%})."
                )

                with _lock_operaciones:

                    if not broker.tiene_posicion_abierta(
                        ticker
                    ):

                        return

                    mensaje = broker.vender(
                        ticker
                    )

                _maximos_cripto.pop(
                    ticker,
                    None,
                )

                if mensaje:

                    notificaciones.notificar(
                        f"🛑 STOP-LOSS MANUAL\n"
                        f"{mensaje}\n"
                        f"Pérdida: {perdida_pct:.2%}"
                    )

                return

            # -----------------------------------------------
            # TRAILING STOP
            # -----------------------------------------------

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
                        f"({retroceso:.2%})."
                    )

                    with _lock_operaciones:

                        if not broker.tiene_posicion_abierta(
                            ticker
                        ):

                            return

                        mensaje = broker.vender(
                            ticker
                        )

                    _maximos_cripto.pop(
                        ticker,
                        None,
                    )

                    if mensaje:

                        notificaciones.notificar(
                            f"📉 TRAILING STOP\n"
                            f"{mensaje}\n"
                            f"Retroceso: "
                            f"{retroceso:.2%}"
                        )

                    return

        # ====================================================
        # COMPRAR
        # ====================================================

        if (
            senal == "COMPRAR"
            and not posicion_abierta
        ):

            if atr_actual is None:

                log.warning(
                    f"{ticker}: ATR no disponible. "
                    f"Compra cancelada."
                )

                return

            with _lock_operaciones:

                if broker.tiene_posicion_abierta(
                    ticker
                ):

                    log.info(
                        f"{ticker}: posición apareció "
                        f"antes de comprar. "
                        f"Se cancela la compra."
                    )

                    return

                ordenes = (
                    broker.obtener_ordenes_ticker(
                        ticker
                    )
                )

                orden_compra_pendiente = False

                for orden in ordenes:

                    side = str(
                        getattr(
                            orden,
                            "side",
                            "",
                        )
                    ).lower()

                    status = str(
                        getattr(
                            orden,
                            "status",
                            "",
                        )
                    ).lower()

                    if (
                        "buy" in side
                        and (
                            "new" in status
                            or "accepted" in status
                            or "pending" in status
                            or "partially" in status
                        )
                    ):

                        orden_compra_pendiente = True

                        break

                if orden_compra_pendiente:

                    log.info(
                        f"{ticker}: ya existe "
                        f"una compra pendiente. "
                        f"No se duplica."
                    )

                    return

                if (
                    broker.contar_posiciones_abiertas()
                    >= config.MAX_POSICIONES_ABIERTAS
                ):

                    log.info(
                        "Máximo de posiciones abiertas "
                        "alcanzado."
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

            return

        # ====================================================
        # VENDER
        # ====================================================

        if (
            senal == "VENDER"
            and posicion_abierta
        ):

            with _lock_operaciones:

                if not broker.tiene_posicion_abierta(
                    ticker
                ):

                    return

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


# ============================================================
# LOOP ACCIONES
# ============================================================

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


# ============================================================
# LOOP EJECUCIONES
# ============================================================

def loop_ejecuciones():

    log.info(
        "[ejecuciones] Monitor de órdenes iniciado."
    )

    try:

        broker.inicializar_monitor_ejecuciones()

    except Exception as e:

        log.error(
            f"[ejecuciones] Error inicializando "
            f"monitor: {e}"
        )

    while True:

        try:

            ejecuciones = (
                broker.detectar_ejecuciones()
            )

            for ejecucion in ejecuciones:

                try:

                    mensaje = ejecucion.get(
                        "mensaje"
                    )

                    ticker = ejecucion.get(
                        "ticker"
                    )

                    compra_accion = ejecucion.get(
                        "compra_accion",
                        False,
                    )

                    if mensaje:

                        notificaciones.notificar(
                            mensaje
                        )

                        log.info(
                            f"[ejecuciones] "
                            f"{ticker}: "
                            f"notificación enviada."
                        )

                    if (
                        compra_accion
                        and ticker
                    ):

                        log.info(
                            f"[ejecuciones] "
                            f"{ticker}: compra de "
                            f"acción detectada. "
                            f"Activando protección."
                        )

                        proteger_compra_ejecutada(
                            ticker
                        )

                except Exception as e:

                    log.error(
                        f"[ejecuciones] Error "
                        f"procesando ejecución: {e}"
                    )

        except Exception as e:

            log.error(
                f"[ejecuciones] "
                f"Error monitorizando órdenes: {e}"
            )

        time.sleep(30)


# ============================================================
# LOOP CRIPTO
# ============================================================

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


# ============================================================
# RECUPERAR PROTECCIONES AL ARRANCAR
# ============================================================

def recuperar_protecciones():

    try:

        posiciones = (
            broker.obtener_todas_las_posiciones()
        )

        if not posiciones:

            log.info(
                "[recuperación] No hay posiciones "
                "abiertas."
            )

            return

        log.info(
            f"[recuperación] "
            f"{len(posiciones)} posiciones "
            f"encontradas."
        )

        for posicion in posiciones:

            ticker = getattr(
                posicion,
                "symbol",
                None,
            )

            if not ticker:

                continue

            if broker.es_cripto(
                ticker
            ):

                continue

            try:

                analisis = (
                    broker.analizar_proteccion(
                        ticker
                    )
                )

                if analisis[
                    "tiene_proteccion"
                ]:

                    log.info(
                        f"[recuperación] "
                        f"{ticker}: protección "
                        f"ya activa."
                    )

                    continue

                log.warning(
                    f"[recuperación] "
                    f"{ticker}: posición sin "
                    f"protección. "
                    f"Intentando proteger."
                )

                proteger_compra_ejecutada(
                    ticker
                )

            except Exception as e:

                log.error(
                    f"[recuperación] "
                    f"{ticker}: error: {e}"
                )

    except Exception as e:

        log.error(
            f"[recuperación] Error general: {e}"
        )


# ============================================================
# COMANDOS TELEGRAM
# ============================================================

def procesar_comando_telegram(
    comando,
):

    # --------------------------------------------------------
    # /saldo
    # --------------------------------------------------------

    if comando == "/saldo":

        datos = broker.obtener_resumen_cuenta()

        if not datos:

            return (
                "❌ No se pudo obtener "
                "el saldo."
            )

        beneficio = datos[
            "beneficio_dia"
        ]

        emoji = (
            "🟢"
            if beneficio >= 0
            else "🔴"
        )

        return (
            "💰 SALDO DE LA CUENTA\n\n"
            f"Capital total: "
            f"${datos['equity']:,.2f}\n"
            f"Disponible: "
            f"${datos['cash']:,.2f}\n"
            f"Buying Power: "
            f"${datos['buying_power']:,.2f}\n\n"
            "📊 RESULTADO DEL DÍA\n"
            f"{emoji} "
            f"${beneficio:+,.2f}\n\n"
            "📈 POSICIONES\n"
            f"{datos['numero_posiciones']}"
        )

    # --------------------------------------------------------
    # /posiciones
    # --------------------------------------------------------

    if comando == "/posiciones":

        posiciones = (
            broker.obtener_posiciones_telegram()
        )

        if not posiciones:

            return (
                "📭 No hay posiciones abiertas."
            )

        mensaje = (
            "📊 POSICIONES ABIERTAS\n\n"
        )

        for posicion in posiciones:

            emoji = (
                "🟢"
                if posicion["beneficio"] >= 0
                else "🔴"
            )

            mensaje += (
                f"{emoji} "
                f"{posicion['simbolo']}\n"
                f"Cantidad: "
                f"{posicion['cantidad']}\n"
                f"Entrada: "
                f"${posicion['entrada']:.2f}\n"
                f"Actual: "
                f"${posicion['actual']:.2f}\n"
                f"P/L: "
                f"${posicion['beneficio']:+,.2f} "
                f"("
                f"{posicion['beneficio_pct']:+.2f}%"
                f")\n\n"
            )

        return mensaje

    # --------------------------------------------------------
    # /estado
    # --------------------------------------------------------

    if comando == "/estado":

        datos = broker.obtener_resumen_cuenta()

        if not datos:

            return (
                "❌ No se pudo obtener "
                "el estado."
            )

        beneficio = datos[
            "beneficio_dia"
        ]

        emoji = (
            "🟢"
            if beneficio >= 0
            else "🔴"
        )

        return (
            "📊 ESTADO DEL BOT\n\n"
            f"{emoji} Resultado del día: "
            f"${beneficio:+,.2f}\n"
            f"💰 Equity: "
            f"${datos['equity']:,.2f}\n"
            f"📈 Posiciones: "
            f"{datos['numero_posiciones']}\n"
            f"🤖 {config.BOT_NOMBRE}"
        )

    # --------------------------------------------------------
    # /start y /help
    # --------------------------------------------------------

    if comando in (
        "/start",
        "/help",
    ):

        return (
            "🤖 COMANDOS DISPONIBLES\n\n"
            "/saldo — saldo y resultado del día\n"
            "/posiciones — posiciones abiertas\n"
            "/estado — estado general del bot"
        )

    # --------------------------------------------------------
    # COMANDO DESCONOCIDO
    # --------------------------------------------------------

    return (
        "❓ Comando no reconocido.\n\n"
        "Usa /help para ver los comandos."
    )


# ============================================================
# MAIN
# ============================================================

def main():

    # --------------------------------------------------------
    # VALIDAR CONFIGURACIÓN
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # NOTIFICACIÓN DE INICIO
    # --------------------------------------------------------

    try:

        notificaciones.notificar(
            f"🤖 Bot iniciado "
            f"({'paper' if config.PAPER else 'REAL'})\n"
            f"Acciones: "
            f"{', '.join(config.TICKERS) or '(ninguna)'}\n"
            f"Cripto: "
            f"{', '.join(config.CRYPTO_TICKERS) or '(ninguna)'}"
        )

    except Exception as e:

        log.warning(
            f"No se pudo enviar "
            f"notificación de inicio: {e}"
        )

    # --------------------------------------------------------
    # INICIAR COMANDOS TELEGRAM
    # --------------------------------------------------------

    try:

        notificaciones.iniciar_comandos(
            procesar_comando_telegram
        )

    except Exception as e:

        log.warning(
            "No se pudo iniciar el monitor "
            f"de comandos Telegram: {e}"
        )

    # --------------------------------------------------------
    # RECUPERAR PROTECCIONES
    # --------------------------------------------------------

    recuperar_protecciones()

    # --------------------------------------------------------
    # CREAR HILOS
    # --------------------------------------------------------

    hilos = []

    hilos.append(
        threading.Thread(
            target=loop_ejecuciones,
            daemon=True,
            name="MonitorEjecuciones",
        )
    )

    if config.TICKERS:

        hilos.append(
            threading.Thread(
                target=loop_acciones,
                daemon=True,
                name="LoopAcciones",
            )
        )

    if config.CRYPTO_TICKERS:

        hilos.append(
            threading.Thread(
                target=loop_cripto,
                daemon=True,
                name="LoopCripto",
            )
        )

    if not hilos:

        log.error(
            "No hay TICKERS ni "
            "CRYPTO_TICKERS configurados. "
            "Nada que hacer."
        )

        return

    # --------------------------------------------------------
    # INICIAR HILOS
    # --------------------------------------------------------

    for hilo in hilos:

        hilo.start()

        log.info(
            f"Hilo iniciado: "
            f"{hilo.name}"
        )

    log.info(
        "Todos los procesos del bot "
        "han sido iniciados correctamente."
    )

    # --------------------------------------------------------
    # MANTENER BOT ACTIVO
    # --------------------------------------------------------

    while True:

        time.sleep(60)


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":

    main()
