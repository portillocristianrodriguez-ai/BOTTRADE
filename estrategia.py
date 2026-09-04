import pandas as pd
import ta
import config


def calcular_indicadores(df):
    df = df.copy()
    columnas_numericas = ["open", "high", "low", "close", "volume"]
    for columna in columnas_numericas:
        if columna not in df.columns:
            return pd.DataFrame()
        df[columna] = pd.to_numeric(df[columna], errors="coerce")
    df = df.dropna(subset=columnas_numericas).sort_index()
    if df.empty:
        return df

    df["ema_tendencia"] = ta.trend.ema_indicator(df["close"], window=config.EMA_TENDENCIA)
    df["atr"] = ta.volatility.average_true_range(
        df["high"], df["low"], df["close"], window=config.ATR_PERIODO
    )
    df["ema_rapida"] = ta.trend.ema_indicator(df["close"], window=config.EMA_RAPIDA)
    df["ema_lenta"] = ta.trend.ema_indicator(df["close"], window=config.EMA_LENTA)
    df["rsi"] = ta.momentum.rsi(df["close"], window=config.RSI_PERIODO)

    macd = ta.trend.MACD(df["close"], window_fast=12, window_slow=26, window_sign=9)
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"] = macd.macd_diff()

    periodo_volumen = max(5, int(config.VOLUMEN_SMA_PERIODO))
    df["volumen_media"] = df["volume"].shift(1).rolling(periodo_volumen, min_periods=5).mean()
    df["volumen_ratio"] = pd.to_numeric(
        df["volume"] / df["volumen_media"].replace(0, pd.NA), errors="coerce"
    )
    df["volumen_media_corta"] = df["volume"].shift(1).rolling(3, min_periods=3).mean()
    df["aceleracion_volumen"] = pd.to_numeric(
        df["volume"] / df["volumen_media_corta"].replace(0, pd.NA), errors="coerce"
    )
    df["adx"] = ta.trend.adx(df["high"], df["low"], df["close"], window=14)
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
    datos = calcular_indicadores(df)
    if datos.empty or len(datos) < config.EMA_TENDENCIA + 2:
        return "ESPERAR"

    actual, anterior = datos.iloc[-1], datos.iloc[-2]
    columnas = [
        "ema_tendencia", "ema_rapida", "ema_lenta", "rsi",
        "macd", "macd_signal", "atr", "volumen_ratio"
    ]
    if not _datos_validos(actual, columnas) or not _datos_validos(
        anterior, ["ema_tendencia", "ema_rapida", "ema_lenta", "rsi", "macd", "macd_signal"]
    ):
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
    volumen_ok = float(actual["volumen_ratio"]) >= config.VOLUMEN_MIN_MULTIPLICADOR
    atr_pct = float(actual["atr"] / actual["close"]) if float(actual["close"]) > 0 else 0.0
    volatilidad_ok = atr_pct >= config.ATR_MIN_PCT

    impulso = (float(actual["close"]) - float(datos.iloc[-4]["close"])) / float(datos.iloc[-4]["close"]) if len(datos) >= 4 and float(datos.iloc[-4]["close"]) > 0 else 0.0
    ruptura = float(actual["close"]) > float(datos.iloc[-13:-1]["high"].max()) if len(datos) >= 13 else False

    continuacion = (
        tendencia_alcista and emas_alcistas and macd_alcista
        and rsi_ok and volumen_ok and volatilidad_ok
        and impulso > 0
    )
    ruptura_impulso = (
        ruptura and tendencia_alcista and macd_alcista
        and 48 <= rsi <= 74 and volatilidad_ok
    )

    if continuacion or ruptura_impulso or (
        cruce_alcista and tendencia_alcista and macd_alcista
        and rsi <= 72 and volatilidad_ok
    ):
        return "COMPRAR"

    if (
        actual["close"] < actual["ema_tendencia"] * (1 - config.MARGEN_SALIDA_PCT)
        and macd_bajista
    ) or (
        cruce_bajista and macd_bajista
    ) or (
        tendencia_bajista and emas_bajistas and macd_bajista and rsi < 45
    ):
        return "VENDER"

    return "ESPERAR"


