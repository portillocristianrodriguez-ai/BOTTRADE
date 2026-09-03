"""
config.py

Configuración central del bot.

Las claves y secretos se obtienen exclusivamente
desde las variables de entorno de Railway.

IMPORTANTE:
- PAPER debe permanecer en true durante las pruebas.
- La cuenta secundaria es solo lectura.
- El scanner crypto opera únicamente en la cuenta principal.
"""

import os


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def _bool(
    nombre: str,
    default: bool,
) -> bool:

    valor = os.environ.get(
        nombre
    )

    if valor is None:
        return default

    return valor.strip().lower() in (
        "true",
        "1",
        "yes",
        "si",
        "sí",
    )


def _float(
    nombre: str,
    default: float,
) -> float:

    return float(
        os.environ.get(
            nombre,
            default,
        )
    )


def _int(
    nombre: str,
    default: int,
) -> int:

    return int(
        os.environ.get(
            nombre,
            default,
        )
    )


# ============================================================
# ALPACA
# ============================================================

API_KEY = os.environ.get(
    "ALPACA_API_KEY",
    "",
)

API_SECRET = os.environ.get(
    "ALPACA_API_SECRET",
    "",
)

PAPER = _bool(
    "ALPACA_PAPER",
    True,
)


# ============================================================
# ACCIONES
# ============================================================

TICKERS = [
    ticker.strip().upper()
    for ticker in os.environ.get(
        "TICKERS",
        "AAPL,MSFT,NVDA,TSLA,AMZN",
    ).split(",")
    if ticker.strip()
]


# ============================================================
# CRYPTO
# ============================================================

"""
CRYPTO_TICKERS queda como fallback.

El scanner nuevo NO depende únicamente de esta lista:
descubre automáticamente los activos crypto USD
negociables de Alpaca.
"""

CRYPTO_TICKERS = [
    ticker.strip().upper()
    for ticker in os.environ.get(
        "CRYPTO_TICKERS",
        "BTC/USD,ETH/USD,SOL/USD",
    ).split(",")
    if ticker.strip()
]


# ============================================================
# INTERVALOS
# ============================================================

# Acciones
CHECK_INTERVAL_MINUTES = _int(
    "CHECK_INTERVAL_MINUTES",
    5,
)


# Scanner crypto
CRYPTO_SCAN_INTERVAL_MINUTES = _int(
    "CRYPTO_SCAN_INTERVAL_MINUTES",
    5,
)


# Protección crypto
CRYPTO_PROTECTION_INTERVAL_SECONDS = _int(
    "CRYPTO_PROTECTION_INTERVAL_SECONDS",
    15,
)


# ============================================================
# RIESGO GENERAL — ACCIONES
# ============================================================

RISK_PER_TRADE_PCT = _float(
    "RISK_PER_TRADE_PCT",
    0.02,
)

STOP_LOSS_PCT = _float(
    "STOP_LOSS_PCT",
    0.02,
)

TAKE_PROFIT_PCT = _float(
    "TAKE_PROFIT_PCT",
    0.04,
)

ATR_STOP_MULTIPLICADOR = _float(
    "ATR_STOP_MULTIPLICADOR",
    1.5,
)

ATR_TAKE_PROFIT_MULTIPLICADOR = _float(
    "ATR_TAKE_PROFIT_MULTIPLICADOR",
    3.0,
)

TRAILING_STOP_PCT = _float(
    "TRAILING_STOP_PCT",
    0.015,
)

MAX_POSICIONES_ABIERTAS = _int(
    "MAX_POSICIONES_ABIERTAS",
    3,
)


# ============================================================
# RIESGO CRYPTO
# ============================================================

"""
Crypto utiliza un riesgo independiente de las acciones.

1% de equity como riesgo teórico por operación.

Además, ninguna operación crypto podrá superar
el porcentaje máximo de equity definido abajo.
"""

CRYPTO_RISK_PER_TRADE_PCT = _float(
    "CRYPTO_RISK_PER_TRADE_PCT",
    0.01,
)

