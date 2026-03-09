"""
research/backtest/trade_exporter.py

Exports backtest trades to CSV for manual audit and strategy inspection.

Columns exported:
  symbol, date, entry_time, entry_reason,
  OR_high, OR_low, breakout_buffer_pct,
  entry_price, qty, stop, target,
  volume_at_entry, rolling_avg_volume,
  exit_time, exit_price, exit_reason,
  gross_pnl, charges, net_pnl, R_multiple

Usage:
  from research.backtest.trade_exporter import export_trades_csv
  export_trades_csv(result.trades, "backtest_export.csv")

  Or from CLI:
  python -m research.backtest.trade_exporter --run-id 1 --output trades_run1.csv
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from datetime import timezone
from pathlib import Path
from typing import Optional

import zoneinfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

logger = logging.getLogger("TradeExporter")

_IST = zoneinfo.ZoneInfo("Asia/Kolkata")


# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------

COLUMNS = [
    "symbol",
    "date",               # trading date (IST) YYYY-MM-DD
    "entry_time",         # HH:MM IST
    "entry_reason",
    "OR_high",
    "OR_low",
    "breakout_buffer_pct",
    "entry_price",
    "qty",
    "stop",
    "target",
    "volume_at_entry",
    "rolling_avg_volume",
    "exit_time",          # HH:MM IST
    "exit_price",
    "exit_reason",
    "gross_pnl",
    "charges",
    "net_pnl",
    "R_multiple",         # net_pnl / (entry_price - stop) / qty — how many R did we actually get
]


def _compute_r_multiple(trade: dict) -> Optional[float]:
    """R_multiple = net_pnl / (risk_per_share × qty)."""
    try:
        risk_per_share = float(trade["entry_price"]) - float(trade["stop_loss"])
        qty = int(trade["quantity"])
        if risk_per_share <= 0 or qty <= 0:
            return None
        one_r = risk_per_share * qty
        return round(float(trade["net_pnl"]) / one_r, 3)
    except (KeyError, TypeError, ZeroDivisionError):
        return None


def _fmt_ist_time(ts) -> str:
    """Format a UTC-aware datetime as HH:MM IST."""
    if ts is None:
        return ""
    try:
        return ts.astimezone(_IST).strftime("%H:%M")
    except Exception:
        return str(ts)


def _fmt_ist_date(ts) -> str:
    """Format a UTC-aware datetime as YYYY-MM-DD IST date."""
    if ts is None:
        return ""
    try:
        return ts.astimezone(_IST).strftime("%Y-%m-%d")
    except Exception:
        return str(ts)


def _trade_to_row(trade: dict) -> dict:
    """Convert a trade dict to a CSV row dict."""
    r = _compute_r_multiple(trade)
    return {
        "symbol":             trade.get("symbol", ""),
        "date":               _fmt_ist_date(trade.get("entry_time")),
        "entry_time":         _fmt_ist_time(trade.get("entry_time")),
        "entry_reason":       trade.get("entry_reason", ""),
        "OR_high":            trade.get("opening_range_high", ""),
        "OR_low":             trade.get("opening_range_low", ""),
        "breakout_buffer_pct": trade.get("breakout_buffer_pct", ""),
        "entry_price":        trade.get("entry_price", ""),
        "qty":                trade.get("quantity", ""),
        "stop":               trade.get("stop_loss", ""),
        "target":             trade.get("target", ""),
        "volume_at_entry":    trade.get("volume_at_entry", ""),
        "rolling_avg_volume": trade.get("rolling_avg_volume", ""),
        "exit_time":          _fmt_ist_time(trade.get("exit_time")),
        "exit_price":         trade.get("exit_price", ""),
        "exit_reason":        trade.get("exit_reason", ""),
        "gross_pnl":          trade.get("gross_pnl", ""),
        "charges":            trade.get("charges", ""),
        "net_pnl":            trade.get("net_pnl", ""),
        "R_multiple":         r if r is not None else "",
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def export_trades_csv(trades: list[dict], output_path: str) -> str:
    """
    Write a list of trade dicts to a CSV file.
    Returns the absolute path of the written file.
    """
    if not trades:
        logger.warning("No trades to export — CSV not created")
        return ""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for trade in trades:
            writer.writerow(_trade_to_row(trade))

    logger.info(f"Exported {len(trades)} trades to {path.resolve()}")
    print(f"\n[OK] Exported {len(trades)} trades -> {path.resolve()}")
    return str(path.resolve())


def export_from_db(run_id: int, output_path: str) -> str:
    """
    Load trades from research.db for a given BacktestRun.id and export to CSV.
    """
    from research.db import init_db, SessionLocal
    from research.data.models import BacktestTrade

    init_db()
    db = SessionLocal()
    try:
        rows = db.query(BacktestTrade).filter(BacktestTrade.run_id == run_id).all()
        if not rows:
            print(f"No trades found for run_id={run_id}")
            return ""

        trades = [
            {
                "symbol":              r.symbol,
                "entry_time":          r.entry_time,
                "entry_reason":        r.entry_reason,
                "opening_range_high":  float(r.opening_range_high) if r.opening_range_high else None,
                "opening_range_low":   float(r.opening_range_low)  if r.opening_range_low  else None,
                "breakout_buffer_pct": None,   # not stored in DB — captured from meta only
                "entry_price":         float(r.entry_price),
                "quantity":            r.quantity,
                "stop_loss":           float(r.stop_loss) if r.stop_loss else None,
                "target":              float(r.target) if r.target else None,
                "volume_at_entry":     None,   # not stored in DB separately
                "rolling_avg_volume":  None,
                "exit_time":           r.exit_time,
                "exit_price":          float(r.exit_price) if r.exit_price else None,
                "exit_reason":         r.exit_reason,
                "gross_pnl":           float(r.gross_pnl),
                "charges":             float(r.charges),
                "net_pnl":             float(r.net_pnl),
            }
            for r in rows
        ]
        return export_trades_csv(trades, output_path)
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export backtest trades to CSV")
    parser.add_argument("--run-id", type=int, required=True, help="BacktestRun ID from research.db")
    parser.add_argument("--output", default="trades_export.csv", help="Output CSV path")
    args = parser.parse_args()

    export_from_db(run_id=args.run_id, output_path=args.output)
