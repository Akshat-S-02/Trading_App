"""
research/strategies/nifty_breakout.py

NiftyBreakout Strategy — v4 (Long Only)

Two entry modes, configurable via `entry_mode`:

  "immediate"  : classic ORB — enter as soon as bar closes above OR high + buffer
  "retest"     : retest ORB — wait for breakout, then enter on pullback-and-hold

Retest logic (no lookahead — pure state-machine):
  1. Breakout detected  : close > OR_high × (1 + or_threshold_pct/100)
  2. Retest phase       : watch for any bar where low <= OR_high × (1 + retest_tolerance/100)
                          within the next `retest_window` bars
  3. Confirmation entry : if close > OR_high on the retest (or next) bar, enter

Filters (all optional, all default OFF to preserve v2 baseline):
  use_or_range_filter   : OR range must be < max_or_range_pct% of price
  use_gap_filter        : OR_high must be > previous session's close
  volume_filter_mode    : "avg_mult" | "max" | "ratio2"
  use_vwap_filter       : close > intraday VWAP

Version history:
  v1 : or=3, buf=0.10%, cutoff=13:30, immediate
  v2 : or=6, buf=0.25%, cutoff=11:00, immediate
  v3 : v2 + optional filters
  v4 : v3 + retest entry mode
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass
from datetime import datetime, time
from typing import Optional
import zoneinfo

from research.strategies.base import BaseStrategy, Signal

logger = logging.getLogger("NiftyBreakout")

_IST = zoneinfo.ZoneInfo("Asia/Kolkata")


@dataclass
class NiftyBreakoutConfig:
    # --- Entry mode ---
    entry_mode:             str   = "immediate"  # "immediate" or "retest"

    # --- Opening range ---
    or_candle_count:        int   = 6
    or_threshold_pct:       float = 0.25   # Close must be this % above OR high

    # --- Retest parameters (only used when entry_mode="retest") ---
    retest_tolerance_pct:   float = 0.10   # Pullback must reach within 0.10% of OR high
    retest_window:          int   = 5      # Give up on retest after N bars

    # --- Volume filter ---
    volume_filter_mode:     str   = "avg_mult"  # "avg_mult" | "max" | "ratio2"
    volume_multiplier:      float = 1.5
    volume_ratio_multiplier:float = 2.0
    volume_lookback:        int   = 10

    # --- Exit ---
    reward_ratio:           float = 1.5
    trail_atr_lookback:     int   = 14
    trail_atr_multiplier:   float = 0.5

    # --- Entry time gate ---
    no_entry_after_hour:    int   = 11
    no_entry_after_minute:  int   = 0

    # --- Professional filters ---
    use_vwap_filter:        bool  = False
    use_or_range_filter:    bool  = False
    max_or_range_pct:       float = 1.0
    use_gap_filter:         bool  = False


class NiftyBreakoutStrategy(BaseStrategy):
    """ORB v4 — supports both immediate and retest entry modes."""

    def __init__(self, config: NiftyBreakoutConfig | None = None):
        self.config = config or NiftyBreakoutConfig()

        # Daily state
        self._or_high:      Optional[float] = None
        self._or_low:       Optional[float] = None
        self._or_complete:  bool = False
        self._or_bars:      list[dict] = []
        self._trade_done:   bool = False

        # Retest state machine
        self._breakout_seen:       bool = False   # breakout bar detected
        self._retest_bars_waited:  int  = 0       # bars since breakout
        self._retest_triggered:    bool = False   # price pulled back to OR level
        self._breakout_volume_ok:  bool = False   # volume was ok on breakout bar
        self._breakout_bar:        Optional[dict] = None  # the original breakout bar

        # VWAP accumulators
        self._vwap_cum_tp_vol: float = 0.0
        self._vwap_cum_vol:    float = 0.0

        # Cross-day carry
        self._prev_day_close:  Optional[float] = None
        self._last_bar_close:  Optional[float] = None

    # ------------------------------------------------------------------
    # BaseStrategy hooks
    # ------------------------------------------------------------------

    def on_day_start(self, date: datetime, symbol: str) -> None:
        self._prev_day_close = self._last_bar_close
        self._or_high = self._or_low = None
        self._or_complete = self._trade_done = False
        self._or_bars = []
        self._breakout_seen = self._retest_triggered = False
        self._retest_bars_waited = 0
        self._breakout_volume_ok = False
        self._breakout_bar = None
        self._vwap_cum_tp_vol = self._vwap_cum_vol = 0.0

    def on_bar(
        self,
        bar: dict,
        history: list[dict],
        position: Optional[dict],
    ) -> Optional[Signal]:
        self._update_vwap(bar)
        self._last_bar_close = bar["close"]

        if position is not None or self._trade_done:
            return None

        bar_time_ist = bar["timestamp"].astimezone(_IST).time()

        # Phase 1: OR formation
        if not self._or_complete:
            self._or_bars.append(bar)
            if len(self._or_bars) >= self.config.or_candle_count:
                self._or_high = max(b["high"] for b in self._or_bars)
                self._or_low  = min(b["low"]  for b in self._or_bars)
                self._or_complete = True
            return None

        # Phase 2: time gate
        cutoff = time(self.config.no_entry_after_hour, self.config.no_entry_after_minute)
        if bar_time_ist >= cutoff:
            return None

        # Phase 3: OR range compression filter
        or_range_pct = (self._or_high - self._or_low) / bar["close"] * 100
        if self.config.use_or_range_filter and or_range_pct >= self.config.max_or_range_pct:
            return None

        # Volume check helper
        lookback = self.config.volume_lookback
        recent_vols = [b["volume"] for b in history[-lookback:] if b.get("volume", 0) > 0]

        if self.config.entry_mode == "retest":
            return self._retest_entry(bar, bar_time_ist, history, recent_vols, or_range_pct)
        else:
            return self._immediate_entry(bar, history, recent_vols, or_range_pct)

    # ------------------------------------------------------------------
    # Entry mode: immediate (classic ORB)
    # ------------------------------------------------------------------

    def _immediate_entry(
        self, bar: dict, history: list[dict],
        recent_vols: list[float], or_range_pct: float,
    ) -> Optional[Signal]:
        breakout_level = self._or_high * (1 + self.config.or_threshold_pct / 100)
        if bar["close"] <= breakout_level:
            return None
        if self.config.use_gap_filter and not self._gap_ok():
            return None
        current_vwap = self._get_vwap()
        if self.config.use_vwap_filter and current_vwap and bar["close"] <= current_vwap:
            return None
        if not self._check_volume(bar["volume"], recent_vols):
            return None
        return self._build_signal(bar, or_range_pct)

    # ------------------------------------------------------------------
    # Entry mode: retest ORB (state machine)
    # ------------------------------------------------------------------

    def _retest_entry(
        self, bar: dict, bar_time_ist: time,
        history: list[dict], recent_vols: list[float], or_range_pct: float,
    ) -> Optional[Signal]:

        breakout_level  = self._or_high * (1 + self.config.or_threshold_pct / 100)
        retest_level    = self._or_high * (1 + self.config.retest_tolerance_pct / 100)

        if not self._breakout_seen:
            # Waiting for initial breakout
            if bar["close"] > breakout_level:
                # Validate all non-time filters at breakout bar
                if self.config.use_gap_filter and not self._gap_ok():
                    return None
                current_vwap = self._get_vwap()
                if self.config.use_vwap_filter and current_vwap and bar["close"] <= current_vwap:
                    return None
                vol_ok = self._check_volume(bar["volume"], recent_vols)
                self._breakout_seen      = True
                self._retest_bars_waited = 0
                self._breakout_volume_ok = vol_ok
                self._breakout_bar       = bar
                logger.debug(
                    f"Breakout detected: close={bar['close']:.2f} > level={breakout_level:.2f} "
                    f"| vol_ok={vol_ok}"
                )
            return None

        # Breakout was seen — now watching for retest
        self._retest_bars_waited += 1

        # Retest window expired → abandon
        if self._retest_bars_waited > self.config.retest_window:
            logger.debug(f"Retest window expired after {self._retest_bars_waited} bars — reset")
            self._breakout_seen = False
            self._retest_triggered = False
            return None

        # Check if this bar touched the retest zone (low came back to OR high level)
        if not self._retest_triggered:
            if bar["low"] <= retest_level:
                self._retest_triggered = True
                logger.debug(
                    f"Retest triggered: low={bar['low']:.2f} <= retest_level={retest_level:.2f}"
                )

        # After retest triggered, wait for close back above OR high (confirmation)
        if self._retest_triggered:
            if bar["close"] > self._or_high:
                # Must still pass volume check (use breakout bar's volume status)
                if not self._breakout_volume_ok:
                    logger.debug("Retest confirmed but breakout volume insufficient — skip")
                    self._breakout_seen = self._retest_triggered = False
                    return None
                return self._build_signal(bar, or_range_pct)

        return None

    # ------------------------------------------------------------------
    # Signal builder
    # ------------------------------------------------------------------

    def _build_signal(self, bar: dict, or_range_pct: float) -> Optional[Signal]:
        entry_price = bar["close"]
        stop_loss   = self.get_stop_loss(entry_price, self._or_low)
        target      = self.get_target(entry_price, stop_loss)
        risk        = entry_price - stop_loss
        if risk <= 0:
            return None
        self._trade_done = True
        current_vwap = self._get_vwap()
        lookback = self.config.volume_lookback
        recent_vols = []  # meta only
        return Signal(
            direction    = "LONG",
            entry_price  = entry_price,
            stop_loss    = stop_loss,
            target       = target,
            quantity     = 0,
            entry_reason = f"{'retest' if self.config.entry_mode == 'retest' else 'breakout'}_entry",
            meta         = {
                "or_high":             self._or_high,
                "or_low":              self._or_low,
                "or_range_pct":        round(or_range_pct, 4),
                "entry_mode":          self.config.entry_mode,
                "prev_day_close":      self._prev_day_close,
                "vwap":                round(current_vwap, 2) if current_vwap else None,
                "volume_at_entry":     bar["volume"],
                "breakout_buffer_pct": self.config.or_threshold_pct,
            }
        )

    def get_stop_loss(self, entry_price: float, opening_range_low: float) -> float:
        return round(opening_range_low, 2)

    def get_target(self, entry_price: float, stop_loss: float) -> float:
        return round(entry_price + (entry_price - stop_loss) * self.config.reward_ratio, 2)

    # ------------------------------------------------------------------
    # Trailing stop
    # ------------------------------------------------------------------

    def get_trailing_stop(
        self, current_bar: dict, all_bars_since_entry: list[dict],
        entry_price: float, stop_loss: float, initial_risk: float,
    ) -> float:
        if current_bar["close"] - entry_price < initial_risk:
            return stop_loss
        atr = self._calculate_atr(all_bars_since_entry, self.config.trail_atr_lookback)
        return round(max(stop_loss, current_bar["close"] - atr * self.config.trail_atr_multiplier), 2)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _gap_ok(self) -> bool:
        if self._prev_day_close is None:
            return True  # first day — allow
        return self._or_high > self._prev_day_close

    def _update_vwap(self, bar: dict) -> None:
        tp  = (bar["high"] + bar["low"] + bar["close"]) / 3
        self._vwap_cum_tp_vol += tp * bar.get("volume", 0)
        self._vwap_cum_vol    += bar.get("volume", 0)

    def _get_vwap(self) -> Optional[float]:
        return self._vwap_cum_tp_vol / self._vwap_cum_vol if self._vwap_cum_vol else None

    def _check_volume(self, volume: int, recent_vols: list[float]) -> bool:
        if len(recent_vols) < 3:
            return True
        mode = self.config.volume_filter_mode
        if mode == "max":
            return volume > max(recent_vols)
        avg = statistics.mean(recent_vols)
        if mode == "ratio2":
            return volume >= self.config.volume_ratio_multiplier * avg
        return volume >= self.config.volume_multiplier * avg  # avg_mult

    def _calculate_atr(self, bars: list[dict], period: int) -> float:
        if len(bars) < 2:
            return bars[-1]["close"] * 0.005 if bars else 10.0
        trs = [max(bars[i]["high"] - bars[i]["low"],
                   abs(bars[i]["high"] - bars[i-1]["close"]),
                   abs(bars[i]["low"]  - bars[i-1]["close"]))
               for i in range(1, min(len(bars), period + 1))]
        return round(statistics.mean(trs), 4) if trs else 10.0

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def get_name(self) -> str: return "nifty_breakout"
    def get_version(self) -> str: return "v4"

    def get_params(self) -> dict:
        return {
            "entry_mode":             self.config.entry_mode,
            "or_candle_count":        self.config.or_candle_count,
            "or_threshold_pct":       self.config.or_threshold_pct,
            "retest_tolerance_pct":   self.config.retest_tolerance_pct,
            "retest_window":          self.config.retest_window,
            "volume_filter_mode":     self.config.volume_filter_mode,
            "volume_multiplier":      self.config.volume_multiplier,
            "volume_ratio_multiplier":self.config.volume_ratio_multiplier,
            "reward_ratio":           self.config.reward_ratio,
            "no_entry_after":         f"{self.config.no_entry_after_hour:02d}:{self.config.no_entry_after_minute:02d}",
            "use_or_range_filter":    self.config.use_or_range_filter,
            "max_or_range_pct":       self.config.max_or_range_pct,
            "use_gap_filter":         self.config.use_gap_filter,
            "use_vwap_filter":        self.config.use_vwap_filter,
        }
