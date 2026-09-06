"""Research helpers for walk-forward validation and Monte Carlo stress tests.

This module is deliberately offline: it consumes OHLCV data and a signal function,
never touches Alpaca, and never changes live strategy parameters.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import math
from typing import Callable

import numpy as np
import pandas as pd

import backtest_engine


@dataclass(frozen=True)
class WalkForwardWindow:
    train_start: object
    train_end: object
    test_start: object
    test_end: object
    stats: dict


@dataclass(frozen=True)
class MonteCarloSummary:
    simulations: int
    horizon_trades: int
    median_return_pct: float
    p05_return_pct: float
    p95_return_pct: float
    probability_loss_pct: float
    median_max_drawdown_pct: float
    p95_max_drawdown_pct: float


def walk_forward(
    df: pd.DataFrame,
    signal_fn: Callable[[pd.DataFrame], str] | None = None,
    train_bars: int = 250,
    test_bars: int = 100,
    step_bars: int | None = None,
    **backtest_kwargs,
) -> list[WalkForwardWindow]:
    """Runs rolling out-of-sample windows; training is kept explicit for reporting.

    The current backtest engine is deterministic, so the train slice is evaluated
    only as evidence/context while the returned performance is always from the
    unseen test slice. No parameter is automatically fitted or promoted.
    """
    data = df.sort_index()
    if train_bars < 2 or test_bars < 2:
        raise ValueError("train_bars y test_bars deben ser >= 2")
    step = int(step_bars or test_bars)
    if step < 1:
        raise ValueError("step_bars debe ser >= 1")

    windows: list[WalkForwardWindow] = []
    start = 0
    while start + train_bars + test_bars <= len(data):
        train = data.iloc[start : start + train_bars]
        test = data.iloc[start + train_bars : start + train_bars + test_bars]
        try:
            stats, _, _ = backtest_engine.run(test, signal_fn=signal_fn, **backtest_kwargs)
        except ValueError:
            start += step
            continue
        windows.append(
            WalkForwardWindow(
                train.index[0],
                train.index[-1],
                test.index[0],
                test.index[-1],
                stats,
            )
        )
        start += step
    return windows


def summarize_walk_forward(windows: list[WalkForwardWindow]) -> dict:
    if not windows:
        return {"windows": 0, "consistency_pct": 0.0, "oos_degradation_pct": 0.0}
    returns = np.array([float(w.stats.get("total_return_pct", 0.0)) for w in windows])
    positive = int(np.sum(returns > 0))
    return {
        "windows": len(windows),
        "consistency_pct": positive / len(windows) * 100.0,
        "mean_oos_return_pct": float(returns.mean()),
        "median_oos_return_pct": float(np.median(returns)),
        "worst_oos_return_pct": float(returns.min()),
        # Reserved for comparing train metrics supplied by callers; no fabricated
        # in-sample number is generated here.
        "oos_degradation_pct": 0.0,
    }


def monte_carlo(
    trades: list[backtest_engine.Trade],
    simulations: int = 2000,
    seed: int = 42,
    horizon_trades: int | None = None,
    initial_cash: float = 100_000.0,
) -> MonteCarloSummary:
    """Bootstrap realized trade returns to stress path dependency.

    This is a resampling stress test, not a prediction model. It preserves the
    empirical distribution of trade returns while randomizing their order.
    """
    if simulations < 100:
        raise ValueError("simulations debe ser >= 100")
    returns = np.array([float(t.return_pct) / 100.0 for t in trades], dtype=float)
    if len(returns) < 2:
        raise ValueError("Se necesitan al menos 2 trades para Monte Carlo")
    horizon = int(horizon_trades or len(returns))
    if horizon < 1:
        raise ValueError("horizon_trades debe ser >= 1")
    rng = np.random.default_rng(seed)
    sampled = rng.choice(returns, size=(simulations, horizon), replace=True)
    equity = np.cumprod(1.0 + sampled, axis=1)
    final_returns = equity[:, -1] - 1.0
    peaks = np.maximum.accumulate(equity, axis=1)
    drawdowns = equity / peaks - 1.0
    max_dd = drawdowns.min(axis=1)
    return MonteCarloSummary(
        simulations=simulations,
        horizon_trades=horizon,
        median_return_pct=float(np.median(final_returns) * 100.0),
        p05_return_pct=float(np.percentile(final_returns, 5) * 100.0),
        p95_return_pct=float(np.percentile(final_returns, 95) * 100.0),
        probability_loss_pct=float(np.mean(final_returns < 0) * 100.0),
        median_max_drawdown_pct=float(np.median(max_dd) * 100.0),
        p95_max_drawdown_pct=float(np.percentile(max_dd, 5) * -100.0),
    )


__all__ = [
    "WalkForwardWindow",
    "MonteCarloSummary",
    "walk_forward",
    "summarize_walk_forward",
    "monte_carlo",
]
