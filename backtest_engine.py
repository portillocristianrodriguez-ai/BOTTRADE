"""Backtest determinista de BOTTRADE.

Usa las señales públicas de estrategia.py y nunca toca Alpaca ni envía órdenes.
Entrada: al open de la vela siguiente a la señal. Stops/TP se evalúan intrabar;
si ambos se tocan en la misma vela, se aplica primero el stop (supuesto conservador).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Callable

import numpy as np
import pandas as pd

import config
import estrategia


@dataclass
class Trade:
    entry_time: object
    exit_time: object
    entry: float
    exit: float
    qty: float
    pnl: float
    return_pct: float
    reason: str


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    required = ["open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas OHLCV: {missing}")
    out = df.copy()
    for c in required:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=required).sort_index()
    if not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.to_datetime(out.index, utc=True)
    return out


def _max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    dd = equity / peak - 1.0
    return float(dd.min()) if len(dd) else 0.0


def _sharpe(returns: pd.Series, periods: float) -> float:
    r = returns.dropna()
    if len(r) < 2 or float(r.std(ddof=1)) == 0:
        return 0.0
    return float(r.mean() / r.std(ddof=1) * math.sqrt(periods))


def resumen(trades: list[Trade], equity: pd.Series, initial_cash: float) -> dict:
    pnl = np.array([t.pnl for t in trades], dtype=float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    gross_profit = float(wins.sum()) if len(wins) else 0.0
    gross_loss = float(-losses.sum()) if len(losses) else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss else (float("inf") if gross_profit else 0.0)
    total_return = float(equity.iloc[-1] / initial_cash - 1.0) if len(equity) else 0.0
    return {
        "initial_cash": float(initial_cash),
        "final_equity": float(equity.iloc[-1]) if len(equity) else float(initial_cash),
        "total_return_pct": total_return * 100.0,
        "max_drawdown_pct": _max_drawdown(equity) * 100.0,
        "trades": len(trades),
        "wins": int(len(wins)),
        "losses": int(len(losses)),
        "win_rate_pct": float(len(wins) / len(trades) * 100.0) if trades else 0.0,
        "profit_factor": profit_factor,
        "expectancy_per_trade": float(pnl.mean()) if len(pnl) else 0.0,
        "best_trade_pct": float(max((t.return_pct for t in trades), default=0.0)),
        "worst_trade_pct": float(min((t.return_pct for t in trades), default=0.0)),
        "sharpe_annualized": _sharpe(equity.pct_change(), 252.0),
    }


def run(
    df: pd.DataFrame,
    initial_cash: float = 100_000.0,
    risk_per_trade_pct: float | None = None,
    stop_loss_pct: float | None = None,
    take_profit_pct: float | None = None,
    trailing_stop_pct: float | None = None,
    fee_bps: float = 0.0,
    slippage_bps: float = 0.0,
    signal_fn: Callable[[pd.DataFrame], str] | None = None,
) -> tuple[dict, pd.DataFrame, list[Trade]]:
    """Ejecuta una simulación sin look-ahead.

    La señal se calcula con todo el histórico disponible hasta la vela actual y
    la entrada se hace en el open siguiente. El tamaño usa riesgo fijo sobre
    stop, limitado por caja disponible.
    """
    data = _clean(df)
    if len(data) < int(config.EMA_TENDENCIA) + 5:
        raise ValueError("No hay suficientes barras para la EMA de tendencia.")
    risk = float(config.RISK_PER_TRADE_PCT if risk_per_trade_pct is None else risk_per_trade_pct)
    sl = float(config.STOP_LOSS_PCT if stop_loss_pct is None else stop_loss_pct)
    tp = float(config.TAKE_PROFIT_PCT if take_profit_pct is None else take_profit_pct)
    trail = float(config.TRAILING_STOP_PCT if trailing_stop_pct is None else trailing_stop_pct)
    if not (0 < risk <= 1 and 0 < sl < 1 and 0 < tp < 10 and 0 <= fee_bps < 1000 and 0 <= slippage_bps < 1000):
        raise ValueError("Parámetros de backtest inválidos.")

    signal_fn = signal_fn or estrategia.generar_senal
    cash = float(initial_cash)
    position = None
    trades: list[Trade] = []
    equity_rows = []

    for i in range(len(data)):
        row = data.iloc[i]
        price = float(row["close"])
        mark = cash + (position["qty"] * price if position else 0.0)

        if position is not None:
            entry = position["entry"]
            stop = position["stop"]
            target = position["target"]
            if price > position["peak"]:
                position["peak"] = price
                position["trail"] = max(position["trail"], price * (1.0 - trail))
            stop = max(stop, position["trail"])
            reason = None
            exit_price = None
            # Conservador: si stop y TP aparecen en la misma vela, gana el stop.
            if float(row["low"]) <= stop:
                reason, exit_price = "stop", stop
            elif float(row["high"]) >= target:
                reason, exit_price = "take_profit", target
            else:
                window = data.iloc[: i + 1]
                try:
                    sig = signal_fn(window)
                except Exception:
                    sig = "ESPERAR"
                if sig == "VENDER":
                    reason, exit_price = "signal", price
            if reason is not None:
                exit_price *= 1.0 - slippage_bps / 10000.0
                gross = position["qty"] * (exit_price - entry)
                fees = (position["qty"] * entry + position["qty"] * exit_price) * fee_bps / 10000.0
                pnl = gross - fees
                trades.append(Trade(position["entry_time"], data.index[i], entry, exit_price, position["qty"], pnl, (exit_price / entry - 1.0) * 100.0, reason))
                cash += position["qty"] * exit_price - fees
                position = None
                mark = cash

        # Señal al cierre -> entrada en la siguiente vela.
        if position is None and i < len(data) - 1:
            try:
                sig = signal_fn(data.iloc[: i + 1])
            except Exception:
                sig = "ESPERAR"
            if sig == "COMPRAR":
                next_open = float(data.iloc[i + 1]["open"]) * (1.0 + slippage_bps / 10000.0)
                stop_distance = next_open * sl
                risk_cash = cash * risk
                qty = min(risk_cash / stop_distance, cash / next_open) if stop_distance > 0 else 0.0
                if qty > 0:
                    fees = qty * next_open * fee_bps / 10000.0
                    total = qty * next_open + fees
                    if total <= cash:
                        cash -= total
                        position = {"entry_time": data.index[i + 1], "entry": next_open, "qty": qty, "stop": next_open * (1.0 - sl), "target": next_open * (1.0 + tp), "trail": next_open * (1.0 - trail), "peak": next_open}

        mark = cash + (position["qty"] * price if position else 0.0)
        equity_rows.append((data.index[i], mark))

    if position is not None:
        last = float(data.iloc[-1]["close"]) * (1.0 - slippage_bps / 10000.0)
        fees = (position["qty"] * position["entry"] + position["qty"] * last) * fee_bps / 10000.0
        pnl = position["qty"] * (last - position["entry"]) - fees
        trades.append(Trade(position["entry_time"], data.index[-1], position["entry"], last, position["qty"], pnl, (last / position["entry"] - 1.0) * 100.0, "end_of_data"))
        cash += position["qty"] * last - fees
        equity_rows[-1] = (data.index[-1], cash)

    equity = pd.Series(dict(equity_rows), dtype=float).sort_index()
    stats = resumen(trades, equity, initial_cash)
    return stats, equity.rename("equity").to_frame(), trades


def trades_to_frame(trades: list[Trade]) -> pd.DataFrame:
    return pd.DataFrame([asdict(t) for t in trades])


__all__ = ["Trade", "run", "resumen", "trades_to_frame"]
