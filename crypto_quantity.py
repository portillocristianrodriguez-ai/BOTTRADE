"""Normalización segura de cantidades crypto para órdenes Alpaca."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_DOWN


DEFAULT_CRYPTO_INCREMENT = Decimal("0.000000001")


def normalizar_cantidad_crypto(cantidad, incremento=None):
    """Devuelve una qty compatible con el incremento de Alpaca.

    Se redondea siempre hacia abajo. Si la qty cae exactamente en un múltiplo
    del incremento, se descuenta una unidad mínima para evitar rechazos por
    pequeñas diferencias entre la posición local y el saldo disponible del
    broker (caso típico: 109379 solicitado vs 109378.999999823 disponible).
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

    if normalizada == qty and normalizada > inc:
        normalizada -= inc

    return normalizada.quantize(inc, rounding=ROUND_DOWN)
