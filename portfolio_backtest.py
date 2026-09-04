"""Backtest multi-activo determinista para validación de BOTTRADE.

Es un motor de investigación: no usa Alpaca ni envía órdenes. Comparte cash
entre símbolos, permite posiciones simultáneas y ejecuta las señales en el
open de la vela siguiente. Respeta los límites de posiciones/exposición del
config cuando están disponibles.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Callable, Mapping

import pandas as pd

import config


@dataclass
class PortfolioTrade:
    symbol: str
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
        raise ValueError(f"{missing=}")
    out = df.copy()
    for col in required:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=required).sort_index()
    if not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.to_datetime(out.index, utc=True)
    return out


def run_portfolio(
    data: Mapping[str, pd.DataFrame],
    initial_cash: float = 100_000.0,
    risk_per_trade_pct: float | None = None,
    stop_loss_pct: float | None = None,
    take_profit_pct: float | None = None,
    trailing_stop_pct: float | None = None,
    fee_bps: float = 0.0,
    slippage_bps: float = 0.0,
    signal_fn: Callable[[str, pd.DataFrame], str] | None = None,
    max_positions: int | None = None,
    max_total_exposure_pct: float | None = None,
    max_single_position_pct: float | None = None,
) -> tuple[dict, pd.DataFrame, list[PortfolioTrade]]:
    """Simula varios activos con una cuenta compartida y sin look-ahead."""
    frames = {str(symbol): _clean(frame) for symbol, frame in data.items() if frame is not None and not frame.empty}
    if not frames:
        raise ValueError("No hay series de mercado para el portfolio.")
    risk = float(config.RISK_PER_TRADE_PCT if risk_per_trade_pct is None else risk_per_trade_pct)
    sl = float(config.STOP_LOSS_PCT if stop_loss_pct is None else stop_loss_pct)
    tp = float(config.TAKE_PROFIT_PCT if take_profit_pct is None else take_profit_pct)
    trail = float(config.TRAILING_STOP_PCT if trailing_stop_pct is None else trailing_stop_pct)
    max_pos = int(getattr(config, "MAX_POSICIONES_ABIERTAS", 3) if max_positions is None else max_positions)
    max_expo = float(getattr(config, "MAX_TOTAL_EXPOSURE_PCT", 0.50) if max_total_exposure_pct is None else max_total_exposure_pct)
    max_single = float(getattr(config, "MAX_SINGLE_POSITION_PCT", 0.20) if max_single_position_pct is None else max_single_position_pct)
    if not (initial_cash > 0 and 0 < risk <= 1 and 0 < sl < 1 and 0 < tp < 10 and 0 <= fee_bps < 1000 and 0 <= slippage_bps < 1000):
        raise ValueError("Parámetros de portfolio backtest inválidos.")
    if not (1 <= max_pos and 0 < max_expo <= 1 and 0 < max_single <= 1):
        raise ValueError("Límites de portfolio inválidos.")

    symbols = sorted(frames)
    timeline = sorted(set().union(*(set(frame.index) for frame in frames.values())))
    positions: dict[str, dict] = {}
    pending: dict[str, dict] = {}
    cash = float(initial_cash)
    trades: list[PortfolioTrade] = []
    equity_rows = []

    def equity_at(timestamp):
        value = cash
        for symbol, pos in positions.items():
            frame = frames[symbol]
            available = frame.loc[:timestamp]
            if available.empty:
                value += pos["qty"] * pos["entry"]
            else:
                value += pos["qty"] * float(available.iloc[-1]["close"])
        return value

    def exposure_at(timestamp):
        exposure = 0.0
        for symbol, pos in positions.items():
            frame = frames[symbol]
            available = frame.loc[:timestamp]
            px = pos["entry"] if available.empty else float(available.iloc[-1]["close"])
            exposure += pos["qty"] * px
        return exposure

    for timestamp in timeline:
        # Ejecutar primero las órdenes pendientes cuyo open existe en esta fecha.
        for symbol in list(pending):
            order = pending[symbol]
            frame = frames[symbol]
            if timestamp != order["entry_time"] or timestamp not in frame.index:
                continue
            total = order["qty"] * order["entry"] + order["entry_fee"]
            current_exposure = exposure_at(timestamp)
            if len(positions) < max_pos and total <= cash and current_exposure + total <= initial_cash * max_expo:
                cash -= total
                positions[symbol] = order
            del pending[symbol]

        # Gestionar posiciones activas. Si stop y TP se tocan en la misma vela,
        # el stop gana para mantener un supuesto conservador.
        for symbol in list(positions):
            frame = frames[symbol]
            if timestamp not in frame.index:
                continue
            row = frame.loc[timestamp]
            pos = positions[symbol]
            close = float(row["close"])
            if close > pos["peak"]:
                pos["peak"] = close
                pos["trail"] = max(pos["trail"], close * (1.0 - trail))
            stop = max(pos["stop"], pos["trail"])
            reason = None
            exit_price = None
            if float(row["low"]) <= stop:
                reason, exit_price = "stop", stop
            elif float(row["high"]) >= pos["target"]:
                reason, exit_price = "take_profit", pos["target"]
            else:
                try:
                    hist = frame.loc[:timestamp]
                    sig = signal_fn(symbol, hist) if signal_fn else "ESPERAR"
                except Exception:
                    sig = "ESPERAR"
                if sig == "VENDER":
                    reason, exit_price = "signal", close
            if reason is not None:
                exit_price *= 1.0 - slippage_bps / 10000.0
                gross = pos["qty"] * (exit_price - pos["entry"])
                fees = (pos["qty"] * pos["entry"] + pos["qty"] * exit_price) * fee_bps / 10000.0
                pnl = gross - fees
                trades.append(PortfolioTrade(symbol, pos["entry_time"], timestamp, pos["entry"], exit_price, pos["qty"], pnl, (exit_price / pos["entry"] - 1.0) * 100.0, reason))
                cash += pos["qty"] * exit_price - fees
                del positions[symbol]

        # Programar nuevas entradas. Nunca se ejecutan en la misma vela de señal.
        for symbol in symbols:
            if symbol in positions or symbol in pending or timestamp not in frames[symbol].index:
                continue
            if len(positions) + len(pending) >= max_pos:
                break
            frame = frames[symbol]
            loc = frame.index.get_loc(timestamp)
            if isinstance(loc, slice) or isinstance(loc, list) or loc >= len(frame) - 1:
                continue
            try:
                hist = frame.iloc[: int(loc) + 1]
                sig = signal_fn(symbol, hist) if signal_fn else "ESPERAR"
            except Exception:
                sig = "ESPERAR"
            if sig != "COMPRAR":
                continue
            next_open = float(frame.iloc[int(loc) + 1]["open"]) * (1.0 + slippage_bps / 10000.0)
            if next_open <= 0:
                continue
            stop_distance = next_open * sl
            risk_cash = cash * risk
            qty_by_risk = risk_cash / stop_distance if stop_distance > 0 else 0.0
            qty_by_cash = cash * max_single / next_open
            qty = min(qty_by_risk, qty_by_cash)
            current_exposure = exposure_at(timestamp)
            qty_by_portfolio = max(0.0, (initial_cash * max_expo - current_exposure) / next_open)
            qty = min(qty, qty_by_portfolio)
            if qty <= 0:
                continue
            entry_fee = qty * next_open * fee_bps / 10000.0
            total = qty * next_open + entry_fee
            if total <= cash:
                pending[symbol] = {
                    "entry_time": frame.index[int(loc) + 1],
                    "entry": next_open,
                    "entry_fee": entry_fee,
                    "qty": qty,
                    "stop": next_open * (1.0 - sl),
                    "target": next_open * (1.0 + tp),
                    "trail": next_open * (1.0 - trail),
                    "peak": next_open,
                }

        equity_rows.append((timestamp, equity_at(timestamp)))

    # Liquidación final de posiciones y cancelación de órdenes pendientes.
    for symbol, pos in list(positions.items()):
        frame = frames[symbol]
        last = float(frame.iloc[-1]["close"]) * (1.0 - slippage_bps / 10000.0)
        fees = (pos["qty"] * pos["entry"] + pos["qty"] * last) * fee_bps / 10000.0
        pnl = pos["qty"] * (last - pos["entry"]) - fees
        trades.append(PortfolioTrade(symbol, pos["entry_time"], frame.index[-1], pos["entry"], last, pos["qty"], pnl, (last / pos["entry"] - 1.0) * 100.0, "end_of_data"))
        cash += pos["qty"] * last - fees
    if equity_rows:
        equity_rows[-1] = (equity_rows[-1][0], cash)

    equity = pd.Series(dict(equity_rows), dtype=float).sort_index()
    returns = equity.pct_change().dropna()
    total_return = float(equity.iloc[-1] / initial_cash - 1.0) if len(equity) else 0.0
    peak = equity.cummax()
    max_dd = float((equity / peak - 1.0).min()) if len(equity) else 0.0
    wins = [trade.pnl for trade in trades if trade.pnl > 0]
    losses = [-trade.pnl for trade in trades if trade.pnl < 0]
    stats = {
        "initial_cash": float(initial_cash),
        "final_equity": float(equity.iloc[-1]) if len(equity) else float(initial_cash),
        "total_return_pct": total_return * 100.0,
        "max_drawdown_pct": max_dd * 100.0,
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": (len(wins) / len(trades) * 100.0) if trades else 0.0,
        "profit_factor": (sum(wins) / sum(losses)) if losses else (float("inf") if wins else 0.0),
        "expectancy_per_trade": (sum(t.pnl for t in trades) / len(trades)) if trades else 0.0,
        "symbols_traded": len({t.symbol for t in trades}),
        "mean_trade_return_pct": (sum(t.return_pct for t in trades) / len(trades)) if trades else 0.0,
        "positive_periods_pct": (float((returns > 0).mean()) * 100.0) if len(returns) else 0.0,
    }
    return stats, equity.rename("equity").to_frame(), trades


def trades_to_frame(trades: list[PortfolioTrade]) -> pd.DataFrame:
    return pd.DataFrame([asdict(trade) for trade in trades])


__all__ = ["PortfolioTrade", "run_portfolio", "trades_to_frame"]
