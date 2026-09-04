"""
config.py

Configuración central del bot.

Las claves y secretos se obtienen exclusivamente
desde las variables de entorno de Railway.

IMPORTANTE:
- PAPER debe permanecer en true durante las pruebas.
- La cuenta secundaria es solo lectura.
- El scanner crypto opera únicamente en la cuenta principal.
- El motor de patrones inicialmente SOLO OBSERVA.
"""

import os


def _bool(nombre: str, default: bool) -> bool:
    valor = os.environ.get(nombre)
    if valor is None:
        return default
    return valor.strip().lower() in ("true", "1", "yes", "si", "sí", "on")


def _float(nombre: str, default: float) -> float:
    try:
        return float(os.environ.get(nombre, default))
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{nombre} debe ser un número.") from exc


def _int(nombre: str, default: int) -> int:
    try:
        return int(os.environ.get(nombre, default))
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{nombre} debe ser un entero.") from exc


# ============================================================
# ALPACA
# ============================================================

API_KEY = os.environ.get("ALPACA_API_KEY", "")
API_SECRET = os.environ.get("ALPACA_API_SECRET", "")
PAPER = _bool("ALPACA_PAPER", True)


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

CHECK_INTERVAL_MINUTES = _int("CHECK_INTERVAL_MINUTES", 5)
STOCK_OBSERVATION_ENABLED = _bool("STOCK_OBSERVATION_ENABLED", True)
STOCK_OBSERVATION_INTERVAL_MINUTES = _int("STOCK_OBSERVATION_INTERVAL_MINUTES", 5)
STOCK_OBSERVATION_LOOKBACK_DAYS = _int("STOCK_OBSERVATION_LOOKBACK_DAYS", 30)

# Perfil activo: escaneo frecuente, manteniendo los cortafuegos de riesgo.
CRYPTO_SCAN_INTERVAL_MINUTES = _int("CRYPTO_SCAN_INTERVAL_MINUTES", 3)
CRYPTO_PROTECTION_INTERVAL_SECONDS = _int("CRYPTO_PROTECTION_INTERVAL_SECONDS", 15)
EXECUTION_MONITOR_INTERVAL_SECONDS = _int("EXECUTION_MONITOR_INTERVAL_SECONDS", 10)
WATCHDOG_INTERVAL_SECONDS = _int("WATCHDOG_INTERVAL_SECONDS", 30)


# ============================================================
# RIESGO GENERAL — ACCIONES
# ============================================================

RISK_PER_TRADE_PCT = _float("RISK_PER_TRADE_PCT", 0.02)
STOP_LOSS_PCT = _float("STOP_LOSS_PCT", 0.02)
TAKE_PROFIT_PCT = _float("TAKE_PROFIT_PCT", 0.04)
ATR_STOP_MULTIPLICADOR = _float("ATR_STOP_MULTIPLICADOR", 1.5)
ATR_TAKE_PROFIT_MULTIPLICADOR = _float("ATR_TAKE_PROFIT_MULTIPLICADOR", 3.0)
TRAILING_STOP_PCT = _float("TRAILING_STOP_PCT", 0.015)
MAX_POSICIONES_ABIERTAS = _int("MAX_POSICIONES_ABIERTAS", 3)


# ============================================================
# RIESGO CRYPTO
# ============================================================

CRYPTO_RISK_PER_TRADE_PCT = _float("CRYPTO_RISK_PER_TRADE_PCT", 0.01)
CRYPTO_MAX_NOTIONAL_PCT = _float("CRYPTO_MAX_NOTIONAL_PCT", 0.10)


# ============================================================
# LIMITES ABSOLUTOS DE ÓRDENES
# ============================================================

CRYPTO_MAX_ORDER_NOTIONAL_USD = _float("CRYPTO_MAX_ORDER_NOTIONAL_USD", 200000.0)
CRYPTO_INTERNAL_MAX_ORDER_NOTIONAL_USD = _float(
    "CRYPTO_INTERNAL_MAX_ORDER_NOTIONAL_USD", 100000.0
)
MAX_BUYING_POWER_USAGE_PCT = _float("MAX_BUYING_POWER_USAGE_PCT", 0.90)
MAX_ORDER_PRICE_DEVIATION_PCT = _float("MAX_ORDER_PRICE_DEVIATION_PCT", 0.03)


