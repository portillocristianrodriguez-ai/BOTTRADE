"""
main.py

Punto de entrada del bot.

Gestiona:

- Acciones
- Observación de acciones fuera de mercado
- Scanner de acciones por impulso
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
- Circuit breaker
- Límite de pérdida diaria
- Control de exposición
- Watchdog de posiciones sin protección
- Motor de observación de patrones
- Persistencia de estado
- Comandos de Telegram
- Consulta de la segunda cuenta

IMPORTANTE:
La cuenta secundaria permanece SOLO EN LECTURA.

El scanner crypto y el scanner de acciones
operan únicamente con la cuenta principal.

El motor de patrones inicialmente SOLO OBSERVA.
No puede modificar señales ni ejecutar operaciones.
"""

import os
import json
import time
import logging
import threading

from collections import deque
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

_lock_estado = threading.Lock()

_ultimo_scan_crypto = None

_ultimo_candidato_crypto = None


# ============================================================
# ESTADO DE SEGURIDAD
# ============================================================

"""
Estos estados existen en memoria durante la ejecución.

Se guardan también en disco cuando la persistencia
está habilitada para sobrevivir a reinicios.
"""

_estado_seguridad = {
    "circuit_breaker": False,
    "circuit_breaker_desde": None,
    "errores_recientes": [],
    "perdida_diaria_bloqueada": False,
    "equity_inicio_dia": None,
    "fecha_equity_inicio_dia": None,
    "posiciones_sin_proteccion": {},
    "ultima_actualizacion": None,
}


# ============================================================
# OBSERVACIÓN DE PATRONES
# ============================================================

_ultima_observacion_pattern = {}

_pattern_lock = threading.Lock()


# ============================================================
# FUNCIONES DE ESTADO
# ============================================================

def _ahora_utc():

    return datetime.now(
        timezone.utc
    )


def _iso_ahora():

    return _ahora_utc().isoformat()


def _cargar_estado():

    if not getattr(
        config,
        "STATE_PERSISTENCE_ENABLED",
        True,
    ):

        return

    ruta = getattr(
        config,
        "STATE_FILE",
        "bot_state.json",
    )

    try:

        if not os.path.exists(ruta):

            return

        with open(
            ruta,
            "r",
            encoding="utf-8",
        ) as archivo:

            datos = json.load(
                archivo
            )

        if not isinstance(
            datos,
            dict,
        ):

            return

        with _lock_estado:

            estado_seguridad = datos.get(
                "estado_seguridad"
            )

            if isinstance(
                estado_seguridad,
                dict,
            ):

                _estado_seguridad.update(
                    estado_seguridad
                )

            cooldowns = datos.get(
                "cooldown_crypto"
            )

            if isinstance(
                cooldowns,
                dict,
            ):

                for ticker, fecha in cooldowns.items():

                    try:

                        _cooldown_crypto[
                            ticker
                        ] = datetime.fromisoformat(
                            fecha
                        )

                    except Exception:

                        continue

            maximos = datos.get(
                "maximos_cripto"
            )

            if isinstance(
                maximos,
                dict,
            ):

                for ticker, precio in maximos.items():

                    try:

                        _maximos_cripto[
                            ticker
                        ] = float(
                            precio
                        )

                    except Exception:

                        continue

        log.info(
            "[estado] Estado persistente "
            "recuperado correctamente."
        )

    except Exception as e:

        log.warning(
            "[estado] No se pudo cargar "
            f"estado persistente: {e}"
        )


def _guardar_estado():

    if not getattr(
        config,
        "STATE_PERSISTENCE_ENABLED",
        True,
    ):

        return

    ruta = getattr(
        config,
        "STATE_FILE",
        "bot_state.json",
    )

    temporal = (
        f"{ruta}.tmp"
    )

    try:

        with _lock_estado:

            datos = {
                "estado_seguridad": dict(
                    _estado_seguridad
                ),
                "cooldown_crypto": {
                    ticker: fecha.isoformat()
                    for ticker, fecha
                    in _cooldown_crypto.items()
                },
                "maximos_cripto": dict(
                    _maximos_cripto
                ),
                "actualizado": _iso_ahora(),
            }

        with open(
            temporal,
            "w",
            encoding="utf-8",
        ) as archivo:

            json.dump(
                datos,
                archivo,
                indent=2,
                ensure_ascii=False,
            )

        os.replace(
            temporal,
            ruta,
        )

    except Exception as e:

        log.warning(
            "[estado] No se pudo guardar "
            f"estado: {e}"
        )

        try:

            if os.path.exists(
                temporal
            ):

                os.remove(
                    temporal
                )

        except Exception:

            pass


# ============================================================
# CIRCUIT BREAKER
# ============================================================

def registrar_error_operativo(
    origen: str,
    error,
):

    if not getattr(
        config,
        "CIRCUIT_BREAKER_ENABLED",
        True,
    ):

        return

    ahora = _ahora_utc()

    with _lock_estado:

        errores = (
            _estado_seguridad.get(
                "errores_recientes",
                [],
            )
        )

        errores_validos = []

        ventana = timedelta(
            minutes=getattr(
                config,
                "CIRCUIT_BREAKER_WINDOW_MINUTES",
                15,
            )
        )

        for elemento in errores:

            try:

                fecha = datetime.fromisoformat(
                    elemento["fecha"]
                )

                if (
                    ahora - fecha
                ) <= ventana:

                    errores_validos.append(
                        elemento
                    )

            except Exception:

                continue

        errores_validos.append(
            {
                "fecha": ahora.isoformat(),
                "origen": str(origen),
                "error": str(error),
            }
        )

        _estado_seguridad[
            "errores_recientes"
        ] = errores_validos

        limite = getattr(
            config,
            "CIRCUIT_BREAKER_MAX_ERRORS",
            5,
        )

        if (
            len(errores_validos)
            >= limite
            and not _estado_seguridad.get(
                "circuit_breaker",
                False,
            )
        ):

            _estado_seguridad[
                "circuit_breaker"
            ] = True

            _estado_seguridad[
                "circuit_breaker_desde"
            ] = ahora.isoformat()

            log.critical(
                "🚨 CIRCUIT BREAKER ACTIVADO: "
                f"{len(errores_validos)} errores "
                f"en {ventana}."
            )

            try:

                notificaciones.notificar(
                    "🚨 CIRCUIT BREAKER ACTIVADO\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    f"Errores recientes: "
                    f"{len(errores_validos)}\n"
                    "🚫 Nuevas compras bloqueadas.\n"
                    "🛡️ Las posiciones existentes "
                    "continúan gestionándose."
                )

            except Exception:

                pass

    _guardar_estado()


