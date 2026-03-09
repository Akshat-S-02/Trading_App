"""
research/backtest/engine.py

Generic, strategy-agnostic backtesting engine.

Enforces the NO-LOOKAHEAD contract: bars are fed to the strategy one at a time
in chronological order. The strategy never sees future data.

Config is stored as a JSON snapshot in BacktestRun for full reproducibility.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import zoneinfo

from research.db import SessionLocal, init_db
from research.data.candle_repository import get_candles
from research.data.instrument_repository import get_instrument
from research.data.models import BacktestRun, BacktestTrade
from research.strategies.base import BaseStrategy, Signal
from research.backtest.metrics import compute_metrics
from research.utils.fee_calculator import FeeConfig, SlippageConfig, calculate_charges, calculate_slippage
from research.utils.market_calendar import is_trading_day, is_past_squareoff

logger = logging.getLogger("BacktestEngine")

_IST = zoneinfo.ZoneInfo("Asia/Kolkata")
_UTC = timezone.utc


@dataclass
class RiskConfig:
    capital:       float = 100_000.0  # total portfolio capital in Rs
    risk_pct:      float = 1.0        # risk % of capital per trade
    max_positions: int   = 3          # max concurrent open positions


class BacktestResult:
    """Return object from engine.run(). Contains trades list + computed metrics."""

    def __init__(self, trades: list[dict], metrics: dict, run_id: Optional[int] = None):
        self.trades  = trades
        self.metrics = metrics
        self.run_id  = run_id

    def summary(self) -> str:
        m = self.metrics
        lines = [
            f"\n{'='*55}",
            f"  BACKTEST RESULT",
            f"{'='*55}",
            f"  Total Trades    : {m['total_trades']}",
            f"  Win Rate        : {m['win_rate']*100:.1f}%  ({m['winning_trades']}W / {m['losing_trades']}L)",
            f"  Net P&L         : Rs.{m['net_pnl']:,.2f}",
            f"  Return          : {m['net_return_pct']:.2f}%",
            f"  Total Charges   : Rs.{m['total_charges']:,.2f}",
            f"  Profit Factor   : {m['profit_factor'] or 'N/A'}",
            f"  Max Drawdown    : {m['max_drawdown']:.2f}% (Rs.{m['max_drawdown_abs']:,.2f})",
            f"  Expectancy      : Rs.{m['expectancy']:,.2f} per trade",
            f"  Max Consec Loss : {m['max_consecutive_losses']}",
            f"  Sharpe          : {m['sharpe'] or 'N/A'}",
            f"{'='*55}",
        ]
        return "\n".join(lines)


class BacktestEngine:
    """
    Generic backtesting engine — strategy-agnostic.

    Usage:
      engine = BacktestEngine(
          symbols=["RELIANCE", "TCS"],
          timeframe="5m",
          from_date="2024-01-01",
          to_date="2024-06-30",
          strategy=NiftyBreakoutStrategy(),
          fee_config=FeeConfig(),
          slippage_config=SlippageConfig(ticks=1),
          risk_config=RiskConfig(capital=100_000, risk_pct=1.0, max_positions=3),
      )
      result = engine.run()
      print(result.summary())
    """

    def __init__(
        self,
        symbols: list[str],
        timeframe: str,
        from_date: str,           # "YYYY-MM-DD"
        to_date:   str,
        strategy:  BaseStrategy,
        fee_config:      FeeConfig      = None,
        slippage_config: SlippageConfig = None,
        risk_config:     RiskConfig     = None,
        save_to_db:      bool           = True,
    ):
        self.symbols         = symbols
        self.timeframe       = timeframe
        self.from_date       = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=_UTC)
        self.to_date         = datetime.strptime(to_date,   "%Y-%m-%d").replace(tzinfo=_UTC)
        self.strategy        = strategy
        self.fee_config      = fee_config      or FeeConfig()
        self.slippage_config = slippage_config or SlippageConfig()
        self.risk_config     = risk_config     or RiskConfig()
        self.save_to_db      = save_to_db

    # -----------------------------------------------------------------------
    # Main entry point
    # -----------------------------------------------------------------------

    def run(self) -> BacktestResult:
        """Execute the backtest. Returns a BacktestResult with trades and metrics."""
        logger.info(
            f"Backtest: strategy={self.strategy.get_name()} v{self.strategy.get_version()} | "
            f"symbols={self.symbols} | tf={self.timeframe} | "
            f"{self.from_date.date()} → {self.to_date.date()}"
        )

        all_trades: list[dict] = []

        for symbol in self.symbols:
            inst = get_instrument(symbol)
            if not inst:
                logger.warning(f"Symbol '{symbol}' not in NIFTY 50 registry — skipping")
                continue

            trades = self._run_symbol(
                symbol=symbol,
                security_id=inst["security_id"],
            )
            all_trades.extend(trades)
            logger.info(f"  {symbol}: {len(trades)} trades")

        metrics = compute_metrics(all_trades, self.risk_config.capital)

        run_id = None
        if self.save_to_db:
            run_id = self._save_run(all_trades, metrics)

        return BacktestResult(trades=all_trades, metrics=metrics, run_id=run_id)

    # -----------------------------------------------------------------------
    # Per-symbol backtest
    # -----------------------------------------------------------------------

    def _run_symbol(self, symbol: str, security_id: str) -> list[dict]:
        """Run the strategy on all candles for one symbol. Returns list of closed trades."""
        df = get_candles(security_id, self.timeframe, self.from_date, self.to_date)
        if df.empty:
            logger.warning(f"  {symbol}: no candles in DB for {self.from_date.date()} → {self.to_date.date()}")
            return []

        completed_trades: list[dict] = []
        current_position: Optional[dict] = None  # open trade state
        session_history:  list[dict]     = []     # bars seen this session
        current_day:      Optional[datetime] = None

        rows = df.to_dict("records")   # list of bar dicts

        for bar in rows:
            bar_utc = bar["timestamp"]
            bar_ist = bar_utc.astimezone(_IST)
            bar_day = bar_ist.date()

            # ── Day boundary: reset strategy + session history ──────────────
            if current_day != bar_day:
                # EOD squareoff if position still open at day end (shouldn't normally happen,
                # but guards against missing candles around 15:15)
                if current_position is not None:
                    trade = self._close_position(
                        position=current_position,
                        exit_bar=bar,
                        exit_reason="eod_squareoff",
                    )
                    completed_trades.append(trade)
                    current_position = None

                current_day = bar_day
                session_history = []
                self.strategy.on_day_start(bar_utc, symbol)

            # ── MAE/MFE: update running high/low while in a position ────────
            if current_position is not None:
                current_position["running_high"] = max(
                    current_position["running_high"], bar["high"]
                )
                current_position["running_low"] = min(
                    current_position["running_low"], bar["low"]
                )

            # ── Intraday: check exits for open position ─────────────────────
            if current_position is not None:
                closed, trade = self._check_exit(current_position, bar, session_history)
                if closed:
                    completed_trades.append(trade)
                    current_position = None
                else:
                    # Update trailing stop
                    new_stop = self.strategy.get_trailing_stop(
                        current_bar=bar,
                        all_bars_since_entry=session_history,
                        entry_price=current_position["entry_price"],
                        stop_loss=current_position["stop_loss"],
                        initial_risk=current_position["initial_risk"],
                    )
                    current_position["stop_loss"] = new_stop

            # ── Ask strategy for a signal ───────────────────────────────────
            if current_position is None:
                signal: Optional[Signal] = self.strategy.on_bar(
                    bar=bar,
                    history=list(session_history),   # pass a COPY — strategy must not mutate
                    position=current_position,
                )
                if signal is not None:
                    entry = self._open_position(signal, bar, symbol, security_id)
                    if entry is not None:
                        current_position = entry

            session_history.append(bar)  # append AFTER strategy call — no lookahead

        # Close any position still open at the very end of the date range
        if current_position is not None:
            trade = self._close_position(
                position=current_position,
                exit_bar=rows[-1],
                exit_reason="eod_squareoff",
            )
            completed_trades.append(trade)

        return completed_trades

    # -----------------------------------------------------------------------
    # Position open / close helpers
    # -----------------------------------------------------------------------

    def _open_position(
        self,
        signal: Signal,
        bar: dict,
        symbol: str,
        security_id: str,
    ) -> Optional[dict]:
        """
        Calculate position size from risk config, apply entry slippage, charge entry fees.
        Returns a position dict, or None if qty would be 0.
        """
        risk_per_trade = self.risk_config.capital * (self.risk_config.risk_pct / 100)
        risk_per_share = signal.entry_price - signal.stop_loss

        if risk_per_share <= 0:
            return None

        qty = max(1, int(risk_per_trade / risk_per_share))

        # Entry slippage: price moves against us on entry
        slippage_rs = calculate_slippage(self.slippage_config, qty)
        actual_entry = signal.entry_price + slippage_rs / qty  # slightly worse price

        entry_charges = calculate_charges(self.fee_config, "buy", qty, actual_entry)

        return {
            "symbol":               symbol,
            "security_id":          security_id,
            "direction":            signal.direction,
            "entry_time":           bar["timestamp"],
            "entry_price":          actual_entry,
            "stop_loss":            signal.stop_loss,
            "target":               signal.target,
            "quantity":             qty,
            "entry_charges":        entry_charges["total"],
            "entry_slippage":       slippage_rs,
            "initial_risk":         risk_per_share,
            "entry_reason":         signal.entry_reason,
            "or_high":              signal.meta.get("or_high"),
            "or_low":               signal.meta.get("or_low"),
            # Volume audit fields (from signal meta)
            "volume_at_entry":      signal.meta.get("volume_at_entry"),
            "rolling_avg_volume":   signal.meta.get("rolling_avg_volume"),
            "breakout_buffer_pct":  signal.meta.get("breakout_buffer_pct"),
            # MAE/MFE accumulators — updated each bar while position is open
            "running_high":         bar["high"],
            "running_low":          bar["low"],
            "initial_stop":         signal.stop_loss,  # preserve original stop for MAE calc
        }

    def _check_exit(
        self,
        position: dict,
        bar: dict,
        history: list[dict],
    ) -> tuple[bool, Optional[dict]]:
        """
        Check stop loss, target, and EOD squareoff for the current bar.
        Returns (should_exit, trade_dict).
        """
        high  = bar["high"]
        low   = bar["low"]
        close = bar["close"]

        exit_reason  = None
        exit_price   = None

        # Stop loss hit (low touched stop)
        if low <= position["stop_loss"]:
            exit_reason = "stop_loss"
            exit_price  = position["stop_loss"]

        # Target hit (high touched target)
        elif high >= position["target"]:
            exit_reason = "target_hit"
            exit_price  = position["target"]

        # EOD squareoff
        elif is_past_squareoff(bar["timestamp"]):
            exit_reason = "eod_squareoff"
            exit_price  = close

        if exit_reason:
            trade = self._close_position(position, bar, exit_reason, exit_price)
            return True, trade

        return False, None

    def _close_position(
        self,
        position: dict,
        exit_bar: dict,
        exit_reason: str,
        exit_price: Optional[float] = None,
    ) -> dict:
        """Close a position and compute P&L, charges, slippage, MAE, and MFE."""
        if exit_price is None:
            exit_price = exit_bar["close"]

        qty = position["quantity"]

        # Exit slippage: price moves against us on exit (slightly worse than expected)
        slippage_rs = calculate_slippage(self.slippage_config, qty)
        actual_exit = exit_price - (slippage_rs / qty)  # worse fill on exit for longs

        exit_charges = calculate_charges(self.fee_config, "sell", qty, actual_exit)

        gross_pnl     = (actual_exit - position["entry_price"]) * qty
        total_charges = position["entry_charges"] + exit_charges["total"]
        net_pnl       = gross_pnl - total_charges

        # R_multiple: how many R did this trade actually return (net of all costs)
        initial_risk_rs = position["initial_risk"] * qty  # 1R in Rs
        r_multiple = round(net_pnl / initial_risk_rs, 3) if initial_risk_rs > 0 else None

        # ── MAE / MFE ─────────────────────────────────────────────────────────
        # MAE = Maximum Adverse Excursion: worst price move AGAINST the position
        # MFE = Maximum Favorable Excursion: best price move IN FAVOUR of the position
        # Both expressed in Rs per share and in R-multiples (per-share risk = initial_risk)
        entry       = position["entry_price"]
        risk        = position["initial_risk"]  # price distance from entry to original stop

        best_high   = position.get("running_high", entry)
        worst_low   = position.get("running_low",  entry)

        mfe_rs = round(max(0.0, best_high  - entry), 4)   # best unrealized gain per share
        mae_rs = round(max(0.0, entry - worst_low), 4)     # worst unrealized loss per share

        mfe_r  = round(mfe_rs / risk, 3) if risk > 0 else None
        mae_r  = round(mae_rs / risk, 3) if risk > 0 else None

        return {
            "symbol":              position["symbol"],
            "security_id":         position["security_id"],
            "direction":           position["direction"],
            "entry_time":          position["entry_time"],
            "exit_time":           exit_bar["timestamp"],
            "entry_price":         round(entry, 4),
            "exit_price":          round(actual_exit, 4),
            "quantity":            qty,
            "gross_pnl":           round(gross_pnl, 4),
            "charges":             round(total_charges, 4),
            "net_pnl":             round(net_pnl, 4),
            "slippage_entry":      round(position["entry_slippage"], 4),
            "slippage_exit":       round(slippage_rs, 4),
            "entry_reason":        position["entry_reason"],
            "exit_reason":         exit_reason,
            "stop_loss":           position["stop_loss"],
            "target":              position["target"],
            "opening_range_high":  position.get("or_high"),
            "opening_range_low":   position.get("or_low"),
            # Volume audit fields
            "volume_at_entry":     position.get("volume_at_entry"),
            "rolling_avg_volume":  position.get("rolling_avg_volume"),
            "breakout_buffer_pct": position.get("breakout_buffer_pct"),
            # R-multiple (net of fees and slippage)
            "r_multiple":          r_multiple,
            # MAE / MFE
            "mfe_rs":              mfe_rs,
            "mae_rs":              mae_rs,
            "mfe_r":               mfe_r,
            "mae_r":               mae_r,
        }

    # -----------------------------------------------------------------------
    # DB persistence
    # -----------------------------------------------------------------------

    def _save_run(self, trades: list[dict], metrics: dict) -> int:
        """Save BacktestRun + BacktestTrade rows to research.db. Returns run_id."""
        init_db()
        db = SessionLocal()
        try:
            config_snapshot = {
                "strategy_params": self.strategy.get_params(),
                "fee_config": {
                    "brokerage_per_order": self.fee_config.brokerage_per_order,
                    "stt_sell_pct":        self.fee_config.stt_sell_pct,
                    "exchange_pct":        self.fee_config.exchange_pct,
                    "sebi_pct":            self.fee_config.sebi_pct,
                    "gst_pct":             self.fee_config.gst_pct,
                    "stamp_pct":           self.fee_config.stamp_pct,
                },
                "slippage_config": {
                    "ticks":     self.slippage_config.ticks,
                    "tick_size": self.slippage_config.tick_size,
                },
                "risk_config": {
                    "capital":       self.risk_config.capital,
                    "risk_pct":      self.risk_config.risk_pct,
                    "max_positions": self.risk_config.max_positions,
                },
                "universe":   self.symbols,
                "timeframe":  self.timeframe,
                "from_date":  self.from_date.strftime("%Y-%m-%d"),
                "to_date":    self.to_date.strftime("%Y-%m-%d"),
            }

            run = BacktestRun(
                strategy_name    = self.strategy.get_name(),
                strategy_version = self.strategy.get_version(),
                timeframe        = self.timeframe,
                from_date        = self.from_date.strftime("%Y-%m-%d"),
                to_date          = self.to_date.strftime("%Y-%m-%d"),
                universe         = self.symbols,
                config_snapshot  = config_snapshot,
                total_trades        = metrics["total_trades"],
                winning_trades      = metrics["winning_trades"],
                losing_trades       = metrics["losing_trades"],
                win_rate            = metrics["win_rate"],
                gross_profit        = metrics["gross_profit"],
                gross_loss          = metrics["gross_loss"],
                net_pnl             = metrics["net_pnl"],
                total_charges       = metrics["total_charges"],
                profit_factor       = metrics.get("profit_factor"),
                max_drawdown        = metrics["max_drawdown"],
                max_drawdown_abs    = metrics["max_drawdown_abs"],
                expectancy          = metrics["expectancy"],
                sharpe              = metrics.get("sharpe"),
                max_consecutive_losses = metrics["max_consecutive_losses"],
            )
            db.add(run)
            db.flush()   # get run.id before adding trades

            for t in trades:
                trade = BacktestTrade(
                    run_id            = run.id,
                    symbol            = t["symbol"],
                    security_id       = t["security_id"],
                    direction         = t["direction"],
                    entry_time        = t["entry_time"],
                    exit_time         = t.get("exit_time"),
                    entry_price       = t["entry_price"],
                    exit_price        = t.get("exit_price"),
                    quantity          = t["quantity"],
                    gross_pnl         = t["gross_pnl"],
                    charges           = t["charges"],
                    net_pnl           = t["net_pnl"],
                    slippage_entry    = t.get("slippage_entry", 0),
                    slippage_exit     = t.get("slippage_exit", 0),
                    entry_reason      = t.get("entry_reason"),
                    exit_reason       = t.get("exit_reason"),
                    stop_loss         = t.get("stop_loss"),
                    target            = t.get("target"),
                    opening_range_high = t.get("opening_range_high"),
                    opening_range_low  = t.get("opening_range_low"),
                )
                db.add(trade)

            db.commit()
            logger.info(f"Saved BacktestRun id={run.id} with {len(trades)} trades")
            return run.id
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to save backtest run: {e}")
            raise
        finally:
            db.close()
