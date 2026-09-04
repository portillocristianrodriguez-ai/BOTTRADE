import pandas as pd
import ta
import config


def calcular_indicadores(df):
    df = df.copy()
    columnas_numericas = ["open", "high", "low", "close", "volume"]
    for columna in columnas_numericas:
        if columna in df.columns:
            df[columna] = pd.to_numeric(df[columna], errors="coerce")
    df = df.dropna(subset=columnas_numericas).sort_index()
    df["ema_tendencia"] = ta.trend.ema_indicator(df["close"], window=config.EMA_TENDENCIA)
    df["atr"] = ta.volatility.average_true_range(df["high"], df["low"], df["close"], window=config.ATR_PERIODO)
    df["ema_rapida"] = ta.trend.ema_indicator(df["close"], window=config.EMA_RAPIDA)
    df["ema_lenta"] = ta.trend.ema_indicator(df["close"], window=config.EMA_LENTA)
    df["rsi"] = ta.momentum.rsi(df["close"], window=config.RSI_PERIODO)
    macd = ta.trend.MACD(df["close"], window_fast=12, window_slow=26, window_sign=9)
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"] = df["macd"] - df["macd_signal"]
    periodo_volumen = max(5, int(config.VOLUMEN_SMA_PERIODO))
    df["volumen_media"] = df["volume"].shift(1).rolling(periodo_volumen, min_periods=5).mean()
    df["volumen_ratio"] = pd.to_numeric(df["volume"] / df["volumen_media"].replace(0, pd.NA), errors="coerce")
    df["volumen_valido"] = df["volume"] > 0
    return df


def _datos_validos(actual, columnas):
    return all(not pd.isna(actual.get(columna)) for columna in columnas)


def _obtener_indice_barra_crypto(df):
    try:
        if df is None or df.empty or "volume" not in df.columns:
            return None
        volumen = pd.to_numeric(df["volume"], errors="coerce")
        indices_validos = volumen[volumen > 0].index
        if len(indices_validos) == 0:
            return None
        ultimo = indices_validos[-1]
        posiciones = df.index.get_indexer([ultimo])
        return int(posiciones[0]) if len(posiciones) and posiciones[0] >= 0 else None
    except Exception:
        return None


def _generar_senal_acciones(df):
    if len(df) < config.EMA_TENDENCIA + 2:
        return "ESPERAR"
    actual, anterior = df.iloc[-1], df.iloc[-2]
    columnas = ["ema_tendencia", "ema_rapida", "ema_lenta", "rsi", "macd", "macd_signal", "atr", "volumen_ratio"]
    if not _datos_validos(actual, columnas) or not _datos_validos(anterior, ["ema_tendencia", "ema_rapida", "ema_lenta", "rsi", "macd", "macd_signal"]):
        return "ESPERAR"
    tendencia_alcista = actual["close"] > actual["ema_tendencia"]
    tendencia_bajista = actual["close"] < actual["ema_tendencia"]
    emas_alcistas = actual["ema_rapida"] > actual["ema_lenta"]
    emas_bajistas = actual["ema_rapida"] < actual["ema_lenta"]
    cruce_alcista = anterior["ema_rapida"] <= anterior["ema_lenta"] and actual["ema_rapida"] > actual["ema_lenta"]
    cruce_bajista = anterior["ema_rapida"] >= anterior["ema_lenta"] and actual["ema_rapida"] < actual["ema_lenta"]
    macd_alcista = actual["macd"] > actual["macd_signal"]
    macd_bajista = actual["macd"] < actual["macd_signal"]
    rsi = float(actual["rsi"])
    rsi_ok = config.RSI_SOBREVENTA <= rsi <= config.RSI_SOBRECOMPRA
    volumen_ok = actual["volumen_ratio"] >= config.VOLUMEN_MIN_MULTIPLICADOR
    atr_pct = actual["atr"] / actual["close"]
    volatilidad_ok = atr_pct >= config.ATR_MIN_PCT
    if (tendencia_alcista and emas_alcistas and macd_alcista and rsi_ok and volumen_ok and volatilidad_ok) or (cruce_alcista and tendencia_alcista and macd_alcista and rsi <= 70 and volumen_ok and volatilidad_ok):
        return "COMPRAR"
    if (actual["close"] < actual["ema_tendencia"] * (1 - config.MARGEN_SALIDA_PCT) and macd_bajista) or (cruce_bajista and macd_bajista) or (tendencia_bajista and emas_bajistas and macd_bajista and rsi < 45):
        return "VENDER"
    return "ESPERAR"


