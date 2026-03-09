"""
research/utils/fee_calculator.py

Configurable fee/charge computation for NSE equity intraday/delivery trades.
FeeConfig is passed into the backtest engine — never hardcoded.

Default assumptions (Dhan flat fee model):
  brokerage_per_order: Rs 20 flat per executed order (buy and sell separately)
  stt_sell_pct:        0.025% of turnover on sell side (intraday)
  exchange_pct:        0.00345% NSE transaction charge (both sides)
  sebi_pct:            0.0001% SEBI regulatory fee (both sides)
  gst_pct:             18% GST on (brokerage + exchange charge)
  stamp_pct:           0.003% stamp duty on buy side only

Usage:
  fee_config = FeeConfig()  # defaults
  result = calculate_charges(fee_config, side="buy", qty=100, price=2000.0)
  # result = {"brokerage": 20.0, "stt": 0.0, "exchange": 6.9, "sebi": 0.2,
  #           "gst": 4.72, "stamp": 6.0, "total": 31.82}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class FeeConfig:
    """
    All charge rates for a given broker/exchange setup.
    Pass this into BacktestEngine and calculate_charges().

    For Dhan intraday equity (default):
      - Rs 20 flat brokerage per order
      - STT 0.025% on sell side
    """
    brokerage_per_order: float = 20.0    # flat Rs per executed order
    stt_sell_pct:        float = 0.025   # STT on sell side (% of turnover)
    stt_buy_pct:         float = 0.0     # STT on buy side (0 for intraday equity)
    exchange_pct:        float = 0.00345 # NSE transaction charge (both sides)
    sebi_pct:            float = 0.0001  # SEBI regulatory fee (both sides)
    gst_pct:             float = 18.0    # GST on (brokerage + exchange charge)
    stamp_pct:           float = 0.003   # Stamp duty on buy side only


@dataclass
class SlippageConfig:
    """
    Market impact / execution slippage model.
    ticks: number of price ticks of slippage on entry and exit.
           For NSE equity, 1 tick = Rs 0.05.
    """
    ticks:     int   = 1       # 1 tick = Rs 0.05 slippage per share
    tick_size: float = 0.05    # NSE equity minimum price movement


def calculate_charges(
    fee_config: FeeConfig,
    side: Literal["buy", "sell"],
    qty: int,
    price: float,
) -> dict:
    """
    Calculate all-in charges for a single order.

    Returns itemised breakdown and total in Rs.
    """
    turnover = qty * price

    brokerage = fee_config.brokerage_per_order  # flat per order

    if side == "buy":
        stt = turnover * (fee_config.stt_buy_pct / 100)
        stamp = turnover * (fee_config.stamp_pct / 100)
    else:
        stt = turnover * (fee_config.stt_sell_pct / 100)
        stamp = 0.0  # stamp only on buy

    exchange = turnover * (fee_config.exchange_pct / 100)
    sebi     = turnover * (fee_config.sebi_pct     / 100)
    gst      = (brokerage + exchange) * (fee_config.gst_pct / 100)

    total = brokerage + stt + exchange + sebi + gst + stamp

    return {
        "brokerage": round(brokerage, 4),
        "stt":       round(stt,       4),
        "exchange":  round(exchange,  4),
        "sebi":      round(sebi,      4),
        "gst":       round(gst,       4),
        "stamp":     round(stamp,     4),
        "total":     round(total,     4),
        "turnover":  round(turnover,  4),
    }


def calculate_slippage(slippage_config: SlippageConfig, qty: int) -> float:
    """Return total Rs slippage for a single-side fill (qty × tick_value)."""
    tick_value = slippage_config.ticks * slippage_config.tick_size
    return round(qty * tick_value, 4)
