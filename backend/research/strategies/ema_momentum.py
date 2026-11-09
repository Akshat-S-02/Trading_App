"""
research/strategies/ema_momentum.py

EMAMomentum Strategy — v1 (Long Only)
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass
from datetime import datetime, time
from typing import Optional
import zoneinfo

from research.strategies.base import BaseStrategy, Signal

logger = logging.getLogger("EMAMomentum")

_IST = zoneinfo.ZoneInfo("Asia/Kolkata")


@dataclass
class EMAMomentumConfig:
    ema_fast: int = 9
    ema_slow: int = 21
    volume_multiplier: float = 1.5
    volume_lookback: int = 10
    reward_ratio: float = 1.5
    no_entry_after_hour: int = 13
    no_entry_after_minute: int = 0


class EMAMomentumStrategy(BaseStrategy):
    """EMA crossover momentum strategy."""

    def __init__(self, config: EMAMomentumConfig | None = None):
        self.config = config or EMAMomentumConfig()

        # Daily state
        self._trade_done: bool = False
        self._bars_count: int = 0
        
        self._ema_fast_val: Optional[float] = None
        self._ema_slow_val: Optional[float] = None
        self._prev_ema_fast_val: Optional[float] = None
        self._prev_ema_slow_val: Optional[float] = None

    # ------------------------------------------------------------------
    # BaseStrategy hooks
    # ------------------------------------------------------------------

    def on_day_start(self, date: datetime, symbol: str) -> None:
        self._trade_done = False
        self._bars_count = 0
        self._ema_fast_val = None
        self._ema_slow_val = None
        self._prev_ema_fast_val = None
        self._prev_ema_slow_val = None

    def on_bar(
        self,
        bar: dict,
        history: list[dict],
        position: Optional[dict],
    ) -> Optional[Signal]:
        
        self._bars_count += 1
        close_price = bar["close"]
        
        # Calculate EMA incrementally
        k_fast = 2 / (self.config.ema_fast + 1)
        k_slow = 2 / (self.config.ema_slow + 1)
        
        if self._ema_fast_val is None:
            self._ema_fast_val = close_price
        else:
            self._prev_ema_fast_val = self._ema_fast_val
            self._ema_fast_val = close_price * k_fast + self._ema_fast_val * (1 - k_fast)
            
        if self._ema_slow_val is None:
            self._ema_slow_val = close_price
        else:
            self._prev_ema_slow_val = self._ema_slow_val
            self._ema_slow_val = close_price * k_slow + self._ema_slow_val * (1 - k_slow)

        if position is not None or self._trade_done:
            return None

        bar_time_ist = bar["timestamp"].astimezone(_IST).time()

        # Time gate
        cutoff = time(self.config.no_entry_after_hour, self.config.no_entry_after_minute)
        if bar_time_ist >= cutoff:
            return None

        # Minimum bars requirement
        if self._bars_count < max(self.config.ema_slow, 21):
            return None
            
        # We need previous EMAs to check for crossover
        if self._prev_ema_fast_val is None or self._prev_ema_slow_val is None:
            return None

        # Golden Cross check
        crossed_above = (self._prev_ema_fast_val <= self._prev_ema_slow_val) and (self._ema_fast_val > self._ema_slow_val)
        
        if not crossed_above:
            return None
            
        if close_price <= self._ema_slow_val:
            return None

        # Volume check
        lookback = self.config.volume_lookback
        recent_vols = [b["volume"] for b in history[-lookback:] if b.get("volume", 0) > 0]
        
        if len(recent_vols) >= 3:
            avg_volume = statistics.mean(recent_vols)
            if bar["volume"] <= avg_volume * self.config.volume_multiplier:
                return None

        # All criteria met, build signal
        # Stop loss is lowest low of last 3 bars
        recent_bars = history[-3:] if len(history) >= 3 else history
        recent_bars.append(bar) # Include current bar just in case
        stop_loss = min(b["low"] for b in recent_bars[-3:])
        
        if close_price - stop_loss <= 0:
            return None

        self._trade_done = True
        target = close_price + (close_price - stop_loss) * self.config.reward_ratio

        return Signal(
            direction    = "LONG",
            entry_price  = close_price,
            stop_loss    = stop_loss,
            target       = target,
            quantity     = 0,
            entry_reason = "ema_golden_cross",
            meta         = {
                "ema_fast_val": round(self._ema_fast_val, 2),
                "ema_slow_val": round(self._ema_slow_val, 2),
                "volume_at_entry": bar["volume"],
                "cross_type": "golden"
            }
        )

    # ------------------------------------------------------------------
    # Trailing stop
    # ------------------------------------------------------------------

    def get_trailing_stop(
        self, current_bar: dict, all_bars_since_entry: list[dict],
        entry_price: float, stop_loss: float, initial_risk: float,
    ) -> float:
        # Standard ORB-style behavior (fixed stop until Target hit) or simple trailing
        # Not explicitly specified, falling back to a fixed stop behavior
        return stop_loss

    # ------------------------------------------------------------------
    # Abstract methods from BaseStrategy
    # ------------------------------------------------------------------

    def get_stop_loss(self, entry_price: float, opening_range_low: float) -> float:
        if opening_range_low > 0:
            return round(opening_range_low, 2)
        return round(entry_price * 0.99, 2)

    def get_target(self, entry_price: float, stop_loss: float) -> float:
        return round(entry_price + (entry_price - stop_loss) * self.config.reward_ratio, 2)

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def get_name(self) -> str: return "ema_momentum"
    def get_version(self) -> str: return "v1"

    def get_params(self) -> dict:
        return {
            "ema_fast": self.config.ema_fast,
            "ema_slow": self.config.ema_slow,
            "volume_multiplier": self.config.volume_multiplier,
            "volume_lookback": self.config.volume_lookback,
            "reward_ratio": self.config.reward_ratio,
            "no_entry_after": f"{self.config.no_entry_after_hour:02d}:{self.config.no_entry_after_minute:02d}",
        }
