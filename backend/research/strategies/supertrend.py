"""
research/strategies/supertrend.py

Supertrend ATR-based trend following strategy — v1
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass
from datetime import datetime, time
from typing import Optional
import zoneinfo

from research.strategies.base import BaseStrategy, Signal

logger = logging.getLogger("Supertrend")

_IST = zoneinfo.ZoneInfo("Asia/Kolkata")


@dataclass
class SupertrendConfig:
    atr_period: int = 10
    atr_multiplier: float = 3.0
    sma_period: int = 20
    volume_multiplier: float = 1.3
    volume_lookback: int = 10
    reward_ratio: float = 2.0
    no_entry_after_hour: int = 14
    no_entry_after_minute: int = 30


class SupertrendStrategy(BaseStrategy):
    """Supertrend ATR-based strategy."""

    def __init__(self, config: SupertrendConfig | None = None):
        self.config = config or SupertrendConfig()

        # Daily state
        self._trade_done: bool = False
        self._bars_count: int = 0
        
        self._prev_close: Optional[float] = None
        
        # ATR state
        self._tr_buffer: list[float] = []
        self._atr: Optional[float] = None
        
        # Supertrend state
        self._final_upperband: Optional[float] = None
        self._final_lowerband: Optional[float] = None
        self._trend_dir: int = 1  # 1 for bullish, -1 for bearish
        self._supertrend_line: Optional[float] = None
        
        # SMA state
        self._close_buffer: list[float] = []

    # ------------------------------------------------------------------
    # BaseStrategy hooks
    # ------------------------------------------------------------------

    def on_day_start(self, date: datetime, symbol: str) -> None:
        self._trade_done = False
        self._bars_count = 0
        
        self._prev_close = None
        
        self._tr_buffer.clear()
        self._atr = None
        
        self._final_upperband = None
        self._final_lowerband = None
        self._trend_dir = 1
        self._supertrend_line = None
        
        self._close_buffer.clear()

    def on_bar(
        self,
        bar: dict,
        history: list[dict],
        position: Optional[dict],
    ) -> Optional[Signal]:
        
        self._bars_count += 1
        close_price = bar["close"]
        high = bar["high"]
        low = bar["low"]
        
        self._close_buffer.append(close_price)
        if len(self._close_buffer) > self.config.sma_period:
            self._close_buffer.pop(0)
            
        sma20 = statistics.mean(self._close_buffer) if len(self._close_buffer) == self.config.sma_period else None

        # 1. Calculate True Range and ATR
        if self._prev_close is None:
            tr = high - low
        else:
            tr = max(high - low, abs(high - self._prev_close), abs(low - self._prev_close))
            
        self._prev_close = close_price
        
        if self._atr is None:
            self._tr_buffer.append(tr)
            if len(self._tr_buffer) == self.config.atr_period:
                self._atr = sum(self._tr_buffer) / self.config.atr_period
        else:
            # Wilder's Smoothing for ATR
            self._atr = (self._atr * (self.config.atr_period - 1) + tr) / self.config.atr_period
            
        # 2. Calculate Supertrend
        trend_flip = False
        if self._atr is not None:
            hl2 = (high + low) / 2.0
            basic_ub = hl2 + (self.config.atr_multiplier * self._atr)
            basic_lb = hl2 - (self.config.atr_multiplier * self._atr)
            
            if self._final_upperband is None:
                self._final_upperband = basic_ub
            else:
                if basic_ub < self._final_upperband or (history and history[-1]["close"] > self._final_upperband):
                    self._final_upperband = basic_ub
                    
            if self._final_lowerband is None:
                self._final_lowerband = basic_lb
            else:
                if basic_lb > self._final_lowerband or (history and history[-1]["close"] < self._final_lowerband):
                    self._final_lowerband = basic_lb
                    
            prev_trend_dir = self._trend_dir
            
            if self._trend_dir == 1 and close_price < self._final_lowerband:
                self._trend_dir = -1
                trend_flip = True
            elif self._trend_dir == -1 and close_price > self._final_upperband:
                self._trend_dir = 1
                trend_flip = True
                
            self._supertrend_line = self._final_lowerband if self._trend_dir == 1 else self._final_upperband

        # Exit early if not enough bars or position exists or already traded
        if position is not None or self._trade_done or self._bars_count < max(15, self.config.sma_period, self.config.atr_period):
            return None
            
        if self._supertrend_line is None or sma20 is None:
            return None

        # Time gate
        bar_time_ist = bar["timestamp"].astimezone(_IST).time()
        cutoff = time(self.config.no_entry_after_hour, self.config.no_entry_after_minute)
        if bar_time_ist >= cutoff:
            return None

        # Volume check
        lookback = self.config.volume_lookback
        recent_vols = [b["volume"] for b in history[-lookback:] if b.get("volume", 0) > 0]
        valid_volume = False
        if len(recent_vols) >= 3:
            avg_volume = statistics.mean(recent_vols)
            if bar.get("volume", 0) > avg_volume * self.config.volume_multiplier:
                valid_volume = True
                
        if not valid_volume:
            return None

        # Signal Logic
        if trend_flip:
            if self._trend_dir == 1 and close_price > sma20:
                self._trade_done = True
                stop_loss = self._supertrend_line
                risk = close_price - stop_loss
                if risk <= 0: return None
                
                target = close_price + (risk * self.config.reward_ratio)
                
                return Signal(
                    direction    = "LONG",
                    entry_price  = close_price,
                    stop_loss    = stop_loss,
                    target       = target,
                    quantity     = 0,
                    entry_reason = "supertrend_bullish_flip",
                    meta         = {
                        "supertrend_line": round(self._supertrend_line, 2),
                        "supertrend_direction": self._trend_dir,
                        "atr_value": round(self._atr, 2),
                        "sma20": round(sma20, 2),
                        "trend_flip": True
                    }
                )
                
            elif self._trend_dir == -1 and close_price < sma20:
                self._trade_done = True
                stop_loss = self._supertrend_line
                risk = stop_loss - close_price
                if risk <= 0: return None
                
                target = close_price - (risk * self.config.reward_ratio)
                
                return Signal(
                    direction    = "SHORT",
                    entry_price  = close_price,
                    stop_loss    = stop_loss,
                    target       = target,
                    quantity     = 0,
                    entry_reason = "supertrend_bearish_flip",
                    meta         = {
                        "supertrend_line": round(self._supertrend_line, 2),
                        "supertrend_direction": self._trend_dir,
                        "atr_value": round(self._atr, 2),
                        "sma20": round(sma20, 2),
                        "trend_flip": True
                    }
                )

        return None

    # ------------------------------------------------------------------
    # Trailing stop
    # ------------------------------------------------------------------

    def get_trailing_stop(
        self, current_bar: dict, all_bars_since_entry: list[dict],
        entry_price: float, stop_loss: float, initial_risk: float,
    ) -> float:
        # Dynamic support/resistance as requested:
        # "Stop loss: the current Supertrend line value at entry" -> actually, the user
        # specifically stated "current Supertrend line value at entry" which implies a fixed stop.
        # But usually supertrend trails with the line itself. 
        # For this base implementation we return the passed stop_loss (which is the entry time line).
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

    def get_name(self) -> str: return "supertrend"
    def get_version(self) -> str: return "v1"

    def get_params(self) -> dict:
        return {
            "atr_period": self.config.atr_period,
            "atr_multiplier": self.config.atr_multiplier,
            "sma_period": self.config.sma_period,
            "volume_multiplier": self.config.volume_multiplier,
            "volume_lookback": self.config.volume_lookback,
            "reward_ratio": self.config.reward_ratio,
            "no_entry_after": f"{self.config.no_entry_after_hour:02d}:{self.config.no_entry_after_minute:02d}",
        }
