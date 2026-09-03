"""
main.py

Punto de entrada del bot.

Gestiona:

- Acciones
- Scanner crypto automático 24/7
- Señales de estrategia
- Control de posiciones
- Protección automática de acciones
- Protección crypto por software
- Monitor de ejecuciones
- Trailing stop crypto
- Take Profit crypto
- Recuperación tras reinicios
- Bloqueo contra operaciones duplicadas
- Comandos de Telegram
- Consulta de la segunda cuenta

IMPORTANTE:
La cuenta secundaria permanece SOLO EN LECTURA.
El scanner crypto opera únicamente con la cuenta principal.
"""

import os
import time
import logging
import threading
from datetime import datetime, timedelta, timezone

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
# CONTROL GLOBAL
# ============================================================

_maximos_cripto = {}

_cooldown_crypto = {}

_lock_operaciones = threading.Lock()

_ultimo_scan_crypto = None

_ultimo_candidato_crypto = None


# ============================================================
# ATR
# ============================================================

def obtener_atr_actual(ticker: str):

    try:

        df = broker.obtener_datos(
            ticker
        )

        if df.empty:

            log.warning(
                f"{ticker}: no hay datos "
                "para calcular ATR."
            )

            return None

        df = (
            estrategia.calcular_indicadores(
                df
            )
        )

        if "atr" not in df.columns:

            log.warning(
                f"{ticker}: la estrategia "
                "no contiene columna ATR."
            )

            return None

        atr = df.iloc[-1]["atr"]

        if atr is None:

            return None

        try:

            atr = float(
                atr
            )

        except Exception:

            return None

        if atr <= 0:

            return None

        return atr

    except Exception as e:

        log.error(
            f"{ticker}: error obteniendo "
            f"ATR: {e}"
        )

        return None


# ============================================================
# PROTEGER COMPRA DE ACCIONES
# ============================================================

def proteger_compra_ejecutada(
    ticker: str,
):

    if broker.es_cripto(ticker):

        return

    log.info(
        f"{ticker}: esperando confirmación "
        "de posición para protección."
    )

    posicion = None

    for intento in range(6):

        try:

            posicion = (
                broker.obtener_posicion(
                    ticker
                )
            )

            if posicion is not None:

                log.info(
                    f"{ticker}: posición "
                    "confirmada en Alpaca."
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
            f"{ticker}: compra ejecutada "
            "pero la posición todavía "
            "no aparece."
        )

        notificaciones.notificar(
            f"⚠️ {ticker}: COMPRA EJECUTADA "
            "pero no se pudo confirmar "
            "la posición."
        )

        return

    atr = obtener_atr_actual(
        ticker
    )

    if atr is None:

        log.error(
            f"{ticker}: no se pudo obtener "
            "ATR para protección."
        )

        notificaciones.notificar(
            f"⚠️ {ticker}: posición abierta "
            "pero no se pudo calcular "
            "ATR para SL/TP."
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
                    "creada correctamente."
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
                    "ya estaba activa."
                )

                return

        except Exception as e:

            log.error(
                f"{ticker}: error creando "
                "protección "
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
                    f"{ticker}: SL + TP "
                    "verificados correctamente."
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
        "LA PROTECCIÓN."
    )

    notificaciones.notificar(
        f"🚨 ALERTA {ticker}\n"
        "Posición abierta pero no se pudo "
        "verificar SL + TP."
    )


