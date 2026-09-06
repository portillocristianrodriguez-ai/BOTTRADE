"""Offline research helpers for walk-forward validation and Monte Carlo stress tests.

This module never touches Alpaca, never sends orders, and never applies strategy
changes. Walk-forward selection is research-only: parameters selected on each
training slice are evaluated on the following unseen slice.
"""
from __future__ import annotations

from dataclasses import dataclass
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
    selected_params: dict | None = None
    train_stats: dict | None = None


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


def _candidate_score(stats: dict) -> float:
    """Conservative train score: reward return, penalize drawdown."""
    return float(stats.get("total_return_pct", 0.0)) - 0.5 * abs(
        float(stats.get("max_drawdown_pct", 0.0))
    )


def walk_forward(
    df: pd.DataFrame,
    signal_fn: Callable[[pd.DataFrame], str] | None = None,
    train_bars: int = 250,
    test_bars: int = 100,
    step_bars: int | None = None,
    parameter_grid: list[dict] | None = None,
    signal_factory: Callable[[dict], Callable[[pd.DataFrame], str]] | None = None,
    min_train_trades: int = 1,
    **backtest_kwargs,
) -> list[WalkForwardWindow]:
    """Run rolling OOS tests, optionally selecting a candidate on each train slice.

    ``parameter_grid`` contains candidate backtest parameters. When supplied,
    ``signal_factory`` converts each candidate dict into a signal function. The
    best candidate is chosen strictly from the training slice and then evaluated
    once on the following unseen test slice. Nothing is promoted automatically.
    """
    data = df.sort_index()
    if train_bars < 2 or test_bars < 2:
        raise ValueError("train_bars y test_bars deben ser >= 2")
    if min_train_trades < 0:
        raise ValueError("min_train_trades debe ser >= 0")
    if parameter_grid is not None and not parameter_grid:
        raise ValueError("parameter_grid no puede estar vacío")
    if parameter_grid is not None and signal_factory is None:
        raise ValueError("signal_factory es obligatorio con parameter_grid")

    step = int(step_bars or test_bars)
    if step < 1:
        raise ValueError("step_bars debe ser >= 1")

    windows: list[WalkForwardWindow] = []
    start = 0
    while start + train_bars + test_bars <= len(data):
        train = data.iloc[start : start + train_bars]
        test = data.iloc[start + train_bars : start + train_bars + test_bars]
        selected_params = None
        train_stats = None
        selected_signal = signal_fn
        selected_kwargs = dict(backtest_kwargs)

        if parameter_grid is not None:
            candidates = []
            for params in parameter_grid:
                candidate_kwargs = dict(backtest_kwargs)
                candidate_kwargs.update(params)
                candidate_signal = signal_factory(dict(params))
                try:
                    stats, _, trades = backtest_engine.run(
                        train, signal_fn=candidate_signal, **candidate_kwargs
                    )
                except (TypeError, ValueError):
                    continue
                if int(stats.get("trades", len(trades))) < min_train_trades:
                    continue
                candidates.append((_candidate_score(stats), dict(params), stats, candidate_signal, candidate_kwargs))
            if not candidates:
                start += step
                continue
            _, selected_params, train_stats, selected_signal, selected_kwargs = max(
                candidates, key=lambda item: item[0]
            )

        try:
            stats, _, _ = backtest_engine.run(
                test, signal_fn=selected_signal, **selected_kwargs
            )
        except (TypeError, ValueError):
            start += step
            continue

        windows.append(
            WalkForwardWindow(
                train.index[0],
                train.index[-1],
                test.index[0],
                test.index[-1],
                stats,
                selected_params,
                train_stats,
            )
        )
        start += step
    return windows


def summarize_walk_forward(windows: list[WalkForwardWindow]) -> dict:
    if not windows:
        return {
            "windows": 0,
            "consistency_pct": 0.0,
            "oos_degradation_pct": 0.0,
        }
    returns = np.array([float(w.stats.get("total_return_pct", 0.0)) for w in windows])
    positive = int(np.sum(returns > 0))
    train_returns = np.array(
        [float(w.train_stats.get("total_return_pct", 0.0)) for w in windows if w.train_stats]
    )
    mean_train = float(train_returns.mean()) if len(train_returns) else 0.0
    mean_oos = float(returns.mean())
    degradation = max(0.0, (mean_train - mean_oos) / abs(mean_train) * 100.0) if mean_train else 0.0
    return {
        "windows": len(windows),
        "consistency_pct": positive / len(windows) * 100.0,
        "mean_oos_return_pct": mean_oos,
        "median_oos_return_pct": float(np.median(returns)),
        "worst_oos_return_pct": float(returns.min()),
        "mean_train_return_pct": mean_train,
        "oos_degradation_pct": degradation,
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
    if horizon < 1 or not np.isfinite(initial_cash) or initial_cash <= 0:
        raise ValueError("horizon_trades e initial_cash deben ser válidos")
    rng = np.random.default_rng(seed)
    sampled = rng.choice(returns, size=(simulations, horizon), replace=True)
    equity = float(initial_cash) * np.cumprod(1.0 + sampled, axis=1)
    final_returns = equity[:, -1] / float(initial_cash) - 1.0
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
        p95_max_drawdown_pct=float(np.percentile(max_dd, 5) * 100.0),
    )


__all__ = [
    "WalkForwardWindow",
    "MonteCarloSummary",
    "walk_forward",
    "summarize_walk_forward",
    "monte_carlo",
]
