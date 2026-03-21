"""
app/routes/paper.py

API endpoints for the Paper Strategy Runner.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import cast, Date
import zoneinfo
from datetime import datetime

from app.engines.paper_strategy_runner import get_runner
from app.db import get_db
import app.models as models

router = APIRouter(prefix="/api/paper", tags=["paper"])

_IST = zoneinfo.ZoneInfo("Asia/Kolkata")

@router.get("/metrics")
def paper_metrics(db: Session = Depends(get_db)):
    """
    Calculates system-level validation metrics from today's paper fills.
    - Total paper trades
    - Average slippage ticks
    - Average fill latency
    - Running Profit Factor (simplified)
    """
    today = datetime.now(_IST).date()

    # Get all TradeFills for today
    # Because SQLite JSON querying can be tricky, we fetch and aggregate in Python
    # for this diagnostic endpoint.
    fills = (
        db.query(models.TradeFill)
        # Using a date cast on the timezone-aware timestamp
        .filter(cast(models.TradeFill.timestamp, Date) == today)
        .all()
    )

    paper_fills = [f for f in fills if f.paper_meta is not None]

    if not paper_fills:
        return {
            "total_trades": 0,
            "avg_slippage_ticks": 0.0,
            "avg_latency_ms": 0.0,
            "fill_deviation_pct": 0.0,
            "notes": "No paper fills today"
        }

    total_slippage: float = 0.0
    total_latency: float = 0.0
    total_deviation: float = 0.0

    for f in paper_fills:
        meta = f.paper_meta or {}
        
        ticks = meta.get("slippage_ticks")
        if ticks is not None:
            total_slippage = total_slippage + abs(float(ticks))
            
        latency = meta.get("latency_ms")
        if latency is not None:
            total_latency = total_latency + float(latency)

        # fill deviation: abs(fill_price - signal_price) / signal_price
        signal_price = meta.get("signal_price")
        if signal_price is not None and float(signal_price) > 0:
            dev = abs(float(f.price) - float(signal_price)) / float(signal_price)
            total_deviation = total_deviation + float(dev)

    count = len(paper_fills)
    avg_slippage = total_slippage / count
    avg_latency = total_latency / count
    avg_deviation = (total_deviation / count) * 100.0

    return {
        "date": today.isoformat(),
        "total_trades": count,
        "avg_slippage_ticks": float(round(avg_slippage, 2)),
        "avg_latency_ms": float(round(avg_latency, 2)),
        "fill_deviation_pct": float(round(avg_deviation, 4)),
    }


@router.get("/status")
def paper_status():
    """
    Returns current state of the paper strategy runner:
      runner_enabled, runner_paused, symbols_tracked,
      current_session_date, last_completed_candle_time,
      signals_emitted_today, candles_processed, ticks_received
    """
    runner = get_runner()
    return runner.get_status()


@router.post("/start")
def paper_start():
    runner = get_runner()
    runner.start()
    return {"status": "started"}


@router.post("/pause")
def paper_pause():
    runner = get_runner()
    runner.pause()
    return {"status": "paused"}


@router.post("/resume")
def paper_resume():
    runner = get_runner()
    runner.resume()
    return {"status": "resumed"}


@router.post("/stop")
def paper_stop():
    runner = get_runner()
    runner.stop()
    return {"status": "stopped"}
