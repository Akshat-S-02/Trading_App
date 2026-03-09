"""
research/jobs/daily_sync_job.py

Incremental candle sync — fetches only the candles added since the last
stored timestamp. Meant to run after market close (15:45 IST onwards).

Usage:
  cd backend
  python -m research.jobs.daily_sync_job
  python -m research.jobs.daily_sync_job --timeframe 5m
  python -m research.jobs.daily_sync_job --timeframe 1d --symbols RELIANCE TCS
"""

from __future__ import annotations

import argparse
import logging
import sys
import os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from research.db import init_db, SessionLocal
from research.data.models import IngestionJob, IngestionJobStatus
from research.data.instrument_repository import get_nifty50_instruments, get_instrument
from research.data.candle_repository import upsert_candles, get_latest_timestamp
from research.services.historical_data_service import fetch_daily, fetch_intraday

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("DailySyncJob")

_UTC = timezone.utc


def run_sync(timeframe: str = "5m", symbols: list[str] | None = None):
    """
    For each symbol in the NIFTY 50 universe:
      1. Look up the latest stored timestamp from research.db
      2. Fetch candles from that point to now
      3. Upsert any new rows
    """
    init_db()
    db = SessionLocal()

    now = datetime.now(_UTC)

    all_instruments = get_nifty50_instruments()
    if symbols:
        instruments = [get_instrument(s) for s in symbols if get_instrument(s)]
    else:
        instruments = all_instruments

    logger.info(f"Daily sync: {len(instruments)} symbols | timeframe={timeframe} | up to {now.strftime('%Y-%m-%d %H:%M UTC')}")

    total_inserted = 0

    for inst in instruments:
        symbol      = inst["symbol"]
        security_id = inst["security_id"]
        exchange    = inst["exchange_segment"]
        instr_type  = inst["instrument"]

        latest = get_latest_timestamp(security_id, timeframe)
        if latest:
            sync_from = latest + timedelta(minutes=1)
            logger.info(f"  {symbol}: syncing from {sync_from.strftime('%Y-%m-%d %H:%M UTC')}")
        else:
            # No data at all — fetch last 7 days as a bootstrap
            sync_from = now - timedelta(days=7)
            logger.info(f"  {symbol}: no prior data, bootstrapping last 7 days")

        if sync_from >= now:
            logger.info(f"  {symbol}: already up to date")
            continue

        from_str = sync_from.strftime("%Y-%m-%d")
        to_str   = now.strftime("%Y-%m-%d")

        try:
            if timeframe == "1d":
                candles = fetch_daily(
                    security_id=security_id,
                    symbol=symbol,
                    from_date=sync_from,
                    to_date=now,
                    exchange_segment=exchange,
                    instrument=instr_type,
                )
            else:
                interval_min = int(timeframe.replace("m", ""))
                candles = fetch_intraday(
                    security_id=security_id,
                    symbol=symbol,
                    interval_minutes=interval_min,
                    from_date=sync_from,
                    to_date=now,
                    exchange_segment=exchange,
                    instrument=instr_type,
                )

            inserted = upsert_candles(candles)
            total_inserted += inserted

            job = IngestionJob(
                security_id=security_id, symbol=symbol,
                timeframe=timeframe, from_date=from_str, to_date=to_str,
                status=IngestionJobStatus.DONE,
                rows_inserted=inserted,
                finished_at=datetime.now(_UTC),
            )
            db.add(job)
            db.commit()
            logger.info(f"  {symbol}: ✅ {inserted} new rows")

        except Exception as e:
            db.rollback()
            job = IngestionJob(
                security_id=security_id, symbol=symbol,
                timeframe=timeframe, from_date=from_str, to_date=to_str,
                status=IngestionJobStatus.FAILED,
                error_message=str(e),
                finished_at=datetime.now(_UTC),
            )
            db.add(job)
            db.commit()
            logger.error(f"  {symbol}: ❌ {e}")

    db.close()
    logger.info(f"\nSync complete. Total new rows inserted: {total_inserted}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Incremental daily candle sync for NIFTY 50")
    parser.add_argument("--timeframe", default="5m",
                        choices=["1m", "5m", "15m", "25m", "60m", "1d"])
    parser.add_argument("--symbols", nargs="*",
                        help="Optional: limit to specific symbols")
    args = parser.parse_args()

    run_sync(timeframe=args.timeframe, symbols=args.symbols)
