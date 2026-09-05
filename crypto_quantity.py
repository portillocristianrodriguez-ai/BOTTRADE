"""Normalización segura de cantidades crypto para órdenes Alpaca."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_DOWN


DEFAULT_CRYPTO_INCREMENT = Decimal("0.000000001")
# Margen adicional para diferencias de representación/saldo entre el bot y
# Alpaca. Se expresa como mínimo en unidades del activo.
SAFETY_INCREMENTS = Decimal("1000")


def normalizar_cantidad_crypto(cantidad, incremento=None):
    """Devuelve una qty SELL crypto compatible y por debajo del saldo.

    Se redondea siempre hacia abajo usando ``min_trade_increment`` cuando está
    disponible. Después se reserva un pequeño margen adicional (mínimo 1000
    incrementos, equivalente a 0.000001 con el fallback de 1e-9) para cubrir
    diferencias de precisión entre la cantidad calculada por el bot y el
    saldo realmente liquidable en Alpaca.
    """
    try:
        qty = Decimal(str(cantidad))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")

    try:
        inc = Decimal(str(incremento)) if incremento is not None else DEFAULT_CRYPTO_INCREMENT
    except (InvalidOperation, ValueError, TypeError):
        inc = DEFAULT_CRYPTO_INCREMENT

    if qty <= 0 or inc <= 0:
        return Decimal("0")

    unidades = (qty / inc).to_integral_value(rounding=ROUND_DOWN)
    normalizada = unidades * inc

    # Nunca solicitar exactamente el último múltiplo: el saldo del broker
    # puede ser unas fracciones por debajo por representación/settlement.
    margen = inc * SAFETY_INCREMENTS
    if normalizada > margen:
        normalizada -= margen
    else:
        normalizada = Decimal("0")

    return normalizada.quantize(inc, rounding=ROUND_DOWN)