# ============================================================
# REVISAR TICKER NORMAL
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
                f"{ticker}: sin datos, "
                "se omite."
            )

            return

        df = (
            estrategia.calcular_indicadores(
                df
            )
        )

        senal = (
            estrategia.generar_senal(
                df,
                ticker,
            )
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
        # PROTECCIÓN ACCIONES
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
                    f"{ticker}: error "
                    "protegiendo posición "
                    f"existente: {e}"
                )

        # ====================================================
        # CRYPTO — GESTIÓN ANTIGUA
        #
        # Se mantiene para los CRYPTO_TICKERS
        # manuales y compatibilidad.
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

            # ------------------------------------------------
            # STOP LOSS
            # ------------------------------------------------

            if (
                perdida_pct
                <= -config.STOP_LOSS_PCT
            ):

                log.warning(
                    f"{ticker}: stop-loss "
                    "manual disparado "
                    f"({perdida_pct:.2%})."
                )

                with _lock_operaciones:

                    if not (
                        broker.tiene_posicion_abierta(
                            ticker
                        )
                    ):

                        return

                    mensaje = (
                        broker.vender(
                            ticker
                        )
                    )

                _maximos_cripto.pop(
                    ticker,
                    None,
                )

                if mensaje:

                    notificaciones.notificar(
                        "🛑 STOP-LOSS MANUAL\n"
                        f"{mensaje}\n"
                        f"Pérdida: "
                        f"{perdida_pct:.2%}"
                    )

                return

            # ------------------------------------------------
            # TAKE PROFIT
            # ------------------------------------------------

            if (
                perdida_pct
                >= config.TAKE_PROFIT_PCT
            ):

                log.info(
                    f"{ticker}: TAKE PROFIT "
                    "manual disparado "
                    f"({perdida_pct:.2%})."
                )

                with _lock_operaciones:

                    if not (
                        broker.tiene_posicion_abierta(
                            ticker
                        )
                    ):

                        return

                    mensaje = (
                        broker.vender(
                            ticker
                        )
                    )

                _maximos_cripto.pop(
                    ticker,
                    None,
                )

                if mensaje:

                    notificaciones.notificar(
                        "🎯 TAKE PROFIT\n"
                        f"{mensaje}\n"
                        f"Ganancia: "
                        f"{perdida_pct:.2%}"
                    )

                return

            # ------------------------------------------------
            # TRAILING STOP
            # ------------------------------------------------

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

                _maximos_cripto[
                    ticker
                ] = nuevo_maximo

                beneficio_actual = (
                    (
                        precio_actual_pos
                        - precio_entrada
                    )
                    / precio_entrada
                    if precio_entrada > 0
                    else 0
                )

                # El trailing solo se activa
                # después de entrar en beneficio.
                if beneficio_actual >= 0.015:

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
                            f"{ticker}: trailing "
                            "stop disparado "
                            f"({retroceso:.2%})."
                        )

                        with _lock_operaciones:

                            if not (
                                broker.tiene_posicion_abierta(
                                    ticker
                                )
                            ):

                                return

                            mensaje = (
                                broker.vender(
                                    ticker
                                )
                            )

                        _maximos_cripto.pop(
                            ticker,
                            None,
                        )

                        if mensaje:

                            notificaciones.notificar(
                                "📉 TRAILING STOP\n"
                                f"{mensaje}\n"
                                f"Retroceso: "
                                f"{retroceso:.2%}"
                            )

                        return

        # ====================================================
        # COMPRA NORMAL
        # ====================================================

        if (
            senal == "COMPRAR"
            and not posicion_abierta
        ):

            if atr_actual is None:

                log.warning(
                    f"{ticker}: ATR no "
                    "disponible. Compra cancelada."
                )

                return

            with _lock_operaciones:

                if broker.tiene_posicion_abierta(
                    ticker
                ):

                    log.info(
                        f"{ticker}: posición "
                        "apareció antes de "
                        "comprar."
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
                        "una compra pendiente."
                    )

                    return

                if (
                    broker.contar_posiciones_abiertas()
                    >= config.MAX_POSICIONES_ABIERTAS
                ):

                    log.info(
                        "Máximo de posiciones "
                        "abiertas alcanzado."
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
        # VENTA NORMAL
        # ====================================================

        if (
            senal == "VENDER"
            and posicion_abierta
        ):

            with _lock_operaciones:

                if not (
                    broker.tiene_posicion_abierta(
                        ticker
                    )
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
            f"{ticker}: error general "
            f"en revisar_ticker: {e}"
        )


# ============================================================
# ACCIONES
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
                            "[acciones] Error "
                            f"procesando {ticker}: {e}"
                        )

            else:

                log.info(
                    "[acciones] Mercado "
                    "cerrado, se omite "
                    "este ciclo."
                )

        except Exception as e:

            log.error(
                "[acciones] Error en "
                f"el loop: {e}"
            )

            try:

                notificaciones.notificar(
                    "⚠️ Error en el loop "
                    f"de acciones: {e}"
                )

            except Exception:
                pass

        time.sleep(
            60
            * config.CHECK_INTERVAL_MINUTES
        )


# ============================================================
# EJECUCIONES
# ============================================================