CRYPTO_MAX_NOTIONAL_PCT = _float(
    "CRYPTO_MAX_NOTIONAL_PCT",
    0.10,
)


# ============================================================
# ESTRATEGIA ACCIONES
# ============================================================

EMA_RAPIDA = _int(
    "EMA_RAPIDA",
    9,
)

EMA_LENTA = _int(
    "EMA_LENTA",
    21,
)

EMA_TENDENCIA = _int(
    "EMA_TENDENCIA",
    200,
)

RSI_PERIODO = _int(
    "RSI_PERIODO",
    14,
)

RSI_SOBRECOMPRA = _int(
    "RSI_SOBRECOMPRA",
    70,
)

RSI_SOBREVENTA = _int(
    "RSI_SOBREVENTA",
    30,
)

MARGEN_SALIDA_PCT = _float(
    "MARGEN_SALIDA_PCT",
    0.05,
)


# ============================================================
# INDICADORES GENERALES
# ============================================================

ATR_PERIODO = _int(
    "ATR_PERIODO",
    14,
)

ATR_MIN_PCT = _float(
    "ATR_MIN_PCT",
    0.003,
)

VOLUMEN_SMA_PERIODO = _int(
    "VOLUMEN_SMA_PERIODO",
    20,
)

VOLUMEN_MIN_MULTIPLICADOR = _float(
    "VOLUMEN_MIN_MULTIPLICADOR",
    1.0,
)


# ============================================================
# SCANNER CRYPTO
# ============================================================

"""
El scanner busca oportunidades de impulso temprano
en crypto utilizando velas de 5 minutos.

No intenta adivinar el mínimo exacto.

Busca:
- tendencia
- aceleración
- ruptura
- volumen
- momentum
- RSI
- MACD
- volatilidad
"""


CRYPTO_SCANNER_ENABLED = _bool(
    "CRYPTO_SCANNER_ENABLED",
    True,
)


# ------------------------------------------------------------
# UNIVERSO
# ------------------------------------------------------------

# Número máximo de símbolos procesados por ciclo.

CRYPTO_MAX_SYMBOLS_SCAN = _int(
    "CRYPTO_MAX_SYMBOLS_SCAN",
    100,
)


# Tiempo durante el cual se conserva
# el universo descubierto.

CRYPTO_UNIVERSE_REFRESH_MINUTES = _int(
    "CRYPTO_UNIVERSE_REFRESH_MINUTES",
    30,
)


# Tamaño de cada petición de datos.

CRYPTO_SCAN_BATCH_SIZE = _int(
    "CRYPTO_SCAN_BATCH_SIZE",
    50,
)


# ------------------------------------------------------------
# FILTROS
# ------------------------------------------------------------

# Excluir stablecoins.

CRYPTO_EXCLUIR_ESTABLES = _bool(
    "CRYPTO_EXCLUIR_ESTABLES",
    True,
)


# Número de mejores candidatos que se
# conservan después del análisis.

CRYPTO_MAX_CANDIDATOS = _int(
    "CRYPTO_MAX_CANDIDATOS",
    10,
)


# ------------------------------------------------------------
# SCORE
# ------------------------------------------------------------

CRYPTO_SCORE_MINIMO = _float(
    "CRYPTO_SCORE_MINIMO",
    75,
)


# ------------------------------------------------------------
# COMPRAS
# ------------------------------------------------------------

# Máximo de nuevas compras crypto por ciclo.

CRYPTO_MAX_COMPRAS_POR_CICLO = _int(
    "CRYPTO_MAX_COMPRAS_POR_CICLO",
    1,
)


# Tiempo que debe pasar antes de volver a
# entrar en el mismo activo después de una operación.

CRYPTO_COOLDOWN_MINUTES = _int(
    "CRYPTO_COOLDOWN_MINUTES",
    30,
)


# ------------------------------------------------------------
# BREAKOUT
# ------------------------------------------------------------

# Número de velas utilizadas para determinar
# una ruptura reciente.

CRYPTO_BREAKOUT_LOOKBACK = _int(
    "CRYPTO_BREAKOUT_LOOKBACK",
    12,
)


