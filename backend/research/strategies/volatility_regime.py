"""
research/strategies/volatility_regime.py

ATR-based market regime classifier and strategy router.
"""

from enum import Enum
from typing import Optional


class VolatilityRegime(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RegimeClassifier:
    """Classifies market regime based on ATR and SMA."""

    STRATEGY_MATRIX = {
        (VolatilityRegime.LOW, "UPTREND"): ["ema_momentum", "vwap_reversion"],
        (VolatilityRegime.MEDIUM, "UPTREND"): ["orb_v4", "ema_momentum", "supertrend"],
        (VolatilityRegime.HIGH, "UPTREND"): ["orb_v4", "supertrend"],
        (VolatilityRegime.LOW, "DOWNTREND"): ["vwap_reversion"],
        (VolatilityRegime.MEDIUM, "DOWNTREND"): ["orb_v4", "vwap_reversion", "supertrend"],
        (VolatilityRegime.HIGH, "DOWNTREND"): ["supertrend"],
    }

    @classmethod
    def classify(cls, bars: list[dict]) -> Optional[dict]:
        """
        Classifies the current market regime based on the provided bars.
        Requires at least 20 bars.
        """
        if len(bars) < 20:
            return None

        # --- Trend Calculation (SMA20) ---
        recent_20 = bars[-20:]
        sma20 = sum(b["close"] for b in recent_20) / 20.0
        
        current_close = bars[-1]["close"]
        trend = "UPTREND" if current_close > sma20 else "DOWNTREND"

        # --- Volatility Calculation (ATR14) ---
        trs = []
        # Calculate TR for the last 14 bars
        for i in range(len(bars) - 14, len(bars)):
            curr = bars[i]
            prev = bars[i - 1]
            tr = max(
                curr["high"] - curr["low"],
                abs(curr["high"] - prev["close"]),
                abs(curr["low"] - prev["close"])
            )
            trs.append(tr)

        atr = sum(trs) / 14.0
        atr_pct = atr / current_close

        # --- Regime Classification ---
        if atr_pct < 0.0008:
            regime = VolatilityRegime.LOW
        elif atr_pct < 0.0020:
            regime = VolatilityRegime.MEDIUM
        else:
            regime = VolatilityRegime.HIGH

        allowed_strategies = cls.STRATEGY_MATRIX.get((regime, trend), [])

        return {
            "regime": regime,
            "trend": trend,
            "atr": atr,
            "atr_pct": atr_pct,
            "sma20": sma20,
            "allowed_strategies": allowed_strategies,
        }