def _resultado_vacio():
    return {
        "score": 0.0,
        "comprar": False,
        "motivo": [],
        "rsi": 0.0,
        "volumen_ratio": 0.0,
        "momentum_pct": 0.0,
        "atr_pct": 0.0,
        "breakout": False,
        "regimen": "neutral",
        "adx": 0.0,
        "aceleracion_volumen": 0.0,
    }


def _analizar_impulso(df, ticker, es_crypto=False):
    resultado = _resultado_vacio()
    try:
        if df is None or df.empty:
            return resultado

        datos = calcular_indicadores(df)
        if datos.empty:
            return resultado

        lookback = max(4, int(getattr(config, "CRYPTO_BREAKOUT_LOOKBACK", 12)))
        momentum_bars = max(1, int(getattr(config, "CRYPTO_MOMENTUM_BARS", 3)))
        minimo = max(50, int(config.EMA_TENDENCIA) + 5, lookback + momentum_bars + 4)
        if len(datos) < minimo:
            return resultado

        i = _obtener_indice_barra_crypto(datos) if es_crypto else len(datos) - 1
        if i is None or i < max(lookback, momentum_bars, 4):
            return resultado

        actual = datos.iloc[i]
        anterior = datos.iloc[i - 1]
        cols = [
            "close", "high", "ema_tendencia", "ema_rapida", "ema_lenta",
            "rsi", "macd_hist", "atr", "volumen_ratio", "adx",
        ]
        if not _datos_validos(actual, cols):
            return resultado

        precio = float(actual["close"])
        previo = float(datos.iloc[i - momentum_bars]["close"])
        if precio <= 0 or previo <= 0:
            return resultado

        rsi = float(actual["rsi"])
        vol = float(actual["volumen_ratio"])
        aceleracion_vol = float(actual["aceleracion_volumen"]) if not pd.isna(actual["aceleracion_volumen"]) else 0.0
        adx = float(actual["adx"]) if not pd.isna(actual["adx"]) else 0.0
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

        if es_crypto:
            vol_min = float(getattr(config, "CRYPTO_VOLUME_MIN_MULTIPLICADOR", 1.25))
            rsi_min = float(getattr(config, "CRYPTO_RSI_MIN", 48))
            rsi_max = float(getattr(config, "CRYPTO_RSI_MAX", 72))
            mom_min = float(getattr(config, "CRYPTO_MIN_MOMENTUM_PCT", 0.20))
            score_min = float(getattr(config, "CRYPTO_SCORE_MINIMO", 70))
            max_rise = float(getattr(config, "CRYPTO_MAX_RISE_PCT", 10.0))
        else:
            vol_min = float(getattr(config, "VOLUMEN_MIN_MULTIPLICADOR", 1.0))
            rsi_min = 48.0
            rsi_max = 74.0
            mom_min = 0.10
            score_min = 65.0
            max_rise = 8.0

        vol_ok = vol >= vol_min
        rsi_ok = rsi_min <= rsi <= rsi_max
        mom_ok = momentum >= mom_min
        atr_ok = atr_pct >= float(config.ATR_MIN_PCT) * 100
        no_ext = momentum <= max_rise
        macd_ok = hist > 0
        macd_crec = hist >= hist_prev
        adx_ok = adx >= 18.0
        aceleracion_ok = aceleracion_vol >= 1.0

        if sobre_tendencia and emas and slope_ok:
            regimen = "alcista"
        elif sobre_tendencia or slope_ok:
            regimen = "transicion"
        else:
            regimen = "bajista"

        score = 0.0
        motivos = []
        checks = [
            (sobre_tendencia, 15, "precio > EMA tendencia"),
            (emas, 15, "EMA rápida > EMA lenta"),
            (slope_ok, 10, "pendiente positiva"),
            (breakout, 15, "breakout"),
            (vol_ok, 10, "volumen fuerte"),
            (rsi_ok, 10, "RSI saludable"),
            (macd_ok, 5, "MACD positivo"),
            (macd_crec, 5, "MACD creciente"),
            (mom_ok, 5, "momentum suficiente"),
            (atr_ok, 5, "volatilidad suficiente"),
        ]
        for ok, puntos, motivo in checks:
            if ok:
                score += puntos
                motivos.append(motivo)

        # ADX y aceleración no dominan el score: sirven para distinguir una
        # tendencia realmente negociable de una subida débil o sin participación.
        if adx_ok:
            score += 2.5
            motivos.append("ADX con tendencia")
        if aceleracion_ok:
            score += 2.5
            motivos.append("volumen acelerando")

        if not sobre_tendencia:
            motivos.append("debajo EMA tendencia")
        if not emas:
            motivos.append("EMA no alineadas")
        if not breakout:
            motivos.append("sin breakout")
        if not vol_ok:
            motivos.append("volumen insuficiente")
        if not rsi_ok:
            motivos.append("RSI fuera de zona")
        if not mom_ok:
            motivos.append("momentum insuficiente")
        if not atr_ok:
            motivos.append("ATR insuficiente")
        if not no_ext:
            motivos.append("movimiento demasiado extendido")
        if not macd_ok:
            motivos.append("MACD negativo")
        if not adx_ok:
            motivos.append("ADX débil")

        # Dos familias de entrada:
        # 1) continuación: exige estructura + participación;
        # 2) breakout: permite entrar con algo menos de pendiente/volumen si
        #    el propio rompimiento aporta la confirmación de flujo.
        continuacion = (
            sobre_tendencia and emas and slope_ok
            and macd_ok and rsi_ok and mom_ok and atr_ok
            and vol_ok and no_ext
        )
        breakout_fuerte = (
            breakout and sobre_tendencia and emas
            and macd_ok and rsi_ok and mom_ok and atr_ok
            and no_ext and (vol_ok or aceleracion_ok)
        )
        cruce_impulso = (
            sobre_tendencia and emas and macd_ok and rsi_ok
            and mom_ok and atr_ok and no_ext
            and macd_crec and (vol_ok or aceleracion_ok)
        )

        comprar = bool(
            score >= score_min
            and (continuacion or breakout_fuerte or cruce_impulso)
        )

        return {
            "score": float(min(score, 100.0)),
            "comprar": comprar,
            "motivo": motivos,
            "rsi": rsi,
            "volumen_ratio": vol,
            "momentum_pct": momentum,
            "atr_pct": atr_pct,
            "breakout": bool(breakout),
            "regimen": regimen,
            "adx": adx,
            "aceleracion_volumen": aceleracion_vol,
        }
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
    analisis = analizar_impulso_crypto(df, "CRYPTO")
    if analisis["comprar"]:
        return "COMPRAR"

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
    rsi = float(getattr(config, "CRYPTO_RSI_MIN", 48)) <= float(actual["rsi"]) <= float(getattr(config, "CRYPTO_RSI_MAX", 72))
    volumen = actual["volumen_ratio"] >= float(getattr(config, "CRYPTO_VOLUME_MIN_MULTIPLICADOR", 1.25))
    atr = actual["atr"] / actual["close"] >= config.ATR_MIN_PCT
    cruce = anterior["ema_rapida"] <= anterior["ema_lenta"] and actual["ema_rapida"] > actual["ema_lenta"]

    if (tendencia and emas and macd and rsi and volumen and atr) or (
        cruce and tendencia and macd and float(actual["rsi"]) <= 74 and volumen and atr
    ):
        return "COMPRAR"
    if actual["close"] < actual["ema_tendencia"] and actual["macd"] < actual["macd_signal"] and float(actual["rsi"]) < 45:
        return "VENDER"
    return "ESPERAR"


def generar_senal(df, ticker):
    try:
        return _generar_senal_cripto(df) if "/" in str(ticker) else _generar_senal_acciones(df)
    except Exception as e:
        print(f"{ticker}: error generando señal: {e}")
        return "ESPERAR"
