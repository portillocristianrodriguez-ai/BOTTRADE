"""Consulta y gestiona las posiciones abiertas en Alpaca."""
print( TEST ALPACA FUNCIONANDO)
import logging

from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass
from alpaca.trading.requests import MarketOrderRequest, StopLossRequest, TakeProfitRequest

import config
import broker

log = logging.getLogger(__name__)


def obtener_posiciones():
    """Devuelve todas las posiciones abiertas."""
    return broker.trading_client.get_all_positions()


def obtener_ordenes_abiertas(ticker: str):
    """Devuelve las órdenes abiertas de un ticker."""
    return broker.trading_client.get_orders(
        status="open",
        symbols=[ticker],
    )


def comprobar_proteccion(ticker: str) -> tuple[bool, bool]:
    """
    Comprueba si una posición tiene Stop Loss y Take Profit
    entre sus órdenes abiertas.
    """
    ordenes = obtener_ordenes_abiertas(ticker)

    tiene_stop = False
    tiene_take_profit = False

    for orden in ordenes:
        tipo = str(orden.order_type).lower()

        if "stop" in tipo:
            tiene_stop = True

        if "limit" in tipo:
            tiene_take_profit = True

    return tiene_stop, tiene_take_profit


def mostrar_posiciones():
    """Muestra las posiciones actuales de forma clara."""

    posiciones = obtener_posiciones()

    print("\n📊 POSICIONES ACTUALES")
    print("=" * 35)

    if not posiciones:
        print("No hay posiciones abiertas.")
        return

    for posicion in posiciones:
        ticker = posicion.symbol
        cantidad = float(posicion.qty)
        entrada = float(posicion.avg_entry_price)
        actual = float(posicion.current_price)

        tiene_stop, tiene_tp = comprobar_proteccion(ticker)

        print(f"\n{ticker}")
        print(f"Cantidad: {cantidad:g}")
        print(f"Entrada: ${entrada:.2f}")
        print(f"Actual: ${actual:.2f}")
        print(f"Stop Loss: {'✅' if tiene_stop else '❌'}")
        print(f"Take Profit: {'✅' if tiene_tp else '❌'}")


def proteger_posicion(ticker: str) -> bool:
    """
    Si una posición no tiene protección, crea una orden bracket
    de protección para la cantidad existente.

    Se utiliza como mecanismo de seguridad para posiciones que
    hayan quedado abiertas sin SL/TP.
    """

    try:
        posicion = broker.trading_client.get_open_position(ticker)
    except Exception:
        return False

    cantidad = float(posicion.qty)
    entrada = float(posicion.avg_entry_price)

    if cantidad <= 0:
        return False

    tiene_stop, tiene_tp = comprobar_proteccion(ticker)

    if tiene_stop and tiene_tp:
        return True

    # Si falta alguna protección, cancelamos órdenes abiertas
    # de ese ticker antes de crear la protección correcta.
    ordenes = obtener_ordenes_abiertas(ticker)

    for orden in ordenes:
        try:
            broker.trading_client.cancel_order_by_id(orden.id)
        except Exception as e:
            log.warning(f"{ticker}: no se pudo cancelar orden {orden.id}: {e}")

    stop_loss = round(entrada * (1 - config.STOP_LOSS_PCT), 2)
    take_profit = round(entrada * (1 + config.TAKE_PROFIT_PCT), 2)

    orden = MarketOrderRequest(
        symbol=ticker,
        qty=cantidad,
        side=OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
        order_class=OrderClass.BRACKET,
        stop_loss=StopLossRequest(stop_price=stop_loss),
        take_profit=TakeProfitRequest(limit_price=take_profit),
    )

    try:
        broker.trading_client.submit_order(orden)

        log.info(
            f"{ticker}: protección creada "
            f"(SL ${stop_loss} / TP ${take_profit})."
        )
        return True

    except Exception as e:
        log.error(f"{ticker}: error creando protección: {e}")
        return False


def revisar_posiciones():
    """
    Revisa todas las posiciones y garantiza que tengan
    Stop Loss y Take Profit.
    """

    posiciones = obtener_posiciones()

    if not posiciones:
        return

    for posicion in posiciones:
        ticker = posicion.symbol

        try:
            tiene_stop, tiene_tp = comprobar_proteccion(ticker)

            log.info(
                f"{ticker}: "
                f"SL={'✅' if tiene_stop else '❌'} "
                f"TP={'✅' if tiene_tp else '❌'}"
            )

            if not tiene_stop or not tiene_tp:
                proteger_posicion(ticker)

        except Exception as e:
            log.error(f"{ticker}: error revisando protección: {e}")
