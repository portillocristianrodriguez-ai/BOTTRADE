"""Validación walk-forward/OOS de BOTTRADE.

Herramienta de investigación: no envía órdenes. Puede consumir CSVs locales
para reproducibilidad o descargar barras diarias de Alpaca. El universo
histórico se documenta como universo actual cuando se obtiene desde activos
actuales, evitando presentar ese resultado como libre de survivorship bias.
"""
from __future__ import annotations

import argparse
import math
import os
from pathlib import Path
from typing import Callable, Mapping

import numpy as np
import pandas as pd

from portfolio_backtest import run_portfolio


def cargar_csvs(directory: str | os.PathLike) -> dict[str, pd.DataFrame]:
    root = Path(directory)
    result = {}
    for path in sorted(root.glob("*.csv")):
        symbol = path.stem.upper()
        frame = pd.read_csv(path)
        if "timestamp" in frame.columns:
            frame = frame.set_index("timestamp")
        elif "date" in frame.columns:
            frame = frame.set_index("date")
        frame.index = pd.to_datetime(frame.index, utc=True)
        result[symbol] = frame
    if not result:
        raise ValueError(f"No se encontraron CSV en {root}")
    return result


def descargar_alpaca(symbols: list[str], start: str, end: str, cache_dir: str = "research_data", feed: str | None = None) -> dict[str, pd.DataFrame]:
    """Descarga barras diarias en lotes y las guarda por símbolo.

    Requiere ALPACA_API_KEY/ALPACA_API_SECRET. El feed por defecto queda en
    manos de la suscripción de Alpaca; `feed=sip` exige permisos adecuados.
    """
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    key = os.environ.get("ALPACA_API_KEY", "")
    secret = os.environ.get("ALPACA_API_SECRET", "")
    if not key or not secret:
        raise RuntimeError("Faltan ALPACA_API_KEY/ALPACA_API_SECRET para descargar históricos.")
    root = Path(cache_dir)
    root.mkdir(parents=True, exist_ok=True)
    client = StockHistoricalDataClient(key, secret)
    result: dict[str, pd.DataFrame] = {}
    for offset in range(0, len(symbols), 100):
        batch = symbols[offset:offset + 100]
        request_kwargs = {
            "symbol_or_symbols": batch,
            "timeframe": TimeFrame.Day,
            "start": pd.Timestamp(start).to_pydatetime(),
            "end": pd.Timestamp(end).to_pydatetime(),
        }
        if feed:
            from alpaca.data.enums import DataFeed
            request_kwargs["feed"] = DataFeed(feed)
        bars = client.get_stock_bars(StockBarsRequest(**request_kwargs)).df
        if bars is None or bars.empty:
            continue
        for symbol in batch:
            try:
                frame = bars.xs(symbol, level="symbol").copy()
            except (KeyError, TypeError):
                continue
            frame.index = pd.to_datetime(frame.index, utc=True)
            frame = frame.rename(columns={"v": "volume", "o": "open", "h": "high", "l": "low", "c": "close"})
            if set(["open", "high", "low", "close", "volume"]).issubset(frame.columns):
                frame.to_csv(root / f"{symbol}.csv", index_label="timestamp")
                result[symbol] = frame
    return result


def metricas_oos(equity: pd.Series, stats: Mapping, initial_cash: float) -> dict:
    eq = pd.Series(equity, dtype=float).dropna()
    if len(eq) < 2:
        return {"return_pct": 0.0, "cagr_pct": 0.0, "max_drawdown_pct": 0.0, "sharpe": 0.0, "sortino": 0.0, "calmar": 0.0}
    years = max((eq.index[-1] - eq.index[0]).total_seconds() / (365.25 * 86400.0), 0.0)
    total = float(eq.iloc[-1] / initial_cash - 1.0)
    cagr = (float(eq.iloc[-1] / initial_cash) ** (1.0 / years) - 1.0) if years > 0 and eq.iloc[-1] > 0 else 0.0
    dd = float((eq / eq.cummax() - 1.0).min())
    ret = eq.pct_change().dropna()
    sharpe = float(ret.mean() / ret.std(ddof=1) * math.sqrt(252.0)) if len(ret) > 1 and ret.std(ddof=1) else 0.0
    downside = ret[ret < 0]
    down_dev = float(np.sqrt((downside ** 2).mean())) if len(downside) else 0.0
    sortino = float(ret.mean() / down_dev * math.sqrt(252.0)) if down_dev else (float("inf") if ret.mean() > 0 else 0.0)
    calmar = cagr / abs(dd) if dd < 0 else (float("inf") if cagr > 0 else 0.0)
    return {"return_pct": total * 100.0, "cagr_pct": cagr * 100.0, "max_drawdown_pct": dd * 100.0, "sharpe": sharpe, "sortino": sortino, "calmar": calmar, "trades": int(stats.get("trades", 0)), "profit_factor": float(stats.get("profit_factor", 0.0))}