# ============================================================
# CIRCUIT BREAKER
# ============================================================

CIRCUIT_BREAKER_ENABLED = _bool("CIRCUIT_BREAKER_ENABLED", True)
CIRCUIT_BREAKER_MAX_ERRORS = _int("CIRCUIT_BREAKER_MAX_ERRORS", 5)
CIRCUIT_BREAKER_WINDOW_MINUTES = _int("CIRCUIT_BREAKER_WINDOW_MINUTES", 15)
CIRCUIT_BREAKER_COOLDOWN_MINUTES = _int("CIRCUIT_BREAKER_COOLDOWN_MINUTES", 30)


# ============================================================
# PERDIDA DIARIA MAXIMA
# ============================================================

DAILY_LOSS_LIMIT_ENABLED = _bool("DAILY_LOSS_LIMIT_ENABLED", True)
DAILY_LOSS_LIMIT_PCT = _float("DAILY_LOSS_LIMIT_PCT", 0.05)


# ============================================================
# PROTECCION POST-COMPRA
# ============================================================

REQUIRE_PROTECTION_FOR_NEW_ENTRIES = _bool("REQUIRE_PROTECTION_FOR_NEW_ENTRIES", True)
PROTECTION_MAX_WAIT_SECONDS = _int("PROTECTION_MAX_WAIT_SECONDS", 30)
PROTECTION_RETRY_SECONDS = _int("PROTECTION_RETRY_SECONDS", 5)
PROTECTION_MAX_RETRIES = _int("PROTECTION_MAX_RETRIES", 5)


# ============================================================
# EXPOSICION
# ============================================================

MAX_TOTAL_EXPOSURE_PCT = _float("MAX_TOTAL_EXPOSURE_PCT", 0.50)
MAX_SINGLE_POSITION_PCT = _float("MAX_SINGLE_POSITION_PCT", 0.20)


# ============================================================
# ESTRATEGIA ACCIONES
# ============================================================

EMA_RAPIDA = _int("EMA_RAPIDA", 9)
EMA_LENTA = _int("EMA_LENTA", 21)
EMA_TENDENCIA = _int("EMA_TENDENCIA", 200)
RSI_PERIODO = _int("RSI_PERIODO", 14)
RSI_SOBRECOMPRA = _int("RSI_SOBRECOMPRA", 70)
RSI_SOBREVENTA = _int("RSI_SOBREVENTA", 30)
MARGEN_SALIDA_PCT = _float("MARGEN_SALIDA_PCT", 0.05)


# ============================================================
# INDICADORES GENERALES
# ============================================================

ATR_PERIODO = _int("ATR_PERIODO", 14)
ATR_MIN_PCT = _float("ATR_MIN_PCT", 0.003)
VOLUMEN_SMA_PERIODO = _int("VOLUMEN_SMA_PERIODO", 20)
VOLUMEN_MIN_MULTIPLICADOR = _float("VOLUMEN_MIN_MULTIPLICADOR", 1.0)


# ============================================================
# SCANNER CRYPTO — PERFIL AGRESIVO CONTROLADO
# ============================================================

CRYPTO_SCANNER_ENABLED = _bool("CRYPTO_SCANNER_ENABLED", True)
CRYPTO_MAX_SYMBOLS_SCAN = _int("CRYPTO_MAX_SYMBOLS_SCAN", 150)
CRYPTO_UNIVERSE_REFRESH_MINUTES = _int("CRYPTO_UNIVERSE_REFRESH_MINUTES", 30)
CRYPTO_SCAN_BATCH_SIZE = _int("CRYPTO_SCAN_BATCH_SIZE", 50)
CRYPTO_EXCLUIR_ESTABLES = _bool("CRYPTO_EXCLUIR_ESTABLES", True)
CRYPTO_MAX_CANDIDATOS = _int("CRYPTO_MAX_CANDIDATOS", 12)

