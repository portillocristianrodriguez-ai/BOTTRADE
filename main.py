
"""
Punto de entrada del bot. Pensado para correr como worker en Railway:
un proceso de larga duración, sin puerto HTTP, que se reinicia solo
si Railway lo mata (por eso el manejo de errores no deja que un fallo
puntual tire abajo todo el proceso).

Corre dos loops independientes en paralelo (hilos), cada uno con su
propio intervalo:
- Acciones (config.TICKERS): cada CHECK_INTERVAL_MINUTES, solo si el
  mercado está abierto. Usan bracket orders (stop-loss/take-profit
  automáticos basados en ATR).
- Cripto (config.CRYPTO_TICKERS): cada CRYPTO_CHECK_INTERVAL_MINUTES,
  siempre (mercado 24/7). Sin bracket orders (Alpaca no las soporta en
  cripto), así que la salida se gestiona con:
    1) stop-loss manual basado en ATR (pérdida máxima admitida), y
    2) trailing stop manual (retrocede TRAILING_STOP_PCT desde el máximo
       alcanzado desde la compra).
  El trailing stop se guarda en memoria (_maximos_cripto) y se resetea
  si el proceso reinicia — es una limitación real a tener en cuenta.
"""

import time
import logging
import threading

import config
import broker
import estrategia
import notificaciones

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# Máximo (precio) alcanzado por cada posición cripto desde que se abrió,
# usado para el trailing stop manual. Vive solo en memoria del proceso.
_maximos_cripto = {}


def revisar_ticker(ticker: str):
    df = broker.obtener_datos(ticker)
    if df.empty:
        log.warning(f"{ticker}: sin datos, se omite.")
        return

    df = estrategia.calcular_indicadores(df)
    senal = estrategia.generar_senal(df)
    actual = df.iloc[-1]
    precio_actual = float(actual["close"])
    atr_actual = float(actual["atr"]) if not actual.isna().get("atr", True) else None
    posicion_abierta = broker.tiene_posicion_abierta(ticker)

    log.info(f"{ticker}: precio=${precio_actual:.2f} señal={senal} posición_abierta={posicion_abierta}")

    if posicion_abierta and broker.es_cripto(ticker):
        # 1) Stop-loss manual basado en ATR: pérdida no realizada máxima admitida.
        perdida_pct = broker.perdida_pct_no_realizada(ticker)
        if perdida_pct is not None and perdida_pct <= -config.STOP_LOSS_PCT:
            log.warning(f"{ticker}: stop-loss manual disparado ({perdida_pct:.2%}). Vendiendo.")
            mensaje = broker.vender(ticker)
            _maximos_cripto.pop(ticker, None)
            if mensaje:
                notificaciones.notificar(f"🛑 STOP-LOSS manual — {mensaje} (pérdida: {perdida_pct:.2%})")
            return

        # 2) Trailing stop manual: si el precio retrocede TRAILING_STOP_PCT
        # desde el máximo alcanzado, se cierra para proteger ganancias.
        info_posicion = broker.precio_actual_posicion(ticker)
        if info_posicion is not None:
            _, precio_posicion = info_posicion
            maximo_previo = _maximos_cripto.get(ticker, precio_posicion)
            nuevo_maximo = max(maximo_previo, precio_posicion)
            _maximos_cripto[ticker] = nuevo_maximo

            retroceso = (nuevo_maximo - precio_posicion) / nuevo_maximo if nuevo_maximo > 0 else 0
            if retroceso >= config.TRAILING_STOP_PCT:
                log.warning(f"{ticker}: trailing stop disparado (retroceso {retroceso:.2%} desde ${nuevo_maximo:.2f}). Vendiendo.")
                mensaje = broker.vender(ticker)
                _maximos_cripto.pop(ticker, None)
                if mensaje:
                    notificaciones.notificar(f"📉 TRAILING STOP — {mensaje} (retroceso: {retroceso:.2%})")
                return

    if senal == "COMPRAR" and not posicion_abierta:
        if atr_actual is None:
            log.warning(f"{ticker}: ATR no disponible, se omite compra.")
            return
        if broker.contar_posiciones_abiertas() >= config.MAX_POSICIONES_ABIERTAS:
            log.info("Máximo de posiciones abiertas alcanzado, se omite compra.")
            return
        mensaje = broker.comprar(ticker, precio_actual, atr_actual)
        if mensaje:
            notificaciones.notificar(mensaje)
            if broker.es_cripto(ticker):
                _maximos_cripto[ticker] = precio_actual

    elif senal == "VENDER" and posicion_abierta:
        mensaje = broker.vender(ticker)
        _maximos_cripto.pop(ticker, None)
        if mensaje:
            notificaciones.notificar(mensaje)


def loop_acciones():
    if not config.TICKERS:
        return
    while True:
        try:
            if broker.mercado_abierto():
                for ticker in config.TICKERS:
                    try:
                        revisar_ticker(ticker)
                    except Exception as e:
                        log.error(f"[acciones] Error procesando {ticker}: {e}")
            else:
                log.info("[acciones] Mercado cerrado, se omite este ciclo.")
        except Exception as e:
            log.error(f"[acciones] Error en el loop: {e}")
            notificaciones.notificar(f"⚠️ Error en el loop de acciones: {e}")
        time.sleep(60 * config.CHECK_INTERVAL_MINUTES)


def loop_cripto():
    if not config.CRYPTO_TICKERS:
        return
    while True:
        try:
            for ticker in config.CRYPTO_TICKERS:
                try:
                    revisar_ticker(ticker)
                except Exception as e:
                    log.error(f"[cripto] Error procesando {ticker}: {e}")
        except Exception as e:
            log.error(f"[cripto] Error en el loop: {e}")
            notificaciones.notificar(f"⚠️ Error en el loop de cripto: {e}")
        time.sleep(60 * config.CRYPTO_CHECK_INTERVAL_MINUTES)


def main():
    config.validar()

    log.info(f"Iniciando bot — modo {'PAPER (simulado)' if config.PAPER else 'REAL'}")
    log.info(
        f"Acciones: {config.TICKERS} (cada {config.CHECK_INTERVAL_MINUTES} min) | "
        f"Cripto: {config.CRYPTO_TICKERS} (cada {config.CRYPTO_CHECK_INTERVAL_MINUTES} min)"
    )
    notificaciones.notificar(
        f"🤖 Bot iniciado ({'paper' if config.PAPER else 'REAL'}) — "
        f"acciones: {', '.join(config.TICKERS) or '(ninguna)'} — "
        f"cripto: {', '.join(config.CRYPTO_TICKERS) or '(ninguna)'}"
    )

    hilos = []
    if config.TICKERS:
        hilos.append(threading.Thread(target=loop_acciones, daemon=True))
    if config.CRYPTO_TICKERS:
        hilos.append(threading.Thread(target=loop_cripto, daemon=True))

    if not hilos:
        log.error("No hay TICKERS ni CRYPTO_TICKERS configurados. Nada que hacer.")
        return

    for hilo in hilos:
        hilo.start()

    # El hilo principal se queda vivo mientras los loops corren en segundo plano.
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
