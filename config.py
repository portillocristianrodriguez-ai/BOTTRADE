"""
Configuración del bot. Todo se lee de variables de entorno para poder
deployar en Railway sin exponer claves en el código.
"""

import os


def _bool(nombre: str, default: bool) -> bool:
    valor = os.environ.get(nombre)
    if valor is None:
        return default
    return valor.strip().lower() in ("true", "1", "yes", "si", "sí")


def _float(nombre: str, default: float) -> float:
    return float(os.environ.get(nombre, default))


def _int(nombre: str, default: int) -> int:
    return int(os.environ.get(nombre, default))


API_KEY = os.environ.get("ALPACA_API_KEY", "")
API_SECRET = os.environ.get("ALPACA_API_SECRET", "")
PAPER = _bool("ALPACA_PAPER", True)

TICKERS = [t.strip().upper() for t in os.environ.get("TICKERS", "AAPL,MSFT,NVDA,TSLA,AMZN").split(",") if t.strip()]

CRYPTO_TICKERS = [t.strip().upper() for t in os.environ.get("CRYPTO_TICKERS", "").split(",") if t.strip()]

CHECK_INTERVAL_MINUTES = _int("CHECK_INTERVAL_MINUTES", 5)
CRYPTO_CHECK_INTERVAL_MINUTES = _int("CRYPTO_CHECK_INTERVAL_MINUTES", 1)
RISK_PER_TRADE_PCT = _float("RISK_PER_TRADE_PCT", 0.02)
STOP_LOSS_PCT = _float("STOP_LOSS_PCT", 0.02)
TAKE_PROFIT_PCT = _float("TAKE_PROFIT_PCT", 0.04)
ATR_STOP_MULTIPLICADOR = _float("ATR_STOP_MULTIPLICADOR", 1.5)
ATR_TAKE_PROFIT_MULTIPLICADOR = _float("ATR_TAKE_PROFIT_MULTIPLICADOR", 3.0)
TRAILING_STOP_PCT = _float("TRAILING_STOP_PCT", 0.015)
MAX_POSICIONES_ABIERTAS = _int("MAX_POSICIONES_ABIERTAS", 3)

EMA_RAPIDA = _int("EMA_RAPIDA", 9)
EMA_LENTA = _int("EMA_LENTA", 21)
EMA_TENDENCIA = _int("EMA_TENDENCIA", 200)
RSI_PERIODO = _int("RSI_PERIODO", 14)
RSI_SOBRECOMPRA = _int("RSI_SOBRECOMPRA", 70)
RSI_SOBREVENTA = _int("RSI_SOBREVENTA", 30)
ATR_PERIODO = _int("ATR_PERIODO", 14)
ATR_MIN_PCT = _float("ATR_MIN_PCT", 0.003)
VOLUMEN_SMA_PERIODO = _int("VOLUMEN_SMA_PERIODO", 20)
VOLUMEN_MIN_MULTIPLICADOR = _float("VOLUMEN_MIN_MULTIPLICADOR", 1.0)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def validar():
    faltantes = []
    if not API_KEY:
        faltantes.append("ALPACA_API_KEY")
    if not API_SECRET:
        faltantes.append("ALPACA_API_SECRET")
    if faltantes:
        raise RuntimeError(
            f"Faltan variables de entorno: {', '.join(faltantes)}. "
            f"Configuralas en Railway (Settings -> Variables)."
        )