# Se baja moderadamente el umbral para capturar más impulsos,
# pero las condiciones estructurales siguen siendo obligatorias.
CRYPTO_SCORE_MINIMO = _float("CRYPTO_SCORE_MINIMO", 70)
CRYPTO_MAX_COMPRAS_POR_CICLO = _int("CRYPTO_MAX_COMPRAS_POR_CICLO", 2)
CRYPTO_COOLDOWN_MINUTES = _int("CRYPTO_COOLDOWN_MINUTES", 15)
CRYPTO_BREAKOUT_LOOKBACK = _int("CRYPTO_BREAKOUT_LOOKBACK", 12)
CRYPTO_MOMENTUM_BARS = _int("CRYPTO_MOMENTUM_BARS", 3)
CRYPTO_MIN_MOMENTUM_PCT = _float("CRYPTO_MIN_MOMENTUM_PCT", 0.20)
CRYPTO_MAX_RISE_PCT = _float("CRYPTO_MAX_RISE_PCT", 10.0)
CRYPTO_VOLUME_MIN_MULTIPLICADOR = _float("CRYPTO_VOLUME_MIN_MULTIPLICADOR", 1.25)
CRYPTO_RSI_MIN = _float("CRYPTO_RSI_MIN", 48)
CRYPTO_RSI_MAX = _float("CRYPTO_RSI_MAX", 72)


# ============================================================
# MOTOR DE PATRONES
# ============================================================

PATTERN_ENGINE_ENABLED = _bool("PATTERN_ENGINE_ENABLED", True)
PATTERN_ENGINE_TRADING_ENABLED = _bool("PATTERN_ENGINE_TRADING_ENABLED", False)
PATTERN_ENGINE_MIN_SAMPLES = _int("PATTERN_ENGINE_MIN_SAMPLES", 100)
PATTERN_ENGINE_MIN_CONFIDENCE = _float("PATTERN_ENGINE_MIN_CONFIDENCE", 0.65)
PATTERN_ENGINE_MIN_EXPECTED_RETURN_PCT = _float("PATTERN_ENGINE_MIN_EXPECTED_RETURN_PCT", 0.20)
PATTERN_ENGINE_MAX_LOOKBACK_ROWS = _int("PATTERN_ENGINE_MAX_LOOKBACK_ROWS", 50000)
PATTERN_FORWARD_HORIZONS_MINUTES = [5, 15, 30, 60]
PATTERN_TRACK_NEXT_OPEN = _bool("PATTERN_TRACK_NEXT_OPEN", True)
PATTERN_DEDUPLICATION_ENABLED = _bool("PATTERN_DEDUPLICATION_ENABLED", True)
PATTERN_MIN_OBSERVATION_INTERVAL_SECONDS = _int("PATTERN_MIN_OBSERVATION_INTERVAL_SECONDS", 60)
PATTERN_TRACK_SESSION = _bool("PATTERN_TRACK_SESSION", True)
PATTERN_TRACK_PRICE = _bool("PATTERN_TRACK_PRICE", True)
PATTERN_TRACK_VOLUME = _bool("PATTERN_TRACK_VOLUME", True)
PATTERN_TRACK_RSI = _bool("PATTERN_TRACK_RSI", True)
PATTERN_TRACK_MACD = _bool("PATTERN_TRACK_MACD", True)
PATTERN_TRACK_EMAS = _bool("PATTERN_TRACK_EMAS", True)
PATTERN_TRACK_ATR = _bool("PATTERN_TRACK_ATR", True)
PATTERN_TRACK_MOMENTUM = _bool("PATTERN_TRACK_MOMENTUM", True)
PATTERN_TRACK_BREAKOUT = _bool("PATTERN_TRACK_BREAKOUT", True)
PATTERN_TRACK_GAP = _bool("PATTERN_TRACK_GAP", True)


# ============================================================
# PERSISTENCIA
# ============================================================

STATE_PERSISTENCE_ENABLED = _bool("STATE_PERSISTENCE_ENABLED", True)
STATE_FILE = os.environ.get("STATE_FILE", "bot_state.json")
PATTERN_DATA_FILE = os.environ.get("PATTERN_DATA_FILE", "pattern_observations.jsonl")


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
BOT_NOMBRE = os.environ.get("BOT_NOMBRE", "CUENTA PRINCIPAL - TRANQUILO")


# ============================================================
# LOGGING
# ============================================================