def limpiar_errores_operativos():

    if not getattr(
        config,
        "CIRCUIT_BREAKER_ENABLED",
        True,
    ):

        return

    ahora = _ahora_utc()

    with _lock_estado:

        errores = (
            _estado_seguridad.get(
                "errores_recientes",
                [],
            )
        )

        ventana = timedelta(
            minutes=getattr(
                config,
                "CIRCUIT_BREAKER_WINDOW_MINUTES",
                15,
            )
        )

        validos = []

        for elemento in errores:

            try:

                fecha = datetime.fromisoformat(
                    elemento["fecha"]
                )

                if (
                    ahora - fecha
                ) <= ventana:

                    validos.append(
                        elemento
                    )

            except Exception:

                continue

        _estado_seguridad[
            "errores_recientes"
        ] = validos


def actualizar_circuit_breaker():

    if not getattr(
        config,
        "CIRCUIT_BREAKER_ENABLED",
        True,
    ):

        return

    limpiar_errores_operativos()

    ahora = _ahora_utc()

    debe_desactivar = False

    with _lock_estado:

        activo = _estado_seguridad.get(
            "circuit_breaker",
            False,
        )

        desde = _estado_seguridad.get(
            "circuit_breaker_desde"
        )

        if not activo:

            return

        if not desde:

            return

        try:

            fecha_desde = datetime.fromisoformat(
                desde
            )

        except Exception:

            fecha_desde = ahora

        cooldown = timedelta(
            minutes=getattr(
                config,
                "CIRCUIT_BREAKER_COOLDOWN_MINUTES",
                30,
            )
        )

        if (
            ahora - fecha_desde
        ) >= cooldown:

            errores = _estado_seguridad.get(
                "errores_recientes",
                [],
            )

            if not errores:

                debe_desactivar = True

    if debe_desactivar:

        with _lock_estado:

            _estado_seguridad[
                "circuit_breaker"
            ] = False

            _estado_seguridad[
                "circuit_breaker_desde"
            ] = None

        log.warning(
            "🟢 Circuit breaker "
            "desactivado. "
            "Se permiten nuevas entradas."
        )

        try:

            notificaciones.notificar(
                "🟢 CIRCUIT BREAKER DESACTIVADO\n"
                "El periodo de seguridad ha terminado."
            )

        except Exception:

            pass

        _guardar_estado()


def nuevas_entradas_bloqueadas():

    actualizar_circuit_breaker()

    with _lock_estado:

        if _estado_seguridad.get(
            "circuit_breaker",
            False,
        ):

            return True

        if _estado_seguridad.get(
            "perdida_diaria_bloqueada",
            False,
        ):

            return True

    return False


# ============================================================
# CONTROL DE PÉRDIDA DIARIA
# ============================================================

def actualizar_control_perdida_diaria():

    if not getattr(
        config,
        "DAILY_LOSS_LIMIT_ENABLED",
        True,
    ):

        return True

    try:

        datos = (
            broker.obtener_resumen_cuenta()
        )

        if not datos:

            return True

        equity = float(
            datos.get(
                "equity",
                0,
            )
            or 0
        )

        beneficio = float(
            datos.get(
                "beneficio_dia",
                0,
            )
            or 0
        )

        if equity <= 0:

            return True

        hoy = (
            _ahora_utc()
            .date()
            .isoformat()
        )

        with _lock_estado:

            fecha_guardada = (
                _estado_seguridad.get(
                    "fecha_equity_inicio_dia"
                )
            )

            equity_inicio = (
                _estado_seguridad.get(
                    "equity_inicio_dia"
                )
            )

            if (
                fecha_guardada
                != hoy
                or equity_inicio is None
                or float(equity_inicio) <= 0
            ):

                _estado_seguridad[
                    "fecha_equity_inicio_dia"
                ] = hoy

                _estado_seguridad[
                    "equity_inicio_dia"
                ] = equity

                _estado_seguridad[
                    "perdida_diaria_bloqueada"
                ] = False

                log.info(
                    "[riesgo] Nuevo día detectado. "
                    f"Equity inicial=${equity:,.2f}"
                )

            equity_inicio = float(
                _estado_seguridad[
                    "equity_inicio_dia"
                ]
            )

        perdida_desde_inicio = (
            equity - equity_inicio
        ) / equity_inicio

        limite = -float(
            getattr(
                config,
                "DAILY_LOSS_LIMIT_PCT",
                0.05,
            )
        )

        # También utilizamos beneficio_dia como señal
        # complementaria, pero el bloqueo principal se
        # calcula contra equity de inicio.
        perdida_beneficio = (
            beneficio / equity_inicio
            if equity_inicio > 0
            else 0
        )

        activar = (
            perdida_desde_inicio <= limite
            or perdida_beneficio <= limite
        )

        if activar:

            ya_bloqueado = False

            with _lock_estado:

                ya_bloqueado = (
                    _estado_seguridad.get(
                        "perdida_diaria_bloqueada",
                        False,
                    )
                )

                _estado_seguridad[
                    "perdida_diaria_bloqueada"
                ] = True

            if not ya_bloqueado:

                log.critical(
                    "🚨 LÍMITE DE PÉRDIDA DIARIA "
                    "ALCANZADO: "
                    f"{perdida_desde_inicio:.2%}"
                )

                try:

                    notificaciones.notificar(
                        "🚨 LÍMITE DE PÉRDIDA DIARIA\n"
                        "━━━━━━━━━━━━━━━━━━\n"
                        f"Resultado equity: "
                        f"{perdida_desde_inicio:.2%}\n"
                        f"Resultado broker: "
                        f"{perdida_beneficio:.2%}\n"
                        "🚫 Nuevas compras bloqueadas.\n"
                        "🛡️ Las posiciones existentes "
                        "continúan gestionándose."
                    )

                except Exception:

                    pass

            _guardar_estado()

            return False

        return True

    except Exception as e:

        log.error(
            "[riesgo] Error comprobando "
            f"pérdida diaria: {e}"
        )

        registrar_error_operativo(
            "control_perdida_diaria",
            e,
        )

        # Fail-safe:
        # si no podemos verificar el riesgo,
        # no abrimos nuevas posiciones.
        return False


# ============================================================
# CONTROL DE ENTRADAS
# ============================================================

