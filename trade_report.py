"""Informe read-only de rendimiento de BOTTRADE.

Este módulo NO forma parte del camino de ejecución de órdenes.
Se importa y ejecuta explícitamente cuando se desea auditar el historial.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import broker
from trade_analysis import analyze_orders


DEFAULT_OUTPUT = Path("trade_report.json")


def build_report() -> dict[str, Any]:
    """Consulta órdenes cerradas y genera un informe sin modificar Alpaca."""
    orders = broker.obtener_ordenes_ejecutadas()
    report = analyze_orders(orders)
    report["source"] = "Alpaca closed orders"
    report["orders_read"] = len(orders)
    return report


def save_report(path: str | Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    """Genera y guarda el informe localmente; no toca la operativa del bot."""
    report = build_report()
    destination = Path(path)
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return report


if __name__ == "__main__":
    report = save_report()
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2, default=str))