def loop_ejecuciones():

    log.info(
        "[ejecuciones] Monitor de "
        "órdenes iniciado."
    )

    try:

        broker.inicializar_monitor_ejecuciones()

    except Exception as e:

        log.error(
            "[ejecuciones] Error "
            f"inicializando monitor: {e}"
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

                    compra_accion = (
                        ejecucion.get(
                            "compra_accion",
                            False,
                        )
                    )

                    if mensaje:

                        notificaciones.notificar(
                            mensaje
                        )

                        log.info(
                            "[ejecuciones] "
                            f"{ticker}: "
                            "notificación enviada."
                        )

                    if (
                        compra_accion
                        and ticker
                    ):

                        log.info(
                            "[ejecuciones] "
                            f"{ticker}: compra "
                            "de acción detectada. "
                            "Activando protección."
                        )

                        proteger_compra_ejecutada(
                            ticker
                        )

                except Exception as e:

                    log.error(
                        "[ejecuciones] Error "
                        "procesando ejecución: "
                        f"{e}"
                    )

        except Exception as e:

            log.error(
                "[ejecuciones] Error "
                "monitorizando órdenes: "
                f"{e}"
            )

        time.sleep(30)


# ============================================================
# COOLDOWN CRYPTO
# ============================================================

def crypto_en_cooldown(
    ticker: str,
) -> bool:

    ahora = datetime.now(
        timezone.utc
    )

    fecha = _cooldown_crypto.get(
        ticker
    )

    if fecha is None:

        return False

    if (
        ahora - fecha
    ) >= timedelta(
        minutes=config.CRYPTO_COOLDOWN_MINUTES
    ):

        _cooldown_crypto.pop(
            ticker,
            None,
        )

        return False

    return True


def activar_cooldown_crypto(
    ticker: str,
):

    _cooldown_crypto[
        ticker
    ] = datetime.now(
        timezone.utc
    )


# ============================================================
# COMPRA DEL SCANNER
# ============================================================

def ejecutar_compra_scanner_crypto(
    ticker,
    df,
    analisis,
):

    try:

        if broker.tiene_posicion_abierta(
            ticker
        ):

            log.info(
                f"[crypto] {ticker}: "
                "ya tiene posición."
            )

            return False

        if crypto_en_cooldown(
            ticker
        ):

            log.info(
                f"[crypto] {ticker}: "
                "en cooldown."
            )

            return False

        # ----------------------------------------------------
        # COMPROBAR MÁXIMO DE POSICIONES
        # ----------------------------------------------------

        if (
            broker.contar_posiciones_abiertas()
            >= config.MAX_POSICIONES_ABIERTAS
        ):

            log.info(
                "[crypto] Máximo de "
                "posiciones alcanzado."
            )

            return False

        # ----------------------------------------------------
        # COMPROBAR ORDEN PENDIENTE
        # ----------------------------------------------------

        ordenes = (
            broker.obtener_ordenes_ticker(
                ticker
            )
        )

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

                log.info(
                    f"[crypto] {ticker}: "
                    "compra pendiente."
                )

                return False

        # ----------------------------------------------------
        # DATOS
        # ----------------------------------------------------

        if df.empty:

            return False

        df_indicadores = (
            estrategia.calcular_indicadores(
                df
            )
        )

        actual = (
            df_indicadores.iloc[-1]
        )

        precio = float(
            actual["close"]
        )

        atr = float(
            actual["atr"]
        )

        if (
            precio <= 0
            or atr <= 0
        ):

            return False

        # ----------------------------------------------------
        # BLOQUEO GLOBAL
        # ----------------------------------------------------

        with _lock_operaciones:

            if broker.tiene_posicion_abierta(
                ticker
            ):

                return False

            if (
                broker.contar_posiciones_abiertas()
                >= config.MAX_POSICIONES_ABIERTAS
            ):

                return False

            mensaje = broker.comprar(
                ticker,
                precio,
                atr,
            )

        if not mensaje:

            return False

        score = analisis[
            "score"
        ]

        rsi = analisis[
            "rsi"
        ]

        volumen = analisis[
            "volumen_ratio"
        ]

        momentum = analisis[
            "momentum_pct"
        ]

        razones = analisis[
            "motivo"
        ]

        razones_texto = ", ".join(
            razones[:6]
        )

        mensaje_final = (
            "🚀 SCANNER CRYPTO — "
            "OPORTUNIDAD DETECTADA\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"₿ {ticker}\n"
            f"💵 Precio: ${precio:.6f}\n"
            f"🎯 Score: {score:.0f}/100\n"
            f"📊 RSI: {rsi:.1f}\n"
            f"📈 Volumen: {volumen:.2f}x\n"
            f"⚡ Momentum: {momentum:+.2f}%\n\n"
            f"✅ {razones_texto}\n\n"
            f"{mensaje}"
        )

        notificaciones.notificar(
            mensaje_final
        )

        activar_cooldown_crypto(
            ticker
        )

        log.info(
            f"[crypto] COMPRA SCANNER: "
            f"{ticker} | "
            f"score={score:.1f} | "
            f"RSI={rsi:.1f} | "
            f"vol={volumen:.2f}x | "
            f"momentum={momentum:.2f}%"
        )

        return True

    except Exception as e:

        log.error(
            f"[crypto] Error ejecutando "
            f"compra scanner {ticker}: {e}"
        )

        return False


# ============================================================
# SCANNER CRYPTO
# ============================================================

def ejecutar_scanner_crypto():

    global _ultimo_scan_crypto
    global _ultimo_candidato_crypto

    try:

        universo = (
            broker.obtener_universo_crypto()
        )

        if not universo:

            log.warning(
                "[crypto] No se encontró "
                "ninguna crypto negociable."
            )

            return

        # ----------------------------------------------------
        # LIMITAR UNIVERSO
        # ----------------------------------------------------

        max_symbols = (
            config.CRYPTO_MAX_SYMBOLS_SCAN
        )

        universo_scan = universo[
            :max_symbols
        ]

        log.info(
            "[crypto] Iniciando scanner: "
            f"{len(universo_scan)} "
            "símbolos."
        )

        datos = (
            broker.obtener_datos_crypto_lote(
                universo_scan,
                dias=3,
            )
        )

        if not datos:

            log.warning(
                "[crypto] No se recibieron "
                "datos para el scanner."
            )

            return

        candidatos = []

        # ----------------------------------------------------
        # ANALIZAR CADA CRYPTO
        # ----------------------------------------------------

        for ticker, df in datos.items():

            try:

                if df.empty:

                    continue

                # No analizar una posición
                # ya abierta como nueva entrada.

                if broker.tiene_posicion_abierta(
                    ticker
                ):

                    continue

                if crypto_en_cooldown(
                    ticker
                ):

                    continue

                analisis = (
                    estrategia.analizar_impulso_crypto(
                        df,
                        ticker,
                    )
                )

                score = float(
                    analisis.get(
                        "score",
                        0,
                    )
                )

                if score <= 0:

                    continue

                # ------------------------------------------------
                # LIQUIDEZ RELATIVA
                # ------------------------------------------------

                try:

                    ultimas = df.tail(
                        12
                    )

                    dollar_volume = (
                        ultimas["close"]
                        * ultimas["volume"]
                    )

                    volumen_dolar_medio = (
                        float(
                            dollar_volume.mean()
                        )
                    )

                except Exception:

                    volumen_dolar_medio = 0.0

                analisis[
                    "volumen_dolar_medio"
                ] = volumen_dolar_medio

                candidatos.append(
                    (
                        ticker,
                        df,
                        analisis,
                    )
                )

            except Exception as e:

                log.debug(
                    f"[crypto] Error analizando "
                    f"{ticker}: {e}"
                )

        # ----------------------------------------------------
        # ORDENAR POR SCORE
        # ----------------------------------------------------

        candidatos.sort(
            key=lambda x: (
                x[2]["score"],
                x[2].get(
                    "volumen_dolar_medio",
                    0,
                ),
            ),
            reverse=True,
        )

        max_candidatos = (
            config.CRYPTO_MAX_CANDIDATOS
        )

        candidatos = candidatos[
            :max_candidatos
        ]

        # ----------------------------------------------------
        # MOSTRAR TOP
        # ----------------------------------------------------

        if candidatos:

            log.info(
                "[crypto] TOP "
                f"{len(candidatos)} "
                "candidatos:"
            )

            for (
                ticker,
                df,
                analisis,
            ) in candidatos:

                log.info(
                    f"[crypto] "
                    f"{ticker} | "
                    f"score="
                    f"{analisis['score']:.1f} | "
                    f"RSI="
                    f"{analisis['rsi']:.1f} | "
                    f"vol="
                    f"{analisis['volumen_ratio']:.2f}x | "
                    f"mom="
                    f"{analisis['momentum_pct']:+.2f}% | "
                    f"comprar="
                    f"{analisis['comprar']}"
                )

            _ultimo_candidato_crypto = (
                candidatos[0][0]
            )

        else:

            log.info(
                "[crypto] No hay candidatos "
                "interesantes en este ciclo."
            )

            _ultimo_candidato_crypto = None

        # ----------------------------------------------------
        # COMPRAR SOLO LOS QUE CUMPLEN
        # ----------------------------------------------------

        compras = 0

        for (
            ticker,
            df,
            analisis,
        ) in candidatos:

            if compras >= (
                config.CRYPTO_MAX_COMPRAS_POR_CICLO
            ):

                break

            if not analisis.get(
                "comprar",
                False,
            ):

                continue

            if (
                analisis["score"]
                < config.CRYPTO_SCORE_MINIMO
            ):

                continue

            comprada = (
                ejecutar_compra_scanner_crypto(
                    ticker,
                    df,
                    analisis,
                )
            )

            if comprada:

                compras += 1

        _ultimo_scan_crypto = (
            datetime.now(
                timezone.utc
            )
        )

        log.info(
            "[crypto] Scanner terminado. "
            f"Datos={len(datos)} | "
            f"Candidatos={len(candidatos)} | "
            f"Compras={compras}"
        )

    except Exception as e:

        log.error(
            "[crypto] Error general "
            f"del scanner: {e}"
        )

        try:

            notificaciones.notificar(
                "⚠️ Error en scanner crypto: "
                f"{e}"
            )

        except Exception:
            pass


# ============================================================
# LOOP SCANNER CRYPTO
# ============================================================

def loop_scanner_crypto():

    log.info(
        "[crypto] Scanner automático "
        "24/7 iniciado."
    )

    while True:

        try:

            ejecutar_scanner_crypto()

        except Exception as e:

            log.error(
                "[crypto] Error en loop "
                f"scanner: {e}"
            )

        time.sleep(
            60
            * config.CRYPTO_SCAN_INTERVAL_MINUTES
        )


# ============================================================
# GESTIÓN DE POSICIONES CRYPTO
# ============================================================

def gestionar_posiciones_crypto():

    try:

        posiciones = (
            broker.obtener_todas_las_posiciones()
        )

        for posicion in posiciones:

            ticker = getattr(
                posicion,
                "symbol",
                None,
            )

            if not ticker:
                continue

            ticker = (
                broker.normalizar_ticker_crypto(
                    ticker
                )
            )

            if not broker.es_cripto(
                ticker
            ):

                continue

            try:

                precio_entrada = float(
                    getattr(
                        posicion,
                        "avg_entry_price",
                        0,
                    )
                    or 0
                )

                precio_actual = float(
                    getattr(
                        posicion,
                        "current_price",
                        0,
                    )
                    or 0
                )

                if (
                    precio_entrada <= 0
                    or precio_actual <= 0
                ):

                    continue

                rendimiento = (
                    precio_actual
                    - precio_entrada
                ) / precio_entrada

                # =============================================
                # STOP LOSS
                # =============================================

                if (
                    rendimiento
                    <= -config.STOP_LOSS_PCT
                ):

                    log.warning(
                        f"[crypto] {ticker}: "
                        f"STOP LOSS "
                        f"{rendimiento:.2%}"
                    )

                    with _lock_operaciones:

                        if not (
                            broker.tiene_posicion_abierta(
                                ticker
                            )
                        ):

                            continue

                        mensaje = (
                            broker.vender(
                                ticker
                            )
                        )

                    _maximos_cripto.pop(
                        ticker,
                        None,
                    )

                    activar_cooldown_crypto(
                        ticker
                    )

                    if mensaje:

                        notificaciones.notificar(
                            "🛑 CRYPTO STOP LOSS\n"
                            f"{mensaje}\n"
                            f"Pérdida: "
                            f"{rendimiento:.2%}"
                        )

                    continue

                # =============================================
                # TAKE PROFIT
                # =============================================

                if (
                    rendimiento
                    >= config.TAKE_PROFIT_PCT
                ):

                    log.info(
                        f"[crypto] {ticker}: "
                        f"TAKE PROFIT "
                        f"{rendimiento:.2%}"
                    )

                    with _lock_operaciones:

                        if not (
                            broker.tiene_posicion_abierta(
                                ticker
                            )
                        ):

                            continue

                        mensaje = (
                            broker.vender(
                                ticker
                            )
                        )

                    _maximos_cripto.pop(
                        ticker,
                        None,
                    )

                    activar_cooldown_crypto(
                        ticker
                    )

                    if mensaje:

                        notificaciones.notificar(
                            "🎯 CRYPTO TAKE PROFIT\n"
                            f"{mensaje}\n"
                            f"Ganancia: "
                            f"{rendimiento:.2%}"
                        )

                    continue

                # =============================================
                # ACTUALIZAR MÁXIMO
                # =============================================

                maximo_previo = (
                    _maximos_cripto.get(
                        ticker,
                        precio_entrada,
                    )
                )

                nuevo_maximo = max(
                    maximo_previo,
                    precio_actual,
                )

                _maximos_cripto[
                    ticker
                ] = nuevo_maximo

                # =============================================
                # TRAILING
                # =============================================

                if rendimiento >= 0.015:

                    retroceso = (
                        nuevo_maximo
                        - precio_actual
                    ) / nuevo_maximo

                    if (
                        retroceso
                        >= config.TRAILING_STOP_PCT
                    ):

                        log.warning(
                            f"[crypto] {ticker}: "
                            f"TRAILING STOP "
                            f"{retroceso:.2%}"
                        )

                        with _lock_operaciones:

                            if not (
                                broker.tiene_posicion_abierta(
                                    ticker
                                )
                            ):

                                continue

                            mensaje = (
                                broker.vender(
                                    ticker
                                )
                            )

                        _maximos_cripto.pop(
                            ticker,
                            None,
                        )

                        activar_cooldown_crypto(
                            ticker
                        )

                        if mensaje:

                            notificaciones.notificar(
                                "📉 CRYPTO TRAILING STOP\n"
                                f"{mensaje}\n"
                                f"Retroceso: "
                                f"{retroceso:.2%}"
                            )

            except Exception as e:

                log.error(
                    f"[crypto] Error gestionando "
                    f"{ticker}: {e}"
                )

    except Exception as e:

        log.error(
            "[crypto] Error general "
            "gestionando posiciones: "
            f"{e}"
        )


# ============================================================
# LOOP PROTECCIÓN CRYPTO
# ============================================================

def loop_proteccion_crypto():

    log.info(
        "[crypto] Protección crypto "
        "24/7 iniciada."
    )

    while True:

        try:

            gestionar_posiciones_crypto()

        except Exception as e:

            log.error(
                "[crypto] Error en "
                f"protección crypto: {e}"
            )

        # Protección mucho más frecuente
        # que el scanner.

        time.sleep(15)


# ============================================================
# RECUPERACIÓN DE PROTECCIONES
# ============================================================

def recuperar_protecciones():

    try:

        posiciones = (
            broker.obtener_todas_las_posiciones()
        )

        if not posiciones:

            log.info(
                "[recuperación] No hay "
                "posiciones abiertas."
            )

            return

        log.info(
            "[recuperación] "
            f"{len(posiciones)} "
            "posiciones encontradas."
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
                        "ya activa."
                    )

                    continue

                log.warning(
                    f"[recuperación] "
                    f"{ticker}: posición "
                    "sin protección. "
                    "Intentando proteger."
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
            "[recuperación] Error general: "
            f"{e}"
        )


# ============================================================
# TELEGRAM
# ============================================================

def procesar_comando_telegram(
    comando,
):

    if comando in (
        "/saldo",
        "/saldo1",
    ):

        datos = (
            broker.obtener_resumen_cuenta()
        )

        if not datos:

            return (
                "❌ No se pudo obtener "
                "el saldo de la cuenta "
                "principal."
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
            "🟢 CUENTA PRINCIPAL\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"💰 Capital total: "
            f"${datos['equity']:,.2f}\n"
            f"💵 Disponible: "
            f"${datos['cash']:,.2f}\n"
            f"📊 Buying Power: "
            f"${datos['buying_power']:,.2f}\n\n"
            "📈 RESULTADO DEL DÍA\n"
            f"{emoji} ${beneficio:+,.2f}\n\n"
            "📊 POSICIONES\n"
            f"{datos['numero_posiciones']}"
        )

    if comando == "/saldo2":

        datos = (
            broker.obtener_resumen_cuenta_secundaria()
        )

        if not datos:

            return (
                "❌ No se pudo obtener "
                "el saldo de la cuenta "
                "secundaria."
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
            "🔴 CUENTA SECUNDARIA\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"💰 Capital total: "
            f"${datos['equity']:,.2f}\n"
            f"💵 Disponible: "
            f"${datos['cash']:,.2f}\n"
            f"📊 Buying Power: "
            f"${datos['buying_power']:,.2f}\n\n"
            "📈 RESULTADO DEL DÍA\n"
            f"{emoji} ${beneficio:+,.2f}\n\n"
            "📊 POSICIONES\n"
            f"{datos['numero_posiciones']}"
        )

    if comando in (
        "/posiciones",
        "/posiciones1",
    ):

        posiciones = (
            broker.obtener_posiciones_telegram()
        )

        if not posiciones:

            return (
                "🟢 CUENTA PRINCIPAL\n\n"
                "📭 No hay posiciones abiertas."
            )

        mensaje = (
            "🟢 CUENTA PRINCIPAL\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "📊 POSICIONES ABIERTAS\n\n"
        )

        for p in posiciones:

            emoji = (
                "🟢"
                if p["beneficio"] >= 0
                else "🔴"
            )

            mensaje += (
                f"{emoji} {p['simbolo']}\n"
                f"Cantidad: {p['cantidad']}\n"
                f"Entrada: "
                f"${p['entrada']:.2f}\n"
                f"Actual: "
                f"${p['actual']:.2f}\n"
                f"P/L: "
                f"${p['beneficio']:+,.2f} "
                f"({p['beneficio_pct']:+.2f}%)\n\n"
            )

        return mensaje

    if comando == "/posiciones2":

        posiciones = (
            broker.obtener_posiciones_secundaria()
        )

        if not posiciones:

            return (
                "🔴 CUENTA SECUNDARIA\n\n"
                "📭 No hay posiciones abiertas."
            )

        mensaje = (
            "🔴 CUENTA SECUNDARIA\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "📊 POSICIONES ABIERTAS\n\n"
        )

        for p in posiciones:

            emoji = (
                "🟢"
                if p["beneficio"] >= 0
                else "🔴"
            )

            mensaje += (
                f"{emoji} {p['simbolo']}\n"
                f"Cantidad: {p['cantidad']}\n"
                f"Entrada: "
                f"${p['entrada']:.2f}\n"
                f"Actual: "
                f"${p['actual']:.2f}\n"
                f"P/L: "
                f"${p['beneficio']:+,.2f} "
                f"({p['beneficio_pct']:+.2f}%)\n\n"
            )

        return mensaje

    if comando in (
        "/estado",
        "/estado1",
    ):

        datos = (
            broker.obtener_resumen_cuenta()
        )

        if not datos:

            return (
                "❌ No se pudo obtener "
                "el estado de la cuenta "
                "principal."
            )

        beneficio = datos[
            "beneficio_dia"
        ]

        emoji = (
            "🟢"
            if beneficio >= 0
            else "🔴"
        )

        scanner = (
            "🟢 ACTIVO"
            if config.CRYPTO_SCANNER_ENABLED
            else "🔴 DESACTIVADO"
        )

        return (
            "🟢 CUENTA PRINCIPAL\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"{emoji} Resultado del día: "
            f"${beneficio:+,.2f}\n"
            f"💰 Equity: "
            f"${datos['equity']:,.2f}\n"
            f"📈 Posiciones: "
            f"{datos['numero_posiciones']}\n\n"
            f"₿ Scanner crypto: {scanner}\n"
            f"🤖 {config.BOT_NOMBRE}"
        )

    if comando == "/estado2":

        datos = (
            broker.obtener_resumen_cuenta_secundaria()
        )

        if not datos:

            return (
                "❌ No se pudo obtener "
                "el estado de la cuenta "
                "secundaria."
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
            "🔴 CUENTA SECUNDARIA\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"{emoji} Resultado del día: "
            f"${beneficio:+,.2f}\n"
            f"💰 Equity: "
            f"${datos['equity']:,.2f}\n"
            f"📈 Posiciones: "
            f"{datos['numero_posiciones']}"
        )

    if comando == "/todo":

        principal = (
            broker.obtener_resumen_cuenta()
        )

        secundaria = (
            broker.obtener_resumen_cuenta_secundaria()
        )

        if not principal:

            return (
                "❌ No se pudo consultar "
                "la cuenta principal."
            )

        if not secundaria:

            return (
                "❌ No se pudo consultar "
                "la cuenta secundaria."
            )

        beneficio1 = principal[
            "beneficio_dia"
        ]

        beneficio2 = secundaria[
            "beneficio_dia"
        ]

        emoji1 = (
            "🟢"
            if beneficio1 >= 0
            else "🔴"
        )

        emoji2 = (
            "🟢"
            if beneficio2 >= 0
            else "🔴"
        )

        return (
            "🤖 RESUMEN DE LAS DOS CUENTAS\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "🟢 CUENTA PRINCIPAL\n"
            f"💰 Equity: "
            f"${principal['equity']:,.2f}\n"
            f"💵 Disponible: "
            f"${principal['cash']:,.2f}\n"
            f"{emoji1} Resultado día: "
            f"${beneficio1:+,.2f}\n"
            f"📈 Posiciones: "
            f"{principal['numero_posiciones']}\n\n"
            "🔴 CUENTA SECUNDARIA\n"
            f"💰 Equity: "
            f"${secundaria['equity']:,.2f}\n"
            f"💵 Disponible: "
            f"${secundaria['cash']:,.2f}\n"
            f"{emoji2} Resultado día: "
            f"${beneficio2:+,.2f}\n"
            f"📈 Posiciones: "
            f"{secundaria['numero_posiciones']}"
        )

    if comando in (
        "/scanner",
        "/crypto",
    ):

        estado = (
            "🟢 ACTIVO"
            if config.CRYPTO_SCANNER_ENABLED
            else "🔴 DESACTIVADO"
        )

        if (
            _ultimo_scan_crypto
            is not None
        ):

            ultimo_scan = (
                _ultimo_scan_crypto
                .astimezone()
                .strftime(
                    "%H:%M:%S"
                )
            )

        else:

            ultimo_scan = "Todavía no ejecutado"

        candidato = (
            _ultimo_candidato_crypto
            or "Ninguno"
        )

        return (
            "₿ SCANNER CRYPTO\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"Estado: {estado}\n"
            f"Intervalo: "
            f"{config.CRYPTO_SCAN_INTERVAL_MINUTES} min\n"
            f"Score mínimo: "
            f"{config.CRYPTO_SCORE_MINIMO:.0f}\n"
            f"Último scan: "
            f"{ultimo_scan}\n"
            f"Último candidato: "
            f"{candidato}\n\n"
            "🛡️ Protección crypto: ACTIVA"
        )

    if comando in (
        "/start",
        "/help",
    ):

        return (
            "🤖 COMANDOS TELEGRAM\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "🟢 CUENTA PRINCIPAL\n"
            "/saldo1\n"
            "/posiciones1\n"
            "/estado1\n"
            "/scanner\n\n"
            "🔴 CUENTA SECUNDARIA\n"
            "/saldo2\n"
            "/posiciones2\n"
            "/estado2\n\n"
            "📊 AMBAS CUENTAS\n"
            "/todo"
        )

    return (
        "❓ Comando no reconocido.\n\n"
        "Usa /help para ver los comandos."
    )


# ============================================================
# MAIN
# ============================================================

def main():

    config.validar()

    log.info(
        "Iniciando bot — modo "
        f"{'PAPER (simulado)' if config.PAPER else 'REAL'}"
    )

    log.info(
        f"Acciones: {config.TICKERS} "
        f"(cada "
        f"{config.CHECK_INTERVAL_MINUTES} min)"
    )

    log.info(
        "Scanner crypto: "
        f"{'ACTIVO' if config.CRYPTO_SCANNER_ENABLED else 'DESACTIVADO'}"
    )

    log.info(
        "Crypto scanner intervalo: "
        f"{config.CRYPTO_SCAN_INTERVAL_MINUTES} min"
    )

    # ========================================================
    # TELEGRAM INICIO
    # ========================================================

    try:

        notificaciones.notificar(
            "🤖 Bot iniciado\n"
            f"Modo: "
            f"{'PAPER' if config.PAPER else 'REAL'}\n"
            f"Acciones: "
            f"{', '.join(config.TICKERS) or '(ninguna)'}\n"
            f"₿ Scanner crypto: "
            f"{'ACTIVO' if config.CRYPTO_SCANNER_ENABLED else 'DESACTIVADO'}"
        )

    except Exception as e:

        log.warning(
            "No se pudo enviar "
            f"notificación de inicio: {e}"
        )

    # ========================================================
    # TELEGRAM COMMANDS
    # ========================================================

    telegram_comandos = (
        os.environ.get(
            "TELEGRAM_COMMANDS_ENABLED",
            "true",
        )
        .strip()
        .lower()
        in (
            "true",
            "1",
            "yes",
            "si",
            "sí",
        )
    )

    if telegram_comandos:

        try:

            notificaciones.iniciar_comandos(
                procesar_comando_telegram
            )

        except Exception as e:

            log.warning(
                "No se pudo iniciar "
                "el monitor de comandos "
                f"Telegram: {e}"
            )

    else:

        log.info(
            "[Telegram] Monitor de "
            "comandos desactivado "
            "en esta cuenta."
        )

    # ========================================================
    # RECUPERAR PROTECCIONES ACCIONES
    # ========================================================

    recuperar_protecciones()

    # ========================================================
    # HILOS
    # ========================================================

    hilos = []

    # --------------------------------------------------------
    # EJECUCIONES
    # --------------------------------------------------------

    hilos.append(
        threading.Thread(
            target=loop_ejecuciones,
            daemon=True,
            name="MonitorEjecuciones",
        )
    )

    # --------------------------------------------------------
    # ACCIONES
    # --------------------------------------------------------

    if config.TICKERS:

        hilos.append(
            threading.Thread(
                target=loop_acciones,
                daemon=True,
                name="LoopAcciones",
            )
        )

    # --------------------------------------------------------
    # SCANNER CRYPTO
    # --------------------------------------------------------

    if config.CRYPTO_SCANNER_ENABLED:

        hilos.append(
            threading.Thread(
                target=loop_scanner_crypto,
                daemon=True,
                name="LoopCryptoScanner",
            )
        )

        # ----------------------------------------------------
        # PROTECCIÓN CRYPTO
        # ----------------------------------------------------

        hilos.append(
            threading.Thread(
                target=loop_proteccion_crypto,
                daemon=True,
                name="LoopCryptoProteccion",
            )
        )

    # ========================================================
    # ARRANCAR HILOS
    # ========================================================

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

    # ========================================================
    # KEEP ALIVE
    # ========================================================

    while True:

        time.sleep(60)


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":

    main()