def puede_abrir_nueva_posicion(
    ticker: str,
):

    if nuevas_entradas_bloqueadas():

        log.warning(
            f"{ticker}: nueva entrada "
            "bloqueada por circuit breaker "
            "o pérdida diaria."
        )

        return False

    if not actualizar_control_perdida_diaria():

        log.warning(
            f"{ticker}: nueva entrada "
            "bloqueada por control de "
            "pérdida diaria."
        )

        return False

    if getattr(
        config,
        "REQUIRE_PROTECTION_FOR_NEW_ENTRIES",
        True,
    ):

        sin_proteccion = (
            obtener_posiciones_sin_proteccion()
        )

        if sin_proteccion:

            log.warning(
                f"{ticker}: nueva entrada "
                "bloqueada porque existen "
                "posiciones sin protección: "
                f"{sin_proteccion}"
            )

            return False

    return True


# ============================================================
# ATR
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

        registrar_error_operativo(
            "obtener_atr_actual",
            e,
        )

        return None


# ============================================================
# PROTECCIONES
# ============================================================

def marcar_posicion_sin_proteccion(
    ticker: str,
):

    with _lock_estado:

        _estado_seguridad[
            "posiciones_sin_proteccion"
        ][ticker] = _iso_ahora()

    _guardar_estado()


def limpiar_posicion_sin_proteccion(
    ticker: str,
):

    with _lock_estado:

        _estado_seguridad[
            "posiciones_sin_proteccion"
        ].pop(
            ticker,
            None,
        )

    _guardar_estado()


def obtener_posiciones_sin_proteccion():

    resultado = []

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

            if broker.es_cripto(
                ticker
            ):

                # Crypto se protege por software.
                continue

            try:

                analisis = (
                    broker.analizar_proteccion(
                        ticker
                    )
                )

                if not analisis.get(
                    "tiene_proteccion",
                    False,
                ):

                    resultado.append(
                        ticker
                    )

            except Exception as e:

                log.warning(
                    f"{ticker}: no se pudo "
                    "verificar protección: "
                    f"{e}"
                )

                resultado.append(
                    ticker
                )

        # Incorporamos también las posiciones
        # previamente detectadas como problemáticas.
        with _lock_estado:

            registradas = list(
                _estado_seguridad.get(
                    "posiciones_sin_proteccion",
                    {},
                ).keys()
            )

        for ticker in registradas:

            if ticker not in resultado:

                resultado.append(
                    ticker
                )

    except Exception as e:

        log.error(
            "[protección] Error obteniendo "
            f"posiciones sin protección: {e}"
        )

        registrar_error_operativo(
            "obtener_posiciones_sin_proteccion",
            e,
        )

    return list(
        dict.fromkeys(
            resultado
        )
    )


def proteger_compra_ejecutada(
    ticker: str,
):

    if broker.es_cripto(
        ticker
    ):

        return

    log.info(
        f"{ticker}: esperando confirmación "
        "de posición para protección."
    )

    posicion = None

    max_wait = getattr(
        config,
        "PROTECTION_MAX_WAIT_SECONDS",
        30,
    )

    retry_seconds = getattr(
        config,
        "PROTECTION_RETRY_SECONDS",
        5,
    )

    inicio = time.time()

    while (
        time.time() - inicio
    ) < max_wait:

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

        time.sleep(
            retry_seconds
        )

    if posicion is None:

        marcar_posicion_sin_proteccion(
            ticker
        )

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

        return False

    atr = obtener_atr_actual(
        ticker
    )

    if atr is None:

        marcar_posicion_sin_proteccion(
            ticker
        )

        log.error(
            f"{ticker}: no se pudo obtener "
            "ATR para protección."
        )

        notificaciones.notificar(
            f"🚨 {ticker}: posición abierta "
            "pero no se pudo calcular "
            "ATR para SL/TP."
        )

        return False

    mensaje_proteccion = None

    max_retries = getattr(
        config,
        "PROTECTION_MAX_RETRIES",
        5,
    )

    retry_seconds = getattr(
        config,
        "PROTECTION_RETRY_SECONDS",
        5,
    )

    for intento in range(
        max_retries
    ):

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

            if analisis.get(
                "tiene_proteccion",
                False,
            ):

                log.info(
                    f"{ticker}: protección "
                    "ya estaba activa."
                )

                limpiar_posicion_sin_proteccion(
                    ticker
                )

                return True

        except Exception as e:

            log.error(
                f"{ticker}: error creando "
                "protección "
                f"(intento {intento + 1}/"
                f"{max_retries}): {e}"
            )

            registrar_error_operativo(
                f"proteger_{ticker}",
                e,
            )

        if (
            intento + 1
            < max_retries
        ):

            time.sleep(
                retry_seconds
            )

    for intento in range(
        max_retries
    ):

        try:

            analisis = (
                broker.analizar_proteccion(
                    ticker
                )
            )

            if analisis.get(
                "tiene_proteccion",
                False,
            ):

                log.info(
                    f"{ticker}: SL + TP "
                    "verificados correctamente."
                )

                limpiar_posicion_sin_proteccion(
                    ticker
                )

                if mensaje_proteccion:

                    notificaciones.notificar(
                        mensaje_proteccion
                    )

                return True

        except Exception as e:

            log.warning(
                f"{ticker}: error verificando "
                f"protección: {e}"
            )

        time.sleep(
            retry_seconds
        )

    marcar_posicion_sin_proteccion(
        ticker
    )

    log.error(
        f"{ticker}: NO SE PUDO VERIFICAR "
        "LA PROTECCIÓN."
    )

    notificaciones.notificar(
        f"🚨 ALERTA {ticker}\n"
        "Posición abierta pero no se pudo "
        "verificar SL + TP.\n"
        "🚫 Nuevas entradas bloqueadas "
        "hasta recuperar protección."
    )

    return False


# ============================================================
# SESIÓN DE MERCADO
# ============================================================