def _resultado_vacio():
    return {"score": 0.0, "comprar": False, "motivo": [], "rsi": 0.0, "volumen_ratio": 0.0, "momentum_pct": 0.0, "atr_pct": 0.0, "breakout": False}


def _analizar_impulso(df, ticker, es_crypto=False):
    resultado = _resultado_vacio()
    try:
        if df is None or df.empty:
            return resultado
        datos = calcular_indicadores(df)
        lookback = max(2, int(config.CRYPTO_BREAKOUT_LOOKBACK))
        momentum_bars = max(1, int(config.CRYPTO_MOMENTUM_BARS))
        minimo = max(50, config.EMA_TENDENCIA + 5, lookback + momentum_bars + 2)
        if len(datos) < minimo:
            return resultado
        i = _obtener_indice_barra_crypto(datos) if es_crypto else len(datos) - 1
        if i is None or i < max(lookback, momentum_bars, 3):
            return resultado
        actual = datos.iloc[i]
        anterior = datos.iloc[i - 1]
        cols = ["close", "high", "ema_tendencia", "ema_rapida", "ema_lenta", "rsi", "macd_hist", "atr", "volumen_ratio"]
        if not _datos_validos(actual, cols):
            return resultado
        precio = float(actual["close"])
        previo = float(datos.iloc[i - momentum_bars]["close"])
        if precio <= 0 or previo <= 0:
            return resultado
        rsi = float(actual["rsi"])
        vol = float(actual["volumen_ratio"])
        atr_pct = float(actual["atr"] / precio * 100)
        momentum = float((precio - previo) / previo * 100)
        max_previo = float(datos.iloc[i - lookback:i]["high"].max())
        breakout = precio > max_previo
        ema_t = float(actual["ema_tendencia"])
        ema_f = float(actual["ema_rapida"])
        ema_l = float(actual["ema_lenta"])
        hist = float(actual["macd_hist"])
        hist_prev = float(anterior["macd_hist"]) if not pd.isna(anterior["macd_hist"]) else hist
        sobre_tendencia = precio > ema_t
        emas = ema_f > ema_l
        slope_ref = float(datos.iloc[i - 3]["ema_rapida"])
        slope = ((ema_f - slope_ref) / slope_ref * 100) if slope_ref > 0 else 0.0
        slope_ok = slope > 0
        vol_min = float(config.CRYPTO_VOLUME_MIN_MULTIPLIER) if es_crypto else float(config.VOLUMEN_MIN_MULTIPLICADOR)
        vol_ok = vol >= vol_min
        rsi_min = float(config.CRYPTO_RSI_MIN) if es_crypto else 50.0
        rsi_max = float(config.CRYPTO_RSI_MAX) if es_crypto else 68.0
        rsi_ok = rsi_min <= rsi <= rsi_max
        mom_min = float(config.CRYPTO_MIN_MOMENTUM_PCT) if es_crypto else float(config.CRYPTO_MIN_MOMENTUM_PCT)
        mom_ok = momentum >= mom_min
        atr_ok = atr_pct >= float(config.ATR_MIN_PCT) * 100
        no_ext = momentum <= float(config.CRYPTO_MAX_RISE_PCT)
        macd_ok = hist > 0
        macd_crec = hist >= hist_prev
        score = 0.0
        motivos = []
        checks = [(sobre_tendencia, 15, "precio > EMA tendencia"), (emas, 15, "EMA rápida > EMA lenta"), (breakout, 20, "breakout"), (vol_ok, 15, "volumen fuerte"), (rsi_ok, 10, "RSI saludable"), (macd_ok, 5, "MACD positivo"), (macd_crec, 5, "MACD creciente"), (mom_ok, 10, "momentum suficiente"), (atr_ok, 5, "volatilidad suficiente")]
        for ok, puntos, motivo in checks:
            if ok:
                score += puntos
                motivos.append(motivo)
        if not sobre_tendencia: motivos.append("debajo EMA tendencia")
        if not emas: motivos.append("EMA no alineadas")
        if not breakout: motivos.append("sin breakout")
        if not vol_ok: motivos.append("volumen insuficiente")
        if not rsi_ok: motivos.append("RSI fuera de zona")
        if not mom_ok: motivos.append("momentum insuficiente")
        if not atr_ok: motivos.append("ATR insuficiente")
        if not no_ext: motivos.append("movimiento demasiado extendido")
        if not macd_ok: motivos.append("MACD negativo")
        comprar = score >= float(config.CRYPTO_MIN_SCORE) and sobre_tendencia and emas and slope_ok and vol_ok and rsi_ok and mom_ok and atr_ok and no_ext and macd_ok
        return {"score": float(min(score, 100.0)), "comprar": bool(comprar), "motivo": motivos, "rsi": rsi, "volumen_ratio": vol, "momentum_pct": momentum, "atr_pct": atr_pct, "breakout": bool(breakout)}
    except Exception as e:
        print(f"[{ 'crypto' if es_crypto else 'acciones' } scanner] {ticker}: error analizando impulso: {e}")
        return resultado


