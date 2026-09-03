"""
config.py

Configuración central del bot.

Gestiona:
- Alpaca
- Acciones
- Crypto
- Riesgo
- Estrategia
- Scanner crypto 24/7
- Telegram
"""

import os


# ============================================================
# UTILIDADES
# ============================================================

def _bool(nombre: str, default: bool) -> bool:

    valor = os.environ.get(nombre)

    if valor is None:
        return default

    return valor.strip().lower() in (
        "true",
        "1",
        "yes",
        "si",
        "sí",
    )


def _float(nombre: str, default: float) -> float:

    return float(
        os.environ.get(
            nombre,
            default,
        )
    )


def _int(nombre: str, default: int) -> int:

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
    t.strip().upper()
    for t in os.environ.get(
        "TICKERS",
        "AAPL,MSFT,NVDA,TSLA,AMZN",
    ).split(",")
    if t.strip()
]


# ============================================================
# CRYPTO MANUAL
# ============================================================

CRYPTO_TICKERS = [
    t.strip().upper()
    for t in os.environ.get(
        "CRYPTO_TICKERS",
        "BTC/USD,ETH/USD,SOL/USD",
    ).split(",")
    if t.strip()
]


# ============================================================
# SCANNER CRYPTO 24/7
# ============================================================

# Activa el descubrimiento automático de cryptos.
#
# TRUE:
# El bot busca automáticamente las cryptos
# negociables disponibles en Alpaca.
#
# FALSE:
# Utiliza solamente CRYPTO_TICKERS.

CRYPTO_SCANNER_ENABLED = _bool(
    "CRYPTO_SCANNER_ENABLED",
    True,
)


# Cada cuánto se ejecuta el scanner.
#
# 5 minutos = coincide con las velas crypto
# que estamos utilizando actualmente.

CRYPTO_SCAN_INTERVAL_MINUTES = _int(
    "CRYPTO_SCAN_INTERVAL_MINUTES",
    5,
)


# Número máximo de cryptos que se analizan
# en cada ciclo.

CRYPTO_MAX_SYMBOLS_SCAN = _int(
    "CRYPTO_MAX_SYMBOLS_SCAN",
    100,
)


# Número máximo de candidatos que pasan
# a la fase de análisis profundo.

CRYPTO_MAX_CANDIDATOS = _int(
    "CRYPTO_MAX_CANDIDATOS",
    10,
)


# Puntuación mínima necesaria para considerar
# una crypto como oportunidad.

CRYPTO_SCORE_MINIMO = _float(
    "CRYPTO_SCORE_MINIMO",
    70.0,
)


# ============================================================
# FILTROS DEL SCANNER
# ============================================================

# Volumen relativo mínimo.
#
# Ejemplo:
# 1.50 = volumen actual 50% superior
# a la media.

CRYPTO_VOLUMEN_MIN_MULTIPLICADOR = _float(
    "CRYPTO_VOLUMEN_MIN_MULTIPLICADOR",
    1.50,
)


# RSI mínimo para entrada.

CRYPTO_RSI_MIN = _float(
    "CRYPTO_RSI_MIN",
    50.0,
)


# RSI máximo.
#
# Evitamos comprar cuando el movimiento
# ya está excesivamente sobrecalentado.

CRYPTO_RSI_MAX = _float(
    "CRYPTO_RSI_MAX",
    68.0,
)


# ============================================================
# MOMENTUM
# ============================================================

# Subida máxima permitida durante las últimas
# velas antes de entrar.
#
# Evita perseguir una crypto que ya haya
# explotado demasiado.

CRYPTO_MAX_SUBIDA_PREVIA_PCT = _float(
    "CRYPTO_MAX_SUBIDA_PREVIA_PCT",
    4.0,
)


# Porcentaje mínimo de aceleración necesario
# para considerar que existe momentum.

CRYPTO_MOMENTUM_MIN_PCT = _float(
    "CRYPTO_MOMENTUM_MIN_PCT",
    0.30,
)


# ============================================================
# ATR / VOLATILIDAD
# ============================================================

CRYPTO_ATR_MIN_PCT = _float(
    "CRYPTO_ATR_MIN_PCT",
    0.003,
)


# ============================================================
# CONTROL DE ENTRADAS
# ============================================================

# Evita comprar el mismo símbolo repetidamente
# después de una salida.

CRYPTO_COOLDOWN_MINUTES = _int(
    "CRYPTO_COOLDOWN_MINUTES",
    30,
)


# Máximo de nuevas compras crypto en un solo ciclo.

CRYPTO_MAX_COMPRAS_POR_CICLO = _int(
    "CRYPTO_MAX_COMPRAS_POR_CICLO",
    1,
)


# ============================================================
# RIESGO GENERAL
# ============================================================

CHECK_INTERVAL_MINUTES = _int(
    "CHECK_INTERVAL_MINUTES",
    5,
)

CRYPTO_CHECK_INTERVAL_MINUTES = _int(
    "CRYPTO_CHECK_INTERVAL_MINUTES",
    5,
)

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
# ESTRATEGIA
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
# ATR / VOLUMEN
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
            "Configuralas en Railway "
            "(Settings -> Variables)."
        )