LOG_PATTERN_OBSERVATIONS = _bool("LOG_PATTERN_OBSERVATIONS", True)
LOG_ORDER_VALIDATION = _bool("LOG_ORDER_VALIDATION", True)
LOG_RISK_CHECKS = _bool("LOG_RISK_CHECKS", True)


def validar():
    """Valida toda la configuración antes de arrancar el bot."""
    faltantes = []
    if not API_KEY:
        faltantes.append("ALPACA_API_KEY")
    if not API_SECRET:
        faltantes.append("ALPACA_API_SECRET")
    if faltantes:
        raise RuntimeError(
            "Faltan variables de entorno: "
            f"{', '.join(faltantes)}. Configúralas en Railway (Settings -> Variables)."
        )

    if RISK_PER_TRADE_PCT <= 0 or RISK_PER_TRADE_PCT > 1:
        raise RuntimeError("RISK_PER_TRADE_PCT debe estar entre 0 y 1.")
    if CRYPTO_RISK_PER_TRADE_PCT <= 0 or CRYPTO_RISK_PER_TRADE_PCT > 1:
        raise RuntimeError("CRYPTO_RISK_PER_TRADE_PCT debe estar entre 0 y 1.")
    if STOP_LOSS_PCT <= 0 or STOP_LOSS_PCT >= 1:
        raise RuntimeError("STOP_LOSS_PCT debe estar entre 0 y 1.")
    if TAKE_PROFIT_PCT <= 0 or TAKE_PROFIT_PCT >= 1:
        raise RuntimeError("TAKE_PROFIT_PCT debe estar entre 0 y 1.")
    if TRAILING_STOP_PCT <= 0 or TRAILING_STOP_PCT >= 1:
        raise RuntimeError("TRAILING_STOP_PCT debe estar entre 0 y 1.")
    if CRYPTO_MAX_NOTIONAL_PCT <= 0 or CRYPTO_MAX_NOTIONAL_PCT > 1:
        raise RuntimeError("CRYPTO_MAX_NOTIONAL_PCT debe estar entre 0 y 1.")
    if MAX_POSICIONES_ABIERTAS <= 0:
        raise RuntimeError("MAX_POSICIONES_ABIERTAS debe ser mayor que 0.")

    if CRYPTO_MAX_ORDER_NOTIONAL_USD <= 0:
        raise RuntimeError("CRYPTO_MAX_ORDER_NOTIONAL_USD debe ser mayor que 0.")
    if CRYPTO_INTERNAL_MAX_ORDER_NOTIONAL_USD <= 0:
        raise RuntimeError("CRYPTO_INTERNAL_MAX_ORDER_NOTIONAL_USD debe ser mayor que 0.")
    if CRYPTO_INTERNAL_MAX_ORDER_NOTIONAL_USD > CRYPTO_MAX_ORDER_NOTIONAL_USD:
        raise RuntimeError("CRYPTO_INTERNAL_MAX_ORDER_NOTIONAL_USD no puede superar CRYPTO_MAX_ORDER_NOTIONAL_USD.")
    if MAX_BUYING_POWER_USAGE_PCT <= 0 or MAX_BUYING_POWER_USAGE_PCT > 1:
        raise RuntimeError("MAX_BUYING_POWER_USAGE_PCT debe estar entre 0 y 1.")
    if MAX_ORDER_PRICE_DEVIATION_PCT <= 0 or MAX_ORDER_PRICE_DEVIATION_PCT >= 1:
        raise RuntimeError("MAX_ORDER_PRICE_DEVIATION_PCT debe estar entre 0 y 1.")

    if MAX_TOTAL_EXPOSURE_PCT <= 0 or MAX_TOTAL_EXPOSURE_PCT > 1:
        raise RuntimeError("MAX_TOTAL_EXPOSURE_PCT debe estar entre 0 y 1.")
    if MAX_SINGLE_POSITION_PCT <= 0 or MAX_SINGLE_POSITION_PCT > 1:
        raise RuntimeError("MAX_SINGLE_POSITION_PCT debe estar entre 0 y 1.")
    if MAX_SINGLE_POSITION_PCT > MAX_TOTAL_EXPOSURE_PCT:
        raise RuntimeError("MAX_SINGLE_POSITION_PCT no puede superar MAX_TOTAL_EXPOSURE_PCT.")

    if CIRCUIT_BREAKER_MAX_ERRORS <= 0 or CIRCUIT_BREAKER_WINDOW_MINUTES <= 0 or CIRCUIT_BREAKER_COOLDOWN_MINUTES <= 0:
        raise RuntimeError("Los parámetros del circuit breaker deben ser mayores que 0.")
    if DAILY_LOSS_LIMIT_PCT <= 0 or DAILY_LOSS_LIMIT_PCT >= 1:
        raise RuntimeError("DAILY_LOSS_LIMIT_PCT debe estar entre 0 y 1.")
    if PROTECTION_MAX_WAIT_SECONDS <= 0 or PROTECTION_RETRY_SECONDS <= 0 or PROTECTION_MAX_RETRIES <= 0:
        raise RuntimeError("Los parámetros de protección deben ser mayores que 0.")
    if CHECK_INTERVAL_MINUTES <= 0 or STOCK_OBSERVATION_INTERVAL_MINUTES <= 0 or CRYPTO_SCAN_INTERVAL_MINUTES <= 0:
        raise RuntimeError("Los intervalos deben ser mayores que 0.")
    if CRYPTO_PROTECTION_INTERVAL_SECONDS <= 0 or EXECUTION_MONITOR_INTERVAL_SECONDS <= 0 or WATCHDOG_INTERVAL_SECONDS <= 0:
        raise RuntimeError("Los intervalos de ejecución deben ser mayores que 0.")

    if CRYPTO_SCORE_MINIMO < 0 or CRYPTO_SCORE_MINIMO > 100:
        raise RuntimeError("CRYPTO_SCORE_MINIMO debe estar entre 0 y 100.")
    if CRYPTO_MAX_SYMBOLS_SCAN <= 0 or CRYPTO_SCAN_BATCH_SIZE <= 0 or CRYPTO_MAX_CANDIDATOS <= 0:
        raise RuntimeError("Los límites del scanner crypto deben ser mayores que 0.")
    if CRYPTO_MAX_COMPRAS_POR_CICLO <= 0 or CRYPTO_COOLDOWN_MINUTES < 0:
        raise RuntimeError("Los parámetros de compras crypto no son válidos.")
    if CRYPTO_BREAKOUT_LOOKBACK <= 0 or CRYPTO_MOMENTUM_BARS <= 0:
        raise RuntimeError("Los parámetros de breakout/momentum deben ser mayores que 0.")
    if CRYPTO_VOLUME_MIN_MULTIPLICADOR <= 0:
        raise RuntimeError("CRYPTO_VOLUME_MIN_MULTIPLICADOR debe ser mayor que 0.")
    if CRYPTO_RSI_MIN < 0 or CRYPTO_RSI_MIN > 100 or CRYPTO_RSI_MAX < 0 or CRYPTO_RSI_MAX > 100:
        raise RuntimeError("Los límites RSI crypto deben estar entre 0 y 100.")
    if CRYPTO_RSI_MIN >= CRYPTO_RSI_MAX:
        raise RuntimeError("CRYPTO_RSI_MIN debe ser menor que CRYPTO_RSI_MAX.")

    if PATTERN_ENGINE_MIN_SAMPLES <= 0:
        raise RuntimeError("PATTERN_ENGINE_MIN_SAMPLES debe ser mayor que 0.")
    if PATTERN_ENGINE_MIN_CONFIDENCE <= 0 or PATTERN_ENGINE_MIN_CONFIDENCE > 1:
        raise RuntimeError("PATTERN_ENGINE_MIN_CONFIDENCE debe estar entre 0 y 1.")
    if PATTERN_ENGINE_MAX_LOOKBACK_ROWS <= 0:
        raise RuntimeError("PATTERN_ENGINE_MAX_LOOKBACK_ROWS debe ser mayor que 0.")
    if not PATTERN_FORWARD_HORIZONS_MINUTES or any(h <= 0 for h in PATTERN_FORWARD_HORIZONS_MINUTES):
        raise RuntimeError("PATTERN_FORWARD_HORIZONS_MINUTES contiene valores inválidos.")

    if PATTERN_ENGINE_TRADING_ENABLED:
        print("ADVERTENCIA: PATTERN_ENGINE_TRADING_ENABLED=True. El motor de patrones podrá influir en señales.")

    return True
