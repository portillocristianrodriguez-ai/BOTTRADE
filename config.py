"""
Configuración del bot. Todo se lee de variables de entorno para poder
deployar en Railway sin exponer claves en el código.

Variables requeridas en Railway (Settings -> Variables):
  ALPACA_API_KEY
  ALPACA_API_SECRET
  ALPACA_PAPER            (true/false, default: true)
  TICKERS                 (ej: "AAPL,MSFT,NVDA,TSLA,AMZN")
  CHECK_INTERVAL_MINUTES  (default: 5)
  RISK_PER_TRADE_PCT      (default: 0.02)
  STOP_LOSS_PCT           (default: 0.02)
  TAKE_PROFIT_PCT         (default: 0.04)
  MAX_POSICIONES_ABIERTAS (default: 3)
  TELEGRAM_BOT_TOKEN      (opcional, para notificaciones)
  TELEGRAM_CHAT_ID        (opcional, para notificaciones)
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

CHECK_INTERVAL_MINUTES = _int("CHECK_INTERVAL_MINUTES", 5)
RISK_PER_TRADE_PCT = _float("RISK_PER_TRADE_PCT", 0.02)
STOP_LOSS_PCT = _float("STOP_LOSS_PCT", 0.02)
TAKE_PROFIT_PCT = _float("TAKE_PROFIT_PCT", 0.04)
MAX_POSICIONES_ABIERTAS = _int("MAX_POSICIONES_ABIERTAS", 3)

EMA_RAPIDA = _int("EMA_RAPIDA", 9)
EMA_LENTA = _int("EMA_LENTA", 21)
RSI_PERIODO = _int("RSI_PERIODO", 14)
RSI_SOBRECOMPRA = _int("RSI_SOBRECOMPRA", 70)
RSI_SOBREVENTA = _int("RSI_SOBREVENTA", 30)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def validar():
    """Falla rápido y claro si falta algo esencial, en vez de crashear a mitad de operación."""
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
