"""
research/backtest/metrics.py

Computes aggregate performance metrics from a list of simulated trades.
All inputs are plain dicts for easy serialization to BacktestRun columns.
"""

from __future__ import annotations

import math
import statistics
from typing import Optional


def compute_metrics(
    trades: list[dict],
    initial_capital: float,
) -> dict:
    """
    Compute aggregate performance metrics from a list of completed trades.

    Each trade dict must have at minimum:
      net_pnl (float)     — net P&L after all charges
      gross_pnl (float)   — gross P&L before charges
      charges (float)     — total charges paid

    Optional (added by BacktestEngine >= MAE/MFE update):
      mfe_r (float)  — Maximum Favorable Excursion in R-multiples
      mae_r (float)  — Maximum Adverse Excursion in R-multiples

    Returns a dict matching BacktestRun column names.
    """
    if not trades:
        return _empty_metrics()

    net_pnls   = [t["net_pnl"]   for t in trades]
    gross_pnls = [t["gross_pnl"] for t in trades]
    charges    = [t["charges"]   for t in trades]

    winners = [p for p in net_pnls if p > 0]
    losers  = [p for p in net_pnls if p <= 0]

    total_trades  = len(trades)
    winning_count = len(winners)
    losing_count  = len(losers)
    win_rate      = winning_count / total_trades if total_trades else 0.0

    gross_profit = sum(winners) if winners else 0.0
    gross_loss   = abs(sum(losers)) if losers else 0.0
    net_pnl      = sum(net_pnls)
    total_charges = sum(charges)

    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None
    expectancy    = (net_pnl / total_trades) if total_trades else 0.0

    avg_winner = statistics.mean(winners) if winners else 0.0
    avg_loser  = abs(statistics.mean(losers)) if losers else 0.0

    # Equity curve
    equity_curve = _build_equity_curve(initial_capital, net_pnls)
    max_dd_pct, max_dd_abs = _max_drawdown(equity_curve)

    # We return net_return_pct for simplicity
    net_return_pct = (net_pnl / initial_capital) * 100 if initial_capital else 0.0

    # Max consecutive losses
    max_consec_losses = _max_consecutive_losses(net_pnls)

    # Simplified Sharpe: mean(returns) / std(returns)
    sharpe = _simplified_sharpe(net_pnls)

    # ── MAE / MFE aggregates ─────────────────────────────────────────────────
    mfe_r_vals = [t["mfe_r"] for t in trades if t.get("mfe_r") is not None]
    mae_r_vals = [t["mae_r"] for t in trades if t.get("mae_r") is not None]

    avg_mfe_r = round(statistics.mean(mfe_r_vals), 3) if mfe_r_vals else None
    avg_mae_r = round(statistics.mean(mae_r_vals), 3) if mae_r_vals else None

    # % of trades where MFE never reached 1R → entry timing problem (entered too late/early)
    entry_too_late_pct = (
        round(sum(1 for r in mfe_r_vals if r < 0.5) / len(mfe_r_vals) * 100, 1)
        if mfe_r_vals else None
    )

    # % of trades where MAE exceeded 1R → stop too large (or position sizing wrong)
    stop_too_large_pct = (
        round(sum(1 for r in mae_r_vals if r > 1.0) / len(mae_r_vals) * 100, 1)
        if mae_r_vals else None
    )

    # Exit efficiency: what % of maximum available MFE was actually captured
    # A low number means the strategy exits too early or the target is misplaced
    exit_efficiencies = []
    for t in trades:
        mfe = t.get("mfe_r")
        r   = t.get("r_multiple")
        if mfe and mfe > 0 and r is not None:
            exit_efficiencies.append(min(1.0, max(0.0, r / mfe)))
    exit_efficiency_pct = (
        round(statistics.mean(exit_efficiencies) * 100, 1) if exit_efficiencies else None
    )

    return {
        "total_trades":           total_trades,
        "winning_trades":         winning_count,
        "losing_trades":          losing_count,
        "win_rate":               round(win_rate, 4),
        "gross_profit":           round(gross_profit, 4),
        "gross_loss":             round(gross_loss, 4),
        "net_pnl":                round(net_pnl, 4),
        "total_charges":          round(total_charges, 4),
        "profit_factor":          round(profit_factor, 4) if profit_factor else None,
        "max_drawdown":           round(max_dd_pct, 4),
        "max_drawdown_abs":       round(max_dd_abs, 4),
        "expectancy":             round(expectancy, 4),
        "sharpe":                 round(sharpe, 4) if sharpe else None,
        "max_consecutive_losses": max_consec_losses,
        "avg_winner":             round(avg_winner, 4),
        "avg_loser":              round(avg_loser, 4),
        "net_return_pct":         round(net_return_pct, 4),
        "equity_curve":           equity_curve,
        # MAE / MFE diagnostics
        "avg_mfe_r":              avg_mfe_r,
        "avg_mae_r":              avg_mae_r,
        "entry_too_late_pct":     entry_too_late_pct,
        "stop_too_large_pct":     stop_too_large_pct,
        "exit_efficiency_pct":    exit_efficiency_pct,
    }


def _empty_metrics() -> dict:
    return {
        "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
        "win_rate": 0.0, "gross_profit": 0.0, "gross_loss": 0.0,
        "net_pnl": 0.0, "total_charges": 0.0, "profit_factor": None,
        "max_drawdown": 0.0, "max_drawdown_abs": 0.0, "expectancy": 0.0,
        "sharpe": None, "max_consecutive_losses": 0,
        "avg_winner": 0.0, "avg_loser": 0.0, "net_return_pct": 0.0,
        "equity_curve": [],
    }


def _build_equity_curve(initial: float, net_pnls: list[float]) -> list[float]:
    """Cumulative equity after each trade."""
    curve = [initial]
    running = initial
    for pnl in net_pnls:
        running += pnl
        curve.append(round(running, 4))
    return curve


def _max_drawdown(equity_curve: list[float]) -> tuple[float, float]:
    """
    Peak-to-trough maximum drawdown.
    Returns (max_dd_pct, max_dd_abs_Rs).
    """
    if len(equity_curve) < 2:
        return 0.0, 0.0

    peak = equity_curve[0]
    max_dd_pct = 0.0
    max_dd_abs = 0.0

    for val in equity_curve:
        if val > peak:
            peak = val
        dd_abs = peak - val
        dd_pct = (dd_abs / peak * 100) if peak > 0 else 0.0
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
            max_dd_abs = dd_abs

    return max_dd_pct, max_dd_abs


def _max_consecutive_losses(net_pnls: list[float]) -> int:
    """Count the longest streak of consecutive losing trades."""
    max_streak = 0
    current    = 0
    for p in net_pnls:
        if p <= 0:
            current += 1
            max_streak = max(max_streak, current)
        else:
            current = 0
    return max_streak


def _simplified_sharpe(net_pnls: list[float]) -> Optional[float]:
    """Simplified Sharpe = mean_pnl / std_pnl. Not annualized."""
    if len(net_pnls) < 2:
        return None
    mean = statistics.mean(net_pnls)
    std  = statistics.stdev(net_pnls)
    if std == 0:
        return None
    return mean / std