def analizar_impulso_acciones(df, ticker):
    return _analizar_impulso(df, ticker, es_crypto=False)


def analizar_impulso_crypto(df, ticker):
    return _analizar_impulso(df, ticker, es_crypto=True)


def _generar_senal_cripto(df):
    if len(df) < 50:
        return "ESPERAR"
    datos = calcular_indicadores(df)
    i = _obtener_indice_barra_crypto(datos)
    if i is None or i < 2:
        return "ESPERAR"
    actual, anterior = datos.iloc[i], datos.iloc[i - 1]
    columnas = ["ema_tendencia", "ema_rapida", "ema_lenta", "rsi", "macd", "macd_signal", "atr", "volumen_ratio"]
    if not _datos_validos(actual, columnas):
        return "ESPERAR"
    tendencia = actual["close"] > actual["ema_tendencia"]
    emas = actual["ema_rapida"] > actual["ema_lenta"]
    macd = actual["macd"] > actual["macd_signal"]
    rsi = 45 <= float(actual["rsi"]) <= 68
    volumen = actual["volumen_ratio"] >= config.VOLUMEN_MIN_MULTIPLICADOR
    atr = actual["atr"] / actual["close"] >= config.ATR_MIN_PCT
    cruce = anterior["ema_rapida"] <= anterior["ema_lenta"] and actual["ema_rapida"] > actual["ema_lenta"]
    if (tendencia and emas and macd and rsi and volumen and atr) or (cruce and tendencia and macd and float(actual["rsi"]) <= 70 and volumen and atr):
        return "COMPRAR"
    if (actual["close"] < actual["ema_tendencia"] and actual["macd"] < actual["macd_signal"] and float(actual["rsi"]) < 45):
        return "VENDER"
    return "ESPERAR"


def generar_senal(df, ticker):
    try:
        return _generar_senal_cripto(df) if "/" in str(ticker) else _generar_senal_acciones(df)
    except Exception as e:
        print(f"{ticker}: error generando señal: {e}")
        return "ESPERAR"
