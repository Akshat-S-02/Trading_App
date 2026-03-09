"""
research/strategies/base.py

Abstract base class for all research strategies.

NO-LOOKAHEAD CONTRACT (strictly enforced):
  on_bar() is called exactly once per bar, in chronological order.
  The strategy may only access: the current bar + all prior bars this session + the current open position.
  Future bars are NEVER passed in. Any lookahead = invalid backtest.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional


@dataclass
class Signal:
    """Represents a trade signal from a strategy on_bar() call."""
    direction:    Literal["LONG", "SHORT"]
    entry_price:  float
    stop_loss:    float
    target:       float
    quantity:     int
    entry_reason: str = "signal"
    meta:         dict = field(default_factory=dict)


class BaseStrategy(ABC):
    """
    NO-LOOKAHEAD CONTRACT:
    on_bar() is called exactly once per bar, in chronological order.
    The strategy may only access: bars seen so far + current open position.
    Future bars are NEVER passed in. Violation = invalid backtest.

    Implement:
      - on_bar()      : called for every bar; return Signal or None
      - on_day_start(): called once at start of each trading day (optional)
      - on_day_end()  : called once at end of each trading day (optional)
    """

    @abstractmethod
    def on_bar(
        self,
        bar: dict,              # current bar OHLCV (read-only, UTC timestamp)
        history: list[dict],    # all prior bars this trading session (read-only)
        position: Optional[dict],  # current open position dict, or None
    ) -> Optional[Signal]:
        """
        Process one bar. Return a Signal to open a trade, or None to do nothing.
        If a position is already open, return None (no pyramiding in base design).
        """
        ...

    @abstractmethod
    def get_stop_loss(self, entry_price: float, opening_range_low: float) -> float:
        """Return the stop loss price for a long entry."""
        ...

    @abstractmethod
    def get_target(self, entry_price: float, stop_loss: float) -> float:
        """Return the take-profit target price given entry and stop."""
        ...

    def on_day_start(self, date: datetime, symbol: str) -> None:
        """Called at the start of each trading day. Override to reset daily state."""
        pass

    def on_day_end(self, date: datetime, symbol: str, position: Optional[dict]) -> None:
        """Called at end of each trading day (before EOD squareoff). Override if needed."""
        pass

    def get_name(self) -> str:
        return self.__class__.__name__

    def get_version(self) -> str:
        return "v1"

    def get_params(self) -> dict:
        """Return strategy parameters as a dict, for config snapshot storage."""
        return {}
