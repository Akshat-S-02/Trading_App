"""
app/strategies/adapters/momentum_orb_v4_adapter.py

Thin adapter over research/strategies/nifty_breakout.NiftyBreakoutStrategy.

Purpose:
  - Translates live aggregated candle format to the research strategy contract
  - Manages per-symbol strategy instances and session state
  - Bridges the research Signal dataclass → app Signal class for ExecutionEngine
  - Protects the live runtime from research API changes

The research strategy is the SINGLE SOURCE OF TRUTH for ORB logic.
This adapter NEVER modifies, overrides, or duplicates any strategy logic.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional

from research.strategies.nifty_breakout import (
    NiftyBreakoutConfig,
    NiftyBreakoutStrategy,
)
from research.strategies.base import Signal as ResearchSignal

# The app-side Signal (used by ExecutionEngine)
from app.engines.strategy_engine import Signal as AppSignal

logger = logging.getLogger("MomentumORBv4Adapter")


class MomentumORBv4Adapter:
    """
    Manages per-symbol ORB v4 strategy instances.

    Usage:
        adapter = MomentumORBv4Adapter(strategy_id=1)
        app_signal = adapter.on_candle("RELIANCE", candle_dict)
        if app_signal:
            execution_engine.process_signal(app_signal)
    """

    def __init__(
        self,
        strategy_id: int,
        config: NiftyBreakoutConfig | None = None,
    ):
        self.strategy_id = strategy_id
        self.config = config or NiftyBreakoutConfig()

        # Per-symbol strategy instances and history
        self._strategies: Dict[str, NiftyBreakoutStrategy] = {}
        self._histories: Dict[str, list[dict]] = {}
        self._last_dates: Dict[str, datetime] = {}
        self._last_candle_times: Dict[str, datetime] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_candle(self, symbol: str, candle: dict, allow_signal: bool = True) -> Optional[AppSignal]:
        """
        Process a completed 5-min candle for one symbol.

        Args:
            symbol: e.g. "RELIANCE"
            candle: dict with keys: timestamp (UTC datetime), open, high,
                    low, close, volume
            allow_signal: if False, updates strategy indicators but returns None
                          (used for safe historical gap healing).

        Returns:
            An app-side Signal if ORB breakout triggered, else None.
        """
        strategy = self._get_or_create(symbol)
        timestamp = candle["timestamp"]

        # Idempotency check: guard against duplicate candles for same symbol
        last_candle_time = self._last_candle_times.get(symbol)
        if last_candle_time is not None and timestamp <= last_candle_time:
            return None
        self._last_candle_times[symbol] = timestamp

        # Day-reset detection
        candle_date = timestamp.date() if hasattr(timestamp, 'date') else timestamp
        last_date = self._last_dates.get(symbol)
        if last_date is None or candle_date != last_date:
            strategy.on_day_start(timestamp, symbol)
            self._histories[symbol] = []
            self._last_dates[symbol] = candle_date
            # Clean up candle times from previous days to avoid unbounded growth
            self._last_candle_times.pop(symbol, None)
            logger.info(f"Day start for {symbol}: {candle_date}")

        # The research strategy expects lowercase keys
        bar = {
            "timestamp": timestamp,
            "open":      float(candle["open"]),
            "high":      float(candle["high"]),
            "low":       float(candle["low"]),
            "close":     float(candle["close"]),
            "volume":    int(candle.get("volume", 0)),
        }

        history = self._histories[symbol]

        # Call research strategy (no position tracking in paper yet → None)
        research_signal: Optional[ResearchSignal] = strategy.on_bar(
            bar=bar,
            history=history,
            position=None,
        )

        # Append to history AFTER strategy call (matches backtest order)
        history.append(bar)

        # Keep history bounded (last 100 bars ≈ 1 session)
        if len(history) > 100:
            history.pop(0)

        if research_signal is None or not allow_signal:
            return None

        # Translate research Signal → app Signal
        return self._translate(symbol, research_signal, timestamp)

    def reset(self) -> None:
        """Clear all state (e.g. on weekend/holiday reset)."""
        self._strategies.clear()
        self._histories.clear()
        self._last_dates.clear()

    @property
    def active_symbols(self) -> list[str]:
        return list(self._strategies.keys())

    @property
    def signals_emitted_today(self) -> int:
        """Count symbols that already triggered a trade today."""
        return sum(
            1 for s in self._strategies.values()
            if s._trade_done
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_or_create(self, symbol: str) -> NiftyBreakoutStrategy:
        if symbol not in self._strategies:
            self._strategies[symbol] = NiftyBreakoutStrategy(self.config)
            self._histories[symbol] = []
            logger.info(f"Created ORB v4 strategy instance for {symbol}")
        return self._strategies[symbol]

    def _translate(
        self,
        symbol: str,
        rs: ResearchSignal,
        timestamp: datetime,
    ) -> AppSignal:
        """Convert research.strategies.base.Signal → app.engines.strategy_engine.Signal"""
        app_signal = AppSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=rs.direction,
            entry_price=Decimal(str(rs.entry_price)),
            stop_loss=Decimal(str(rs.stop_loss)),
            timestamp=timestamp,
        )
        logger.info(
            f"ORB v4 signal for {symbol}: {rs.direction} "
            f"entry={rs.entry_price:.2f} sl={rs.stop_loss:.2f} "
            f"target={rs.target:.2f} reason={rs.entry_reason}"
        )
        return app_signal
