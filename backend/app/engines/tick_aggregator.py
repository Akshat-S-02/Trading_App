"""
app/engines/tick_aggregator.py

Standalone service that converts raw WebSocket ticks into strict 5-minute
OHLCV candles aligned to IST session buckets.

Rules (matching backtest behaviour):
  - Strict IST bucket alignment: 09:15, 09:20, 09:25, ...
  - Ignore ticks outside session (before 09:15, after 15:30)
  - Emit each candle exactly ONCE when its bucket closes
  - Skip empty candles (no synthetic flat bars)
  - Day reset at session open (09:15)
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone
from typing import Callable, Dict, Optional
import zoneinfo

logger = logging.getLogger("TickAggregator")

_IST = zoneinfo.ZoneInfo("Asia/Kolkata")

SESSION_START = time(9, 15)    # IST
SESSION_END   = time(15, 30)   # IST
BUCKET_MINUTES = 5


class _CandleBuilder:
    """Accumulates ticks into a single 5-min OHLCV bar."""

    __slots__ = ("open", "high", "low", "close", "volume", "tick_count")

    def __init__(self, price: float, volume: int = 0):
        self.open  = price
        self.high  = price
        self.low   = price
        self.close = price
        self.volume = volume
        self.tick_count = 1

    def update(self, price: float, volume: int = 0) -> None:
        self.high  = max(self.high, price)
        self.low   = min(self.low, price)
        self.close = price
        self.volume += volume
        self.tick_count += 1


class TickAggregator:
    """
    Feed ticks via on_tick().  When a 5-min bucket closes, the registered
    callback is invoked with a completed candle dict.

    Usage:
        agg = TickAggregator(on_candle=my_callback)
        agg.on_tick("RELIANCE", 2450.15, volume=100)
    """

    def __init__(self, on_candle: Callable[[str, dict], None]):
        """
        Args:
            on_candle: callback(symbol, candle_dict) called with each
                       completed 5-minute candle.
        """
        self._on_candle = on_candle

        # {symbol: _CandleBuilder}
        self._builders: Dict[str, _CandleBuilder] = {}

        # Current bucket start time (IST, minute-aligned)
        self._current_bucket: Optional[datetime] = None

        # Track session date for day-reset logic
        self._session_date: Optional[datetime] = None

        # Idempotency safeguards: guard against duplicate/out-of-order ticks
        self._last_tick_times: Dict[str, datetime] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_tick(
        self,
        symbol: str,
        price: float,
        volume: int = 0,
        tick_time: Optional[datetime] = None,
    ) -> None:
        """
        Process a single tick.  tick_time should be timezone-aware;
        if omitted, uses current IST time.
        """
        if tick_time is None:
            tick_time = datetime.now(_IST)
        elif tick_time.tzinfo is None:
            tick_time = tick_time.replace(tzinfo=_IST)
        else:
            tick_time = tick_time.astimezone(_IST)

        tick_t = tick_time.time()

        # Ignore ticks outside session hours
        if tick_t < SESSION_START or tick_t >= SESSION_END:
            return

        # Idempotency check: drop old or duplicate ticks
        last_tick = self._last_tick_times.get(symbol)
        if last_tick is not None and tick_time <= last_tick:
            return
        self._last_tick_times[symbol] = tick_time

        bucket_start = self._bucket_for(tick_time)

        # Day reset — new session
        session_date = self._session_date
        if session_date is None or tick_time.date() != session_date.date():
            self._flush_all(self._current_bucket)
            self._builders.clear()
            self._last_tick_times.clear()
            self._session_date = tick_time
            self._current_bucket = bucket_start
            logger.info(f"TickAggregator: new session {tick_time.date()}")

        # Bucket roll — new 5-min window
        curr_bucket = self._current_bucket
        if curr_bucket is not None and bucket_start > curr_bucket:
            self._flush_all(curr_bucket)
            self._builders.clear()
            self._current_bucket = bucket_start

        if self._current_bucket is None:
            self._current_bucket = bucket_start

        # Accumulate tick
        if symbol in self._builders:
            self._builders[symbol].update(price, volume)
        else:
            self._builders[symbol] = _CandleBuilder(price, volume)

    # ------------------------------------------------------------------
    # Status (for runner state endpoint)
    # ------------------------------------------------------------------

    @property
    def session_date(self) -> Optional[datetime]:
        return self._session_date

    @property
    def last_bucket(self) -> Optional[datetime]:
        return self._current_bucket

    @property
    def tracked_symbols(self) -> list[str]:
        return list(self._builders.keys())

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _bucket_for(dt: datetime) -> datetime:
        """Round down to nearest 5-minute bucket boundary."""
        minute = (dt.minute // BUCKET_MINUTES) * BUCKET_MINUTES
        return dt.replace(minute=minute, second=0, microsecond=0)

    def _flush_all(self, bucket_start: Optional[datetime]) -> None:
        """Emit completed candles for every symbol that had ticks."""
        if bucket_start is None:
            return

        # Convert bucket_start to UTC for the candle timestamp
        # (matching the backtest convention where timestamps are UTC)
        bucket_utc = bucket_start.astimezone(timezone.utc)

        for symbol, builder in self._builders.items():
            candle = {
                "timestamp": bucket_utc,
                "open":      builder.open,
                "high":      builder.high,
                "low":       builder.low,
                "close":     builder.close,
                "volume":    builder.volume,
            }
            try:
                self._on_candle(symbol, candle)
            except Exception:
                logger.exception(
                    f"TickAggregator: callback failed for {symbol} "
                    f"bucket={bucket_start.strftime('%H:%M')}"
                )
