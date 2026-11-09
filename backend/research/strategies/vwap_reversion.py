"""
research/strategies/vwap_reversion.py

VWAP Mean Reversion Strategy — v1 (Long and Short)
"""

from __future__ import annotations

import logging
import statistics
import math
from dataclasses import dataclass
from datetime import datetime, time
from typing import Optional
import zoneinfo

from research.strategies.base import BaseStrategy, Signal

logger = logging.getLogger("VWAPReversion")

_IST = zoneinfo.ZoneInfo("Asia/Kolkata")


@dataclass
class VWAPReversionConfig:
    vwap_band_multiplier_entry: float = 1.5
    vwap_band_multiplier_stop: float = 2.0
    rsi_period: int = 14
    rsi_oversold: float = 35
    rsi_overbought: float = 65
    volume_multiplier: float = 1.2
    volume_lookback: int = 10
    entry_start_hour: int = 10
    entry_end_hour: int = 14
    reward_ratio: float = 1.0


class VWAPReversionStrategy(BaseStrategy):
    """VWAP mean reversion strategy using RSI and VWAP bands."""

    def __init__(self, config: VWAPReversionConfig | None = None):
        self.config = config or VWAPReversionConfig()

        # Daily state
        self._long_done: bool = False
        self._short_done: bool = False
        self._bars_count: int = 0
        
        self._cumulative_typ_price_vol: float = 0.0
        self._cumulative_vol: float = 0.0
        
        self._avg_gain: float = 0.0
        self._avg_loss: float = 0.0
        self._prev_close: Optional[float] = None
        self._gains_buffer: list[float] = []
        self._losses_buffer: list[float] = []
        
        self._typical_prices: list[float] = []

    # ------------------------------------------------------------------
    # BaseStrategy hooks
    # ------------------------------------------------------------------

    def on_day_start(self, date: datetime, symbol: str) -> None:
        self._long_done = False
        self._short_done = False
        self._bars_count = 0
        
        self._cumulative_typ_price_vol = 0.0
        self._cumulative_vol = 0.0
        
        self._avg_gain = 0.0
        self._avg_loss = 0.0
        self._prev_close = None
        self._gains_buffer.clear()
        self._losses_buffer.clear()
        self._typical_prices.clear()

    def on_bar(
        self,
        bar: dict,
        history: list[dict],
        position: Optional[dict],
    ) -> Optional[Signal]:
        
        self._bars_count += 1
        close_price = bar["close"]
        high_price = bar["high"]
        low_price = bar["low"]
        vol = bar.get("volume", 0)
        
        typical_price = (high_price + low_price + close_price) / 3.0
        
        # 1. VWAP Update
        self._cumulative_typ_price_vol += (typical_price * vol)
        self._cumulative_vol += vol
        
        vwap = self._cumulative_typ_price_vol / self._cumulative_vol if self._cumulative_vol > 0 else typical_price
        
        self._typical_prices.append(typical_price)
        if len(self._typical_prices) > 20:
            self._typical_prices.pop(0)
            
        # VWAP standard deviation using 20 bar rolling window
        vwap_std = 0.0
        if len(self._typical_prices) == 20:
            deviations = [(tp - vwap) ** 2 for tp in self._typical_prices]
            vwap_std = math.sqrt(sum(deviations) / len(deviations))
            
            # Floor standard deviation to prevent band compression to near-zero on ultra-low-volatility days
            min_std = vwap * 0.0003
            vwap_std = max(vwap_std, min_std)
            
        # 2. RSI Update (Wilder Smoothing)
        rsi = 50.0
        if self._prev_close is not None:
            change = close_price - self._prev_close
            gain = max(change, 0)
            loss = abs(min(change, 0))
            
            if self._bars_count <= self.config.rsi_period:
                self._gains_buffer.append(gain)
                self._losses_buffer.append(loss)
                if self._bars_count == self.config.rsi_period:
                    self._avg_gain = sum(self._gains_buffer) / self.config.rsi_period
                    self._avg_loss = sum(self._losses_buffer) / self.config.rsi_period
            else:
                self._avg_gain = (self._avg_gain * (self.config.rsi_period - 1) + gain) / self.config.rsi_period
                self._avg_loss = (self._avg_loss * (self.config.rsi_period - 1) + loss) / self.config.rsi_period
                
            if self._avg_loss == 0:
                rsi = 100.0 if self._avg_gain > 0 else 50.0
            else:
                rs = self._avg_gain / self._avg_loss
                rsi = 100.0 - (100.0 / (1.0 + rs))
                
        prev_high = self._prev_close if self._bars_count == 1 else (history[-1]["high"] if history else high_price)
        prev_low = self._prev_close if self._bars_count == 1 else (history[-1]["low"] if history else low_price)
        self._prev_close = close_price

        # Exit early if not enough bars or position exists
        if position is not None or self._bars_count < max(20, self.config.rsi_period):
            return None

        # Time gate
        bar_time_ist = bar["timestamp"].astimezone(_IST).time()
        start_time = time(self.config.entry_start_hour, 0)
        end_time = time(self.config.entry_end_hour, 0)
        if bar_time_ist < start_time or bar_time_ist > end_time:
            return None

        # Volume check
        lookback = self.config.volume_lookback
        recent_vols = [b["volume"] for b in history[-lookback:] if b.get("volume", 0) > 0]
        valid_volume = False
        if len(recent_vols) >= 3:
            avg_volume = statistics.mean(recent_vols)
            if vol > avg_volume * self.config.volume_multiplier:
                valid_volume = True
                
        if not valid_volume:
            return None
            
        if vwap_std == 0:
            return None
            
        upper_band_entry = vwap + (vwap_std * self.config.vwap_band_multiplier_entry)
        lower_band_entry = vwap - (vwap_std * self.config.vwap_band_multiplier_entry)
        
        upper_band_stop = vwap + (vwap_std * self.config.vwap_band_multiplier_stop)
        lower_band_stop = vwap - (vwap_std * self.config.vwap_band_multiplier_stop)
        
        deviation_pct = ((close_price - vwap) / vwap) * 100.0

        # LONG Entry Logic
        if not self._long_done:
            if close_price < lower_band_entry and rsi < self.config.rsi_oversold:
                if close_price > prev_low:
                    self._long_done = True
                    return Signal(
                        direction    = "LONG",
                        entry_price  = close_price,
                        stop_loss    = lower_band_stop,
                        target       = vwap,
                        quantity     = 0,
                        entry_reason = "vwap_oversold_bounce",
                        meta         = {
                            "vwap": round(vwap, 2),
                            "upper_band": round(upper_band_entry, 2),
                            "lower_band": round(lower_band_entry, 2),
                            "rsi": round(rsi, 2),
                            "deviation_pct": round(deviation_pct, 4),
                            "entry_side": "LONG"
                        }
                    )

        # SHORT Entry Logic
        if not self._short_done:
            if close_price > upper_band_entry and rsi > self.config.rsi_overbought:
                if close_price < prev_high:
                    self._short_done = True
                    return Signal(
                        direction    = "SHORT",
                        entry_price  = close_price,
                        stop_loss    = upper_band_stop,
                        target       = vwap,
                        quantity     = 0,
                        entry_reason = "vwap_overbought_rejection",
                        meta         = {
                            "vwap": round(vwap, 2),
                            "upper_band": round(upper_band_entry, 2),
                            "lower_band": round(lower_band_entry, 2),
                            "rsi": round(rsi, 2),
                            "deviation_pct": round(deviation_pct, 4),
                            "entry_side": "SHORT"
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

    def get_name(self) -> str: return "vwap_reversion"
    def get_version(self) -> str: return "v1"

    def get_params(self) -> dict:
        return {
            "vwap_band_multiplier_entry": self.config.vwap_band_multiplier_entry,
            "vwap_band_multiplier_stop": self.config.vwap_band_multiplier_stop,
            "rsi_period": self.config.rsi_period,
            "volume_multiplier": self.config.volume_multiplier,
            "volume_lookback": self.config.volume_lookback,
            "reward_ratio": self.config.reward_ratio,
            "time_window": f"{self.config.entry_start_hour}:00 - {self.config.entry_end_hour}:00",
        }