def score_oos(rows: list[dict], min_trades: int = 5) -> list[dict]:
    """Puntúa estabilidad OOS; no optimiza parámetros de estrategia."""
    if not rows:
        return []
    frame = pd.DataFrame(rows).replace([np.inf, -np.inf], np.nan)
    for col in ["cagr_pct", "sharpe", "sortino", "calmar", "profit_factor", "max_drawdown_pct"]:
        if col not in frame:
            frame[col] = 0.0
        frame[col] = frame[col].fillna(0.0)
    frame["trade_ok"] = frame["trades"] >= min_trades
    frame["positive"] = frame["return_pct"] > 0
    grouped = frame.groupby("symbol").agg(
        oos_return_pct=("return_pct", "mean"),
        oos_cagr_pct=("cagr_pct", "mean"),
        oos_sharpe=("sharpe", "mean"),
        oos_sortino=("sortino", "mean"),
        oos_calmar=("calmar", "mean"),
        worst_drawdown_pct=("max_drawdown_pct", "min"),
        profit_factor=("profit_factor", "mean"),
        trades=("trades", "sum"),
        windows=("symbol", "count"),
        positive_windows=("positive", "sum"),
    ).reset_index()
    grouped["consistency_pct"] = grouped["positive_windows"] / grouped["windows"] * 100.0
    grouped["score"] = (
        grouped["oos_cagr_pct"].clip(-50, 50) * 0.30
        + grouped["oos_sharpe"].clip(-3, 5) * 8.0 * 0.20
        + grouped["oos_sortino"].clip(-3, 8) * 5.0 * 0.15
        + grouped["oos_calmar"].clip(-3, 8) * 5.0 * 0.15
        + grouped["consistency_pct"] * 0.15
        + grouped["profit_factor"].clip(0, 5) * 2.0 * 0.05
        + grouped["worst_drawdown_pct"].clip(-50, 0) * 0.10
    )
    grouped.loc[grouped["trades"] < min_trades, "score"] -= 20.0
    return grouped.sort_values(["score", "oos_cagr_pct"], ascending=False).to_dict("records")


def validar_walk_forward(data: Mapping[str, pd.DataFrame], signal_fn: Callable, windows: list[tuple[str, str]], initial_cash: float = 100_000.0, warmup_days: int = 260, fee_bps: float = 5.0, slippage_bps: float = 5.0) -> list[dict]:
    """Evalúa ventanas OOS independientes usando historial de warm-up sin operar antes del inicio."""
    rows = []
    for symbol, frame in sorted(data.items()):
        frame = frame.sort_index()
        for start, end in windows:
            start_ts, end_ts = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")
            context = frame.loc[:end_ts]
            if context.empty:
                continue
            context = context.loc[max(frame.index.min(), start_ts - pd.Timedelta(days=warmup_days)):end_ts]
            if context.empty:
                continue
            def gated(_symbol, hist, _start=start_ts):
                if hist.index[-1] < _start:
                    return "ESPERAR"
                return signal_fn(_symbol, hist)
            stats, equity, _ = run_portfolio({symbol: context}, initial_cash=initial_cash, signal_fn=gated, fee_bps=fee_bps, slippage_bps=slippage_bps, max_positions=1, max_total_exposure_pct=1.0, max_single_position_pct=1.0)
            eq = equity.loc[equity.index >= start_ts, "equity"]
            if eq.empty:
                continue
            metrics = metricas_oos(eq, stats, initial_cash)
            rows.append({"symbol": symbol, "window_start": start, "window_end": end, **metrics})
    return rows


def _signal(_symbol: str, df: pd.DataFrame) -> str:
    from estrategia import generar_senal
    return generar_senal(df)


def main() -> int:
    parser = argparse.ArgumentParser(description="Walk-forward/OOS de BOTTRADE")
    parser.add_argument("--data-dir", default="research_data")
    parser.add_argument("--symbols", default="", help="Símbolos separados por coma; si se omite, usa CSV disponibles")
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--end", default="2026-01-01")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--min-trades", type=int, default=5)
    args = parser.parse_args()
    if args.download:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        if not symbols:
            raise SystemExit("--download requiere --symbols")
        data = descargar_alpaca(symbols, args.start, args.end, args.data_dir)
    else:
        data = cargar_csvs(args.data_dir)
    windows = [("2023-01-01", "2023-12-31"), ("2024-01-01", "2024-12-31"), ("2025-01-01", "2025-12-31")]
    rows = validar_walk_forward(data, _signal, windows)
    ranking = score_oos(rows, args.min_trades)
    print(pd.DataFrame(ranking).head(20).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