def obtener_sesion_mercado():

    """
    Devuelve una etiqueta aproximada de sesión.

    El horario se expresa en UTC para no depender
    de la zona horaria del servidor Railway.

    IMPORTANTE:
    La obtención real de barras extended-hours depende
    de broker.py. Esta función clasifica el momento
    para que el motor de observación pueda registrar
    el contexto correctamente.
    """

    try:

        ahora = _ahora_utc()

        # Estados básicos mediante el reloj de Alpaca.
        try:

            reloj = broker.mercado_abierto()

            if reloj:

                return "REGULAR"

        except Exception:

            pass

        # Aproximación para NYSE/Nasdaq:
        # 13:30 UTC a 20:00 UTC durante horario de verano.
        #
        # Fuera de temporada el offset cambia, por eso
        # la etiqueta horaria es deliberadamente aproximada.
        hora = ahora.hour
        minuto = ahora.minute

        total_minutos = (
            hora * 60
            + minuto
        )

        if 13 * 60 + 30 <= total_minutos < 20 * 60:

            return "REGULAR"

        if 8 * 60 <= total_minutos < 13 * 60 + 30:

            return "PREMARKET"

        if 20 * 60 <= total_minutos < 24 * 60:

            return "AFTER_HOURS"

        if 0 <= total_minutos < 2 * 60:

            return "AFTER_HOURS"

        return "OVERNIGHT"

    except Exception:

        return "UNKNOWN"


# ============================================================
# OBSERVACIÓN DE PATRONES
# ============================================================

def _numero_seguro(
    valor,
    default=None,
):

    try:

        if valor is None:

            return default

        numero = float(
            valor
        )

        if numero != numero:

            return default

        return numero

    except Exception:

        return default


def _bool_seguro(
    valor,
    default=False,
):

    try:

        return bool(
            valor
        )

    except Exception:

        return default


def _obtener_valor(
    fila,
    nombre,
):

    try:

        return fila.get(
            nombre
        )

    except Exception:

        try:

            return fila[
                nombre
            ]

        except Exception:

            return None


def registrar_observacion_pattern(
    ticker: str,
    df,
    analisis_scanner=None,
    senal=None,
):

    if not getattr(
        config,
        "PATTERN_ENGINE_ENABLED",
        True,
    ):

        return

    try:

        if df is None or df.empty:

            return

        ahora = _ahora_utc()

        # ----------------------------------------------------
        # DEDUPLICACIÓN
        # ----------------------------------------------------

        if getattr(
            config,
            "PATTERN_DEDUPLICATION_ENABLED",
            True,
        ):

            intervalo = getattr(
                config,
                "PATTERN_MIN_OBSERVATION_INTERVAL_SECONDS",
                60,
            )

            ultima = (
                _ultima_observacion_pattern.get(
                    ticker
                )
            )

            if ultima is not None:

                segundos = (
                    ahora - ultima
                ).total_seconds()

                if segundos < intervalo:

                    return

        actual = df.iloc[-1]

        precio = _numero_seguro(
            _obtener_valor(
                actual,
                "close",
            )
        )

        if precio is None or precio <= 0:

            return

        volumen = _numero_seguro(
            _obtener_valor(
                actual,
                "volume",
            )
        )

        atr = _numero_seguro(
            _obtener_valor(
                actual,
                "atr",
            )
        )

        rsi = _numero_seguro(
            _obtener_valor(
                actual,
                "rsi",
            )
        )

        macd = _numero_seguro(
            _obtener_valor(
                actual,
                "macd",
            )
        )

        ema_rapida = _numero_seguro(
            _obtener_valor(
                actual,
                "ema_rapida",
            )
        )

        ema_lenta = _numero_seguro(
            _obtener_valor(
                actual,
                "ema_lenta",
            )
        )

        ema_tendencia = _numero_seguro(
            _obtener_valor(
                actual,
                "ema_tendencia",
            )
        )

        volumen_ratio = _numero_seguro(
            _obtener_valor(
                actual,
                "volumen_ratio",
            )
        )

        # ----------------------------------------------------
        # VARIABLES DERIVADAS
        # ----------------------------------------------------

        momentum_pct = None

        try:

            barras = getattr(
                config,
                "CRYPTO_MOMENTUM_BARS",
                3,
            )

            if (
                len(df)
                > barras
            ):

                precio_anterior = _numero_seguro(
                    df.iloc[
                        -1 - barras
                    ]["close"]
                )

                if (
                    precio_anterior
                    and precio_anterior > 0
                ):

                    momentum_pct = (
                        (
                            precio
                            - precio_anterior
                        )
                        / precio_anterior
                    ) * 100

        except Exception:

            momentum_pct = None

        atr_pct = (
            atr / precio
            if (
                atr is not None
                and precio > 0
            )
            else None
        )

        ema_fast_over_slow = None

        if (
            ema_rapida is not None
            and ema_lenta is not None
        ):

            ema_fast_over_slow = (
                ema_rapida
                > ema_lenta
            )

        price_over_trend = None

        if ema_tendencia is not None:

            price_over_trend = (
                precio
                > ema_tendencia
            )

        breakout = False

        try:

            lookback = getattr(
                config,
                "CRYPTO_BREAKOUT_LOOKBACK",
                12,
            )

            if (
                len(df)
                > lookback
            ):

                maximo_previo = float(
                    df.iloc[
                        -1 - lookback:
                        -1
                    ]["high"].max()
                )

                breakout = (
                    precio
                    > maximo_previo
                )

        except Exception:

            breakout = False

        # ----------------------------------------------------
        # SCANNER
        # ----------------------------------------------------

        scanner_data = {}

        if isinstance(
            analisis_scanner,
            dict,
        ):

            scanner_data = {
                "score": _numero_seguro(
                    analisis_scanner.get(
                        "score"
                    )
                ),
                "comprar": _bool_seguro(
                    analisis_scanner.get(
                        "comprar"
                    )
                ),
                "rsi": _numero_seguro(
                    analisis_scanner.get(
                        "rsi"
                    )
                ),
                "volumen_ratio": _numero_seguro(
                    analisis_scanner.get(
                        "volumen_ratio"
                    )
                ),
                "momentum_pct": _numero_seguro(
                    analisis_scanner.get(
                        "momentum_pct"
                    )
                ),
                "atr_pct": _numero_seguro(
                    analisis_scanner.get(
                        "atr_pct"
                    )
                ),
                "breakout": _bool_seguro(
                    analisis_scanner.get(
                        "breakout"
                    )
                ),
            }

        # ----------------------------------------------------
        # REGISTRO
        # ----------------------------------------------------

        observacion = {
            "timestamp_utc": ahora.isoformat(),
            "ticker": ticker,
            "asset_type": (
                "crypto"
                if broker.es_cripto(ticker)
                else "stock"
            ),
            "session": obtener_sesion_mercado(),
            "signal": senal,
            "price": precio,
            "volume": volumen,
            "atr": atr,
            "atr_pct": atr_pct,
            "rsi": rsi,
            "macd": macd,
            "ema_fast": ema_rapida,
            "ema_slow": ema_lenta,
            "ema_trend": ema_tendencia,
            "ema_fast_over_slow": ema_fast_over_slow,
            "price_over_trend": price_over_trend,
            "volume_ratio": volumen_ratio,
            "momentum_pct": momentum_pct,
            "breakout": breakout,
            "scanner": scanner_data,
        }

        # ----------------------------------------------------
        # RESULTADOS FUTUROS
        #
        # Inicialmente se dejan vacíos.
        #
        # En futuras iteraciones se completarán usando
        # nuevas observaciones del mismo activo.
        # ----------------------------------------------------

        observacion[
            "future_returns"
        ] = {}

        observacion[
            "next_open_return_pct"
        ] = None

        ruta = getattr(
            config,
            "PATTERN_DATA_FILE",
            "pattern_observations.jsonl",
        )

        with _pattern_lock:

            with open(
                ruta,
                "a",
                encoding="utf-8",
            ) as archivo:

                archivo.write(
                    json.dumps(
                        observacion,
                        ensure_ascii=False,
                    )
                    + "\n"
                )

            _ultima_observacion_pattern[
                ticker
            ] = ahora

        if getattr(
            config,
            "LOG_PATTERN_OBSERVATIONS",
            True,
        ):

            log.info(
                "[patrones] "
                f"{ticker} | "
                f"sesión={observacion['session']} | "
                f"precio={precio:.6f} | "
                f"RSI={rsi if rsi is not None else 0:.2f} | "
                f"ATR={atr_pct * 100 if atr_pct is not None else 0:.2f}% | "
                f"mom={momentum_pct if momentum_pct is not None else 0:+.2f}% | "
                f"vol={volumen_ratio if volumen_ratio is not None else 0:.2f}x | "
                f"breakout={breakout} | "
                f"señal={senal}"
            )

    except Exception as e:

        log.error(
            f"[patrones] Error registrando "
            f"{ticker}: {e}"
        )

        registrar_error_operativo(
            "registrar_observacion_pattern",
            e,
        )


