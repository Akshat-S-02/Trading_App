"""
app/strategies/adapters/research_adapters.py

One adapter for every research strategy (research/strategies/*). It:
  - keeps one strategy instance + bar history per symbol
  - converts live 5-min candles to the research bar format
  - calls on_day_start on a new date and drops duplicate / out-of-order candles
  - turns a research Signal into the app Signal the ExecutionEngine takes
The research strategy stays the single source of truth for its logic.
"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional

from research.strategies.base import Signal as ResearchSignal
from app.engines.strategy_engine import Signal as AppSignal

logger = logging.getLogger("StrategyAdapter")

MAX_HISTORY = 100  # bars kept per symbol (~1 session of 5-min candles)


class ResearchStrategyAdapter:
    strategy_cls: type = None       # set by subclasses
    config_cls: type = None
    strategy_name: str = ""         # Order.strategy_name / weights key

    def __init__(self, strategy_id: int, config=None):
        self.strategy_id = strategy_id
        self.config = config or self.config_cls()
        self._strategies: Dict[str, object] = {}
        self._histories: Dict[str, list[dict]] = {}
        self._last_dates: Dict[str, object] = {}
        self._last_candle_times: Dict[str, datetime] = {}

    def on_candle(self, symbol: str, candle: dict, allow_signal: bool = True) -> Optional[AppSignal]:
        """
        Feed one completed candle (timestamp = UTC datetime, open/high/low/close/volume).
        allow_signal=False still updates the strategy's state but never returns a signal
        (gap healing, paused runner, regime not allowing this strategy).
        """
        strategy = self._get_or_create(symbol)
        timestamp = candle["timestamp"]

        last = self._last_candle_times.get(symbol)
        if last is not None and timestamp <= last:
            return None
        self._last_candle_times[symbol] = timestamp

        candle_date = timestamp.date() if hasattr(timestamp, "date") else timestamp
        if self._last_dates.get(symbol) != candle_date:
            strategy.on_day_start(timestamp, symbol)
            self._histories[symbol] = []
            self._last_dates[symbol] = candle_date
            logger.info(f"[{self.strategy_name}] Day start for {symbol}: {candle_date}")

        bar = {
            "timestamp": timestamp,
            "open": float(candle["open"]),
            "high": float(candle["high"]),
            "low": float(candle["low"]),
            "close": float(candle["close"]),
            "volume": int(candle.get("volume", 0)),
        }
        history = self._histories[symbol]
        research_signal: Optional[ResearchSignal] = strategy.on_bar(bar=bar, history=history, position=None)

        # Append AFTER the strategy call (matches backtest order)
        history.append(bar)
        if len(history) > MAX_HISTORY:
            history.pop(0)

        if research_signal is None or not allow_signal:
            return None
        return self._translate(symbol, research_signal, timestamp)

    def reset(self) -> None:
        self._strategies.clear()
        self._histories.clear()
        self._last_dates.clear()
        self._last_candle_times.clear()

    def _get_or_create(self, symbol: str):
        if symbol not in self._strategies:
            self._strategies[symbol] = self.strategy_cls(self.config)
            self._histories[symbol] = []
            logger.info(f"Created {self.strategy_name} strategy instance for {symbol}")
        return self._strategies[symbol]

    def _strategy_for(self, symbol: str):
        return self._strategies.get(symbol)

    def _translate(self, symbol: str, rs: ResearchSignal, timestamp: datetime) -> AppSignal:
        target = f"{rs.target:.2f}" if rs.target else "none"
        logger.info(
            f"{self.strategy_name} signal for {symbol}: {rs.direction} "
            f"entry={rs.entry_price:.2f} sl={rs.stop_loss:.2f} target={target} reason={rs.entry_reason}"
        )
        return AppSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=rs.direction,
            entry_price=Decimal(str(rs.entry_price)),
            stop_loss=Decimal(str(rs.stop_loss)),
            target_price=Decimal(str(rs.target)) if rs.target else None,
            timestamp=timestamp,
            strategy_name=self.strategy_name,
        )


# ── The four live strategies ──────────────────────────────────────────────────

from research.strategies.nifty_breakout import NiftyBreakoutConfig, NiftyBreakoutStrategy  # noqa: E402
from research.strategies.ema_momentum import EMAMomentumConfig, EMAMomentumStrategy  # noqa: E402
from research.strategies.vwap_reversion import VWAPReversionConfig, VWAPReversionStrategy  # noqa: E402
from research.strategies.supertrend import SupertrendConfig, SupertrendStrategy  # noqa: E402


class MomentumORBv4Adapter(ResearchStrategyAdapter):
    strategy_cls, config_cls, strategy_name = NiftyBreakoutStrategy, NiftyBreakoutConfig, "orb_v4"


class EMAMomentumAdapter(ResearchStrategyAdapter):
    strategy_cls, config_cls, strategy_name = EMAMomentumStrategy, EMAMomentumConfig, "ema_momentum"


class VWAPReversionAdapter(ResearchStrategyAdapter):
    strategy_cls, config_cls, strategy_name = VWAPReversionStrategy, VWAPReversionConfig, "vwap_reversion"


class SupertrendAdapter(ResearchStrategyAdapter):
    strategy_cls, config_cls, strategy_name = SupertrendStrategy, SupertrendConfig, "supertrend"
