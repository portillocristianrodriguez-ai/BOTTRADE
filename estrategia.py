
import pandas as pd
import ta
import config


def calcular_indicadores(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ema_rapida"] = ta.trend.ema_indicator(df["close"], window=config.EMA_RAPIDA)
    df["ema_lenta"] = ta.trend.ema_indicator(df["close"], window=config.EMA_LENTA)
    df["ema_tendencia"] = ta.trend.ema_indicator(df["close"], window=config.EMA_TENDENCIA)
    df["rsi"] = ta.momentum.rsi(df["close"], window=config.RSI_PERIODO)
    macd = ta.trend.MACD(df["close"])
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["atr"] = ta.volatility.average_true_range(
        df["high"], df["low"], df["close"], window=config.ATR_PERIODO
    )
    if "volume" in df.columns:
        df["volumen_media"] = df["volume"].rolling(window=config.VOLUMEN_SMA_PERIODO).mean()
    return df


def _filtros_ok(actual: pd.Series) -> bool:
    if pd.isna(actual.get("atr")) or actual["close"] <= 0:
        return False
    atr_pct = actual["atr"] / actual["close"]
    if atr_pct < config.ATR_MIN_PCT:
        return False
    if "volumen_media" in actual and not pd.isna(actual.get("volumen_media")):
        if actual["volume"] < actual["volumen_media"] * config.VOLUMEN_MIN_MULTIPLICADOR:
            return False
    return True


def generar_senal(df: pd.DataFrame) -> str:
    minimo_velas = max(config.EMA_TENDENCIA, config.EMA_LENTA, config.RSI_PERIODO) + 2
    if len(df) < minimo_velas:
        return "ESPERAR"

    actual = df.iloc[-1]
    anterior = df.iloc[-2]

    if pd.isna(actual.get("ema_tendencia")):
        return "ESPERAR"

    tendencia_alcista = actual["close"] > actual["ema_tendencia"]

    cruce_alcista = (
        anterior["ema_rapida"] <= anterior["ema_lenta"]
        and actual["ema_rapida"] > actual["ema_lenta"]
    )
    cruce_bajista = (
        anterior["ema_rapida"] >= anterior["ema_lenta"]
        and actual["ema_rapida"] < actual["ema_lenta"]
    )
    macd_positivo = actual["macd"] > actual["macd_signal"]

    if cruce_bajista or actual["rsi"] > config.RSI_SOBRECOMPRA:
        return "VENDER"

    if not _filtros_ok(actual) or not tendencia_alcista:
        return "ESPERAR"

    if cruce_alcista and actual["rsi"] < config.RSI_SOBRECOMPRA and macd_positivo:
        return "COMPRAR"
    if actual["rsi"] < config.RSI_SOBREVENTA and macd_positivo:
        return "COMPRAR"

    return "ESPERAR"
PYEOF
echo "estrategia.py creado correctamente"
python3 diagnostico_senales.py