# ------------------------------------------------------------
# MOMENTUM
# ------------------------------------------------------------

# Número de velas para medir momentum.

CRYPTO_MOMENTUM_BARS = _int(
    "CRYPTO_MOMENTUM_BARS",
    3,
)


# Momentum mínimo requerido.

CRYPTO_MIN_MOMENTUM_PCT = _float(
    "CRYPTO_MIN_MOMENTUM_PCT",
    0.30,
)


# Evita comprar después de movimientos
# demasiado extendidos.

CRYPTO_MAX_RISE_PCT = _float(
    "CRYPTO_MAX_RISE_PCT",
    10.0,
)


# ------------------------------------------------------------
# VOLUMEN
# ------------------------------------------------------------

# Volumen mínimo respecto a su media.

CRYPTO_VOLUME_MIN_MULTIPLICADOR = _float(
    "CRYPTO_VOLUME_MIN_MULTIPLICADOR",
    1.50,
)


# ------------------------------------------------------------
# RSI
# ------------------------------------------------------------

CRYPTO_RSI_MIN = _float(
    "CRYPTO_RSI_MIN",
    50,
)

CRYPTO_RSI_MAX = _float(
    "CRYPTO_RSI_MAX",
    68,
)


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_BOT_TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN",
    "",
)

TELEGRAM_CHAT_ID = os.environ.get(
    "TELEGRAM_CHAT_ID",
    "",
)


BOT_NOMBRE = os.environ.get(
    "BOT_NOMBRE",
    "CUENTA PRINCIPAL - TRANQUILO",
)


# ============================================================
# VALIDACIÓN
# ============================================================

def validar():

    faltantes = []

    if not API_KEY:

        faltantes.append(
            "ALPACA_API_KEY"
        )

    if not API_SECRET:

        faltantes.append(
            "ALPACA_API_SECRET"
        )

    if faltantes:

        raise RuntimeError(
            "Faltan variables de entorno: "
            f"{', '.join(faltantes)}. "
            "Configúralas en Railway "
            "(Settings -> Variables)."
        )

    # --------------------------------------------------------
    # VALIDACIONES DE SEGURIDAD
    # --------------------------------------------------------

    if (
        RISK_PER_TRADE_PCT <= 0
        or RISK_PER_TRADE_PCT > 1
    ):

        raise RuntimeError(
            "RISK_PER_TRADE_PCT debe estar "
            "entre 0 y 1."
        )

    if (
        CRYPTO_RISK_PER_TRADE_PCT <= 0
        or CRYPTO_RISK_PER_TRADE_PCT > 1
    ):

        raise RuntimeError(
            "CRYPTO_RISK_PER_TRADE_PCT debe "
            "estar entre 0 y 1."
        )

    if (
        CRYPTO_MAX_NOTIONAL_PCT <= 0
        or CRYPTO_MAX_NOTIONAL_PCT > 1
    ):

        raise RuntimeError(
            "CRYPTO_MAX_NOTIONAL_PCT debe "
            "estar entre 0 y 1."
        )

    if (
        MAX_POSICIONES_ABIERTAS
        <= 0
    ):

        raise RuntimeError(
            "MAX_POSICIONES_ABIERTAS debe "
            "ser mayor que 0."
        )

    if (
        CRYPTO_SCORE_MINIMO < 0
        or CRYPTO_SCORE_MINIMO > 100
    ):

        raise RuntimeError(
            "CRYPTO_SCORE_MINIMO debe "
            "estar entre 0 y 100."
        )

    if (
        CRYPTO_MAX_SYMBOLS_SCAN
        <= 0
    ):

        raise RuntimeError(
            "CRYPTO_MAX_SYMBOLS_SCAN debe "
            "ser mayor que 0."
        )

    if (
        CRYPTO_SCAN_BATCH_SIZE
        <= 0
    ):

        raise RuntimeError(
            "CRYPTO_SCAN_BATCH_SIZE debe "
            "ser mayor que 0."
        )