# ============================================================
# REVISAR TICKER
# ============================================================

def revisar_ticker(
    ticker: str,
):

    try:

        # ====================================================
        # DATOS
        # ====================================================

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

        # ====================================================
        # SEÑAL ORIGINAL
        # ====================================================

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

        # ====================================================
        # POSICIÓN ACTUAL
        # ====================================================

        posicion_abierta = (
            broker.tiene_posicion_abierta(
                ticker
            )
        )

        # ====================================================
        # SCANNER DE IMPULSO DE ACCIONES
        # ====================================================

        analisis_scanner = None

        if not broker.es_cripto(
            ticker
        ):

            try:

                analisis_scanner = (
                    estrategia.analizar_impulso_acciones(
                        df,
                        ticker,
                    )
                )

                score = float(
                    analisis_scanner.get(
                        "score",
                        0,
                    )
                )

                comprar_scanner = bool(
                    analisis_scanner.get(
                        "comprar",
                        False,
                    )
                )

                rsi = float(
                    analisis_scanner.get(
                        "rsi",
                        0,
                    )
                )

                volumen_ratio = float(
                    analisis_scanner.get(
                        "volumen_ratio",
                        0,
                    )
                )

                momentum_pct = float(
                    analisis_scanner.get(
                        "momentum_pct",
                        0,
                    )
                )

                atr_pct = float(
                    analisis_scanner.get(
                        "atr_pct",
                        0,
                    )
                )

                breakout = bool(
                    analisis_scanner.get(
                        "breakout",
                        False,
                    )
                )

                log.info(
                    f"[acciones scanner] "
                    f"{ticker}: "
                    f"score={score:.1f} "
                    f"comprar={comprar_scanner} "
                    f"RSI={rsi:.1f} "
                    f"vol={volumen_ratio:.2f}x "
                    f"momentum={momentum_pct:+.2f}% "
                    f"ATR={atr_pct:.2f}% "
                    f"breakout={breakout}"
                )

                if (
                    comprar_scanner
                    and not posicion_abierta
                ):

                    senal = "COMPRAR"

                    log.info(
                        f"[acciones scanner] "
                        f"{ticker}: 🚀 "
                        "OPORTUNIDAD DETECTADA — "
                        f"score={score:.1f}/100"
                    )

            except Exception as e:

                log.error(
                    f"[acciones scanner] "
                    f"{ticker}: error analizando "
                    f"impulso: {e}"
                )

                registrar_error_operativo(
                    f"scanner_acciones_{ticker}",
                    e,
                )

        # ====================================================
        # MOTOR DE PATRONES
        #
        # SOLO OBSERVA.
        # No puede cambiar la señal.
        # ====================================================

        registrar_observacion_pattern(
            ticker,
            df,
            analisis_scanner,
            senal,
        )

        # ====================================================
        # LOG GENERAL
        # ====================================================

        log.info(
            f"{ticker}: "
            f"precio=${precio_actual:.6f} "
            f"señal={senal} "
            f"posición_abierta="
            f"{posicion_abierta}"
        )

        # ====================================================
        # PROTECCIÓN ACCIONES
        # ====================================================

        if (
            posicion_abierta
            and not broker.es_cripto(
                ticker
            )
            and atr_actual is not None
        ):

            try:

                mensaje_proteccion = (
                    broker.proteger_posicion(
                        ticker,
                        atr_actual,
                    )
                )

                analisis_proteccion = (
                    broker.analizar_proteccion(
                        ticker
                    )
                )

                if analisis_proteccion.get(
                    "tiene_proteccion",
                    False,
                ):

                    limpiar_posicion_sin_proteccion(
                        ticker
                    )

                else:

                    marcar_posicion_sin_proteccion(
                        ticker
                    )

                if mensaje_proteccion:

                    notificaciones.notificar(
                        mensaje_proteccion
                    )

            except Exception as e:

                log.error(
                    f"{ticker}: error "
                    "protegiendo posición "
                    f"{e}"
                )

                marcar_posicion_sin_proteccion(
                    ticker
                )

                registrar_error_operativo(
                    f"proteccion_{ticker}",
                    e,
                )

        # ====================================================
        # CRYPTO
        #
        # IMPORTANTE:
        # La gestión crypto se realiza SOLO en
        # gestionar_posiciones_crypto().
        #
        # Se elimina aquí la antigua gestión duplicada
        # de stop/take/trailing.
        # ====================================================

        # ====================================================
        # COMPRA NORMAL
        # ====================================================

        if (
            senal == "COMPRAR"
            and not posicion_abierta
        ):

            if not puede_abrir_nueva_posicion(
                ticker
            ):

                return

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

                # Revisión de riesgo justo antes
                # de la llamada al broker.
                if not puede_abrir_nueva_posicion(
                    ticker
                ):

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

                try:

                    mensaje = broker.comprar(
                        ticker,
                        precio_actual,
                        atr_actual,
                    )

                except Exception as e:

                    registrar_error_operativo(
                        f"compra_{ticker}",
                        e,
                    )

                    log.error(
                        f"{ticker}: error "
                        f"comprando: {e}"
                    )

                    return

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

                try:

                    mensaje = broker.vender(
                        ticker
                    )

                except Exception as e:

                    registrar_error_operativo(
                        f"venta_{ticker}",
                        e,
                    )

                    log.error(
                        f"{ticker}: error "
                        f"vendiendo: {e}"
                    )

                    return

            _maximos_cripto.pop(
                ticker,
                None,
            )

            limpiar_posicion_sin_proteccion(
                ticker
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

        registrar_error_operativo(
            f"revisar_ticker_{ticker}",
            e,
        )


# ============================================================
# OBSERVACIÓN ACCIONES
# ============================================================

def observar_acciones_fuera_de_mercado():

    if not getattr(
        config,
        "STOCK_OBSERVATION_ENABLED",
        True,
    ):

        return

    if not config.TICKERS:

        return

    sesion = obtener_sesion_mercado()

    if sesion == "REGULAR":

        return

    log.info(
        "[acciones observación] "
        f"Sesión={sesion}. "
        "Registrando contexto de mercado."
    )

    for ticker in config.TICKERS:

        try:

            df = broker.obtener_datos(
                ticker
            )

            if df.empty:

                continue

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

            registrar_observacion_pattern(
                ticker,
                df,
                None,
                senal,
            )

        except Exception as e:

            log.warning(
                f"[acciones observación] "
                f"{ticker}: {e}"
            )

            registrar_error_operativo(
                f"observacion_acciones_{ticker}",
                e,
            )


# ============================================================
# LOOP ACCIONES
# ============================================================

def loop_acciones():

    if not config.TICKERS:

        return

    while True:

        try:

            abierto = broker.mercado_abierto()

            if abierto:

                log.info(
                    "[acciones] Scanner de "
                    "acciones ejecutando ciclo."
                )

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

                        registrar_error_operativo(
                            f"loop_acciones_{ticker}",
                            e,
                        )

            else:

                log.info(
                    "[acciones] Mercado cerrado. "
                    "Se activa observación."
                )

                observar_acciones_fuera_de_mercado()

        except Exception as e:

            log.error(
                "[acciones] Error en "
                f"el loop: {e}"
            )

            registrar_error_operativo(
                "loop_acciones",
                e,
            )

            try:

                notificaciones.notificar(
                    "⚠️ Error en el loop "
                    f"de acciones: {e}"
                )

            except Exception:
                pass

        intervalo = (
            config.CHECK_INTERVAL_MINUTES
            if broker.mercado_abierto()
            else getattr(
                config,
                "STOCK_OBSERVATION_INTERVAL_MINUTES",
                config.CHECK_INTERVAL_MINUTES,
            )
        )

        time.sleep(
            60 * intervalo
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

        registrar_error_operativo(
            "inicializar_monitor_ejecuciones",
            e,
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

                    registrar_error_operativo(
                        "procesar_ejecucion",
                        e,
                    )

        except Exception as e:

            log.error(
                "[ejecuciones] Error "
                "monitorizando órdenes: "
                f"{e}"
            )

            registrar_error_operativo(
                "loop_ejecuciones",
                e,
            )

        time.sleep(
            getattr(
                config,
                "EXECUTION_MONITOR_INTERVAL_SECONDS",
                15,
            )
        )


# ============================================================
# COOLDOWN CRYPTO
# ============================================================

def crypto_en_cooldown(
    ticker: str,
) -> bool:

    ahora = _ahora_utc()

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

        _guardar_estado()

        return False

    return True


def activar_cooldown_crypto(
    ticker: str,
):

    _cooldown_crypto[
        ticker
    ] = _ahora_utc()

    _guardar_estado()


# ============================================================
# COMPRA SCANNER CRYPTO
# ============================================================

def ejecutar_compra_scanner_crypto(
    ticker,
    df,
    analisis,
):

    try:

        if not puede_abrir_nueva_posicion(
            ticker
        ):

            return False

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

        if (
            broker.contar_posiciones_abiertas()
            >= config.MAX_POSICIONES_ABIERTAS
        ):

            log.info(
                "[crypto] Máximo de "
                "posiciones alcanzado."
            )

            return False

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
        # SEGUNDA COMPROBACIÓN DE SEGURIDAD
        # ----------------------------------------------------

        if not puede_abrir_nueva_posicion(
            ticker
        ):

            return False

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

            # El broker será responsable de realizar
            # la validación final de notional, buying power
            # y cantidad justo antes de enviar la orden.
            try:

                mensaje = broker.comprar(
                    ticker,
                    precio,
                    atr,
                )

            except Exception as e:

                registrar_error_operativo(
                    f"compra_crypto_{ticker}",
                    e,
                )

                log.error(
                    f"[crypto] {ticker}: "
                    f"error enviando compra: {e}"
                )

                return False

        if not mensaje:

            return False

        score = analisis.get(
            "score",
            0,
        )

        rsi = analisis.get(
            "rsi",
            0,
        )

        volumen = analisis.get(
            "volumen_ratio",
            0,
        )

        momentum = analisis.get(
            "momentum_pct",
            0,
        )

        razones = analisis.get(
            "motivo",
            [],
        )

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

        registrar_error_operativo(
            f"ejecutar_compra_scanner_{ticker}",
            e,
        )

        return False


# ============================================================
# SCANNER CRYPTO
# ============================================================

def ejecutar_scanner_crypto():

    global _ultimo_scan_crypto
    global _ultimo_candidato_crypto

    try:

        if nuevas_entradas_bloqueadas():

            log.warning(
                "[crypto] Scanner activo, "
                "pero nuevas entradas bloqueadas "
                "por seguridad."
            )

            _ultimo_scan_crypto = _ahora_utc()

            return

        universo = (
            broker.obtener_universo_crypto()
        )

        if not universo:

            log.warning(
                "[crypto] No se encontró "
                "ninguna crypto negociable."
            )

            return

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

        for ticker, df in datos.items():

            try:

                if df.empty:

                    continue

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

                # Registrar TODAS las observaciones
                # aunque no sean candidatas.
                registrar_observacion_pattern(
                    ticker,
                    df,
                    analisis,
                    (
                        "COMPRAR"
                        if analisis.get(
                            "comprar",
                            False,
                        )
                        else "ESPERAR"
                    ),
                )

                if score <= 0:

                    continue

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

                registrar_error_operativo(
                    f"analisis_crypto_{ticker}",
                    e,
                )

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

        _ultimo_scan_crypto = _ahora_utc()

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

        registrar_error_operativo(
            "ejecutar_scanner_crypto",
            e,
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

            registrar_error_operativo(
                "loop_scanner_crypto",
                e,
            )

        time.sleep(
            60
            * config.CRYPTO_SCAN_INTERVAL_MINUTES
        )


# ============================================================
# GESTIÓN ÚNICA DE POSICIONES CRYPTO
# ============================================================

def gestionar_posiciones_crypto():

    """
    ÚNICO lugar donde se ejecutan:

    - Stop loss crypto
    - Take profit crypto
    - Trailing stop crypto

    Se elimina la antigua gestión duplicada
    dentro de revisar_ticker().
    """

    try:

        posiciones = (
            broker.obtener_todas_las_posiciones()
        )

        tickers_presentes = set()

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

            tickers_presentes.add(
                ticker
            )

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

                # ==========================================
                # STOP LOSS
                # ==========================================

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

                        try:

                            mensaje = (
                                broker.vender(
                                    ticker
                                )
                            )

                        except Exception as e:

                            registrar_error_operativo(
                                f"stop_crypto_{ticker}",
                                e,
                            )

                            log.error(
                                f"[crypto] {ticker}: "
                                f"error STOP: {e}"
                            )

                            continue

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

                # ==========================================
                # TAKE PROFIT
                # ==========================================

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

                        try:

                            mensaje = (
                                broker.vender(
                                    ticker
                                )
                            )

                        except Exception as e:

                            registrar_error_operativo(
                                f"tp_crypto_{ticker}",
                                e,
                            )

                            log.error(
                                f"[crypto] {ticker}: "
                                f"error TP: {e}"
                            )

                            continue

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

                # ==========================================
                # TRAILING STOP
                # ==========================================

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

                            try:

                                mensaje = (
                                    broker.vender(
                                        ticker
                                    )
                                )

                            except Exception as e:

                                registrar_error_operativo(
                                    f"trailing_crypto_{ticker}",
                                    e,
                                )

                                log.error(
                                    f"[crypto] "
                                    f"{ticker}: "
                                    f"error trailing: {e}"
                                )

                                continue

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

                registrar_error_operativo(
                    f"gestionar_crypto_{ticker}",
                    e,
                )

        # Limpiar máximos de posiciones que ya no existen.
        for ticker in list(
            _maximos_cripto.keys()
        ):

            if ticker not in tickers_presentes:

                _maximos_cripto.pop(
                    ticker,
                    None,
                )

        _guardar_estado()

    except Exception as e:

        log.error(
            "[crypto] Error general "
            "gestionando posiciones: "
            f"{e}"
        )

        registrar_error_operativo(
            "gestionar_posiciones_crypto",
            e,
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

            registrar_error_operativo(
                "loop_proteccion_crypto",
                e,
            )

        time.sleep(
            config.CRYPTO_PROTECTION_INTERVAL_SECONDS
        )


# ============================================================
# WATCHDOG
# ============================================================

def watchdog_seguridad():

    log.info(
        "[watchdog] Watchdog de "
        "seguridad iniciado."
    )

    while True:

        try:

            actualizar_circuit_breaker()

            actualizar_control_perdida_diaria()

            sin_proteccion = (
                obtener_posiciones_sin_proteccion()
            )

            if sin_proteccion:

                log.warning(
                    "[watchdog] Posiciones "
                    "sin protección: "
                    f"{sin_proteccion}"
                )

                for ticker in sin_proteccion:

                    try:

                        proteger_compra_ejecutada(
                            ticker
                        )

                    except Exception as e:

                        log.error(
                            f"[watchdog] {ticker}: "
                            f"error recuperando "
                            f"protección: {e}"
                        )

            # Guardar estado periódicamente.
            _guardar_estado()

        except Exception as e:

            log.error(
                "[watchdog] Error: "
                f"{e}"
            )

            registrar_error_operativo(
                "watchdog",
                e,
            )

        time.sleep(
            config.WATCHDOG_INTERVAL_SECONDS
        )


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

                if analisis.get(
                    "tiene_proteccion",
                    False,
                ):

                    limpiar_posicion_sin_proteccion(
                        ticker
                    )

                    log.info(
                        f"[recuperación] "
                        f"{ticker}: protección "
                        "ya activa."
                    )

                    continue

                marcar_posicion_sin_proteccion(
                    ticker
                )

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

                marcar_posicion_sin_proteccion(
                    ticker
                )

                registrar_error_operativo(
                    f"recuperacion_{ticker}",
                    e,
                )

    except Exception as e:

        log.error(
            "[recuperación] Error general: "
            f"{e}"
        )

        registrar_error_operativo(
            "recuperar_protecciones",
            e,
        )


# ============================================================
# ESTADO DE SEGURIDAD PARA TELEGRAM
# ============================================================

def obtener_estado_seguridad():

    actualizar_circuit_breaker()

    try:

        actualizar_control_perdida_diaria()

    except Exception:

        pass

    with _lock_estado:

        circuit = bool(
            _estado_seguridad.get(
                "circuit_breaker",
                False,
            )
        )

        perdida = bool(
            _estado_seguridad.get(
                "perdida_diaria_bloqueada",
                False,
            )
        )

        errores = len(
            _estado_seguridad.get(
                "errores_recientes",
                [],
            )
        )

        sin_proteccion = list(
            _estado_seguridad.get(
                "posiciones_sin_proteccion",
                {},
            ).keys()
        )

    return {
        "circuit_breaker": circuit,
        "perdida_diaria": perdida,
        "errores": errores,
        "sin_proteccion": sin_proteccion,
    }


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

        seguridad = (
            obtener_estado_seguridad()
        )

        if seguridad[
            "circuit_breaker"
        ]:

            estado_seguridad = (
                "🚨 CIRCUIT BREAKER"
            )

        elif seguridad[
            "perdida_diaria"
        ]:

            estado_seguridad = (
                "🛑 PÉRDIDA DIARIA"
            )

        elif seguridad[
            "sin_proteccion"
        ]:

            estado_seguridad = (
                "⚠️ SIN PROTECCIÓN"
            )

        else:

            estado_seguridad = (
                "🟢 NORMAL"
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
            f"🛡️ Seguridad: "
            f"{estado_seguridad}\n"
            f"⚠️ Errores recientes: "
            f"{seguridad['errores']}\n"
            f"🔒 Sin protección: "
            f"{len(seguridad['sin_proteccion'])}\n\n"
            f"₿ Scanner crypto: {scanner}\n"
            f"📈 Scanner acciones: ACTIVO\n"
            f"👁️ Observación patrones: "
            f"{'ACTIVA' if config.PATTERN_ENGINE_ENABLED else 'DESACTIVADA'}\n"
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

            ultimo_scan = (
                "Todavía no ejecutado"
            )

        candidato = (
            _ultimo_candidato_crypto
            or "Ninguno"
        )

        seguridad = (
            obtener_estado_seguridad()
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
            f"🛡️ Seguridad: "
            f"{'BLOQUEADA' if seguridad['circuit_breaker'] or seguridad['perdida_diaria'] else 'NORMAL'}\n"
            "📈 Scanner acciones: ACTIVO\n"
            "🛡️ Protección crypto: ACTIVA\n"
            f"👁️ Patrones: "
            f"{'ACTIVO' if config.PATTERN_ENGINE_ENABLED else 'DESACTIVADO'}"
        )

    # ========================================================
    # NUEVO COMANDO: PATRONES
    # ========================================================

    if comando == "/patrones":

        ruta = getattr(
            config,
            "PATTERN_DATA_FILE",
            "pattern_observations.jsonl",
        )

        observaciones = 0

        try:

            if os.path.exists(
                ruta
            ):

                with open(
                    ruta,
                    "r",
                    encoding="utf-8",
                ) as archivo:

                    for _ in archivo:

                        observaciones += 1

        except Exception:

            pass

        return (
            "🧠 MOTOR DE PATRONES\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"Estado: "
            f"{'🟢 ACTIVO' if config.PATTERN_ENGINE_ENABLED else '🔴 DESACTIVADO'}\n"
            f"Modo trading: "
            f"{'⚠️ ACTIVO' if config.PATTERN_ENGINE_TRADING_ENABLED else '🛡️ SOLO OBSERVACIÓN'}\n\n"
            f"📊 Observaciones: "
            f"{observaciones:,}\n"
            f"🎯 Mínimo muestras: "
            f"{config.PATTERN_ENGINE_MIN_SAMPLES}\n"
            f"📈 Confianza mínima: "
            f"{config.PATTERN_ENGINE_MIN_CONFIDENCE:.0%}\n"
            f"⏱️ Horizontes: "
            f"{', '.join(str(x) + 'm' for x in config.PATTERN_FORWARD_HORIZONS_MINUTES)}\n"
            f"🔎 Siguiente apertura: "
            f"{'ACTIVA' if config.PATTERN_TRACK_NEXT_OPEN else 'DESACTIVADA'}\n\n"
            "ℹ️ El motor todavía NO puede "
            "comprar ni vender por patrones."
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
            "/scanner\n"
            "/patrones\n\n"
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

    # ========================================================
    # VALIDACIÓN
    # ========================================================

    config.validar()

    # ========================================================
    # RECUPERAR ESTADO
    # ========================================================

    _cargar_estado()

    # ========================================================
    # INICIO
    # ========================================================

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
        "Scanner acciones: ACTIVO"
    )

    log.info(
        "Observación fuera de mercado: "
        f"{'ACTIVA' if config.STOCK_OBSERVATION_ENABLED else 'DESACTIVADA'}"
    )

    log.info(
        "Scanner crypto: "
        f"{'ACTIVO' if config.CRYPTO_SCANNER_ENABLED else 'DESACTIVADO'}"
    )

    log.info(
        "Crypto scanner intervalo: "
        f"{config.CRYPTO_SCAN_INTERVAL_MINUTES} min"
    )

    log.info(
        "Motor de patrones: "
        f"{'ACTIVO' if config.PATTERN_ENGINE_ENABLED else 'DESACTIVADO'}"
    )

    log.info(
        "Trading por patrones: "
        f"{'ACTIVO' if config.PATTERN_ENGINE_TRADING_ENABLED else 'DESACTIVADO'}"
    )

    log.info(
        "Circuit breaker: "
        f"{'ACTIVO' if config.CIRCUIT_BREAKER_ENABLED else 'DESACTIVADO'}"
    )

    log.info(
        "Límite pérdida diaria: "
        f"{'ACTIVO' if config.DAILY_LOSS_LIMIT_ENABLED else 'DESACTIVADO'}"
    )

    # ========================================================
    # ESTADO INICIAL DE RIESGO
    # ========================================================

    try:

        actualizar_control_perdida_diaria()

    except Exception as e:

        log.warning(
            "[inicio] No se pudo actualizar "
            f"riesgo diario: {e}"
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
            f"📈 Scanner acciones: ACTIVO\n"
            f"👁️ Observación fuera mercado: "
            f"{'ACTIVA' if config.STOCK_OBSERVATION_ENABLED else 'DESACTIVADA'}\n"
            f"₿ Scanner crypto: "
            f"{'ACTIVO' if config.CRYPTO_SCANNER_ENABLED else 'DESACTIVADO'}\n"
            f"🧠 Patrones: "
            f"{'ACTIVO' if config.PATTERN_ENGINE_ENABLED else 'DESACTIVADO'}\n"
            f"🛡️ Trading patrones: "
            f"{'ACTIVO' if config.PATTERN_ENGINE_TRADING_ENABLED else 'SOLO OBSERVACIÓN'}"
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
    # RECUPERAR PROTECCIONES
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

    # --------------------------------------------------------
    # WATCHDOG
    # --------------------------------------------------------

    hilos.append(
        threading.Thread(
            target=watchdog_seguridad,
            daemon=True,
            name="WatchdogSeguridad",
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

        try:

            time.sleep(
                60
            )

            # Guardado periódico.
            _guardar_estado()

        except KeyboardInterrupt:

            log.info(
                "Bot detenido manualmente."
            )

            _guardar_estado()

            break

        except Exception as e:

            log.error(
                f"[main] Error keep-alive: {e}"
            )


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":

    main()
