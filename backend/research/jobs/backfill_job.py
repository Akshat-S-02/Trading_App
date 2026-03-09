"""
research/jobs/backfill_job.py

One-time historical data loader for the NIFTY 50 universe.
Resumable: skips any (symbol, timeframe, date_chunk) already marked DONE
in the ingestion_jobs table.

Usage:
  cd backend
  python -m research.jobs.backfill_job --timeframe 5m --years 2
  python -m research.jobs.backfill_job --timeframe 1d --years 10
  python -m research.jobs.backfill_job --timeframe 5m --years 1 --symbols RELIANCE TCS HDFCBANK

Options:
  --timeframe   5m | 1m | 15m | 25m | 60m | 1d   (default: 5m)
  --years       how many years of history to backfill (default: 2)
  --symbols     limit to specific symbols (default: all NIFTY 50)
"""

from __future__ import annotations

import argparse
import logging
import sys
import os
from datetime import datetime, timedelta, timezone

# Ensure backend/ is on the Python path when run with python -m
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
logger = logging.getLogger("BackfillJob")

_UTC = timezone.utc


def _is_chunk_done(db, security_id: str, timeframe: str, from_date: str, to_date: str) -> bool:
    """Return True if this exact chunk was already successfully ingested."""
    row = db.query(IngestionJob).filter(
        IngestionJob.security_id == security_id,
        IngestionJob.timeframe   == timeframe,
        IngestionJob.from_date   == from_date,
        IngestionJob.to_date     == to_date,
        IngestionJob.status      == IngestionJobStatus.DONE,
    ).first()
    return row is not None


def _log_job(db, security_id: str, symbol: str, timeframe: str,
             from_date: str, to_date: str, status: str,
             rows_inserted: int = 0, error: str = None):
    job = IngestionJob(
        security_id   = security_id,
        symbol        = symbol,
        timeframe     = timeframe,
        from_date     = from_date,
        to_date       = to_date,
        status        = status,
        rows_inserted = rows_inserted,
        error_message = error,
        finished_at   = datetime.now(_UTC),
    )
    db.add(job)
    db.commit()


def _chunk_date_range(from_dt: datetime, to_dt: datetime, max_days: int = 85):
    """Split into max_days-day chunks."""
    chunks = []
    cursor = from_dt
    while cursor < to_dt:
        end = min(cursor + timedelta(days=max_days), to_dt)
        chunks.append((cursor, end))
        cursor = end + timedelta(days=1)
    return chunks


def run_backfill(timeframe: str, years: int, symbols: list[str] | None = None):
    """Main backfill logic."""
    init_db()
    db = SessionLocal()

    to_date   = datetime.now(_UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    from_date = to_date - timedelta(days=365 * years)

    # Resolve instrument list
    all_instruments = get_nifty50_instruments()
    if symbols:
        instruments = []
        for sym in symbols:
            inst = get_instrument(sym)
            if inst:
                instruments.append(inst)
            else:
                logger.warning(f"Symbol '{sym}' not found in NIFTY 50 registry — skipping")
    else:
        instruments = all_instruments

    logger.info(f"Backfill started: {len(instruments)} symbols | timeframe={timeframe} | {from_date.date()} → {to_date.date()}")

    total_inserted = 0
    failed_symbols = []

    for inst in instruments:
        symbol      = inst["symbol"]
        security_id = inst["security_id"]
        exchange    = inst["exchange_segment"]
        instr_type  = inst["instrument"]

        logger.info(f"\n--- {symbol} (id={security_id}) ---")

        # For intraday: check if we can start from latest stored timestamp (resume support)
        if timeframe != "1d":
            latest = get_latest_timestamp(security_id, timeframe)
            effective_from = max(from_date, (latest + timedelta(minutes=1))) if latest else from_date
        else:
            effective_from = from_date

        if effective_from >= to_date:
            logger.info(f"  {symbol}: already up to date. Skipping.")
            continue

        # For intraday, use chunked approach with per-chunk job tracking
        if timeframe != "1d":
            interval_min = int(timeframe.replace("m", ""))
            chunks = _chunk_date_range(effective_from, to_date)

            for chunk_from, chunk_to in chunks:
                from_str = chunk_from.strftime("%Y-%m-%d")
                to_str   = chunk_to.strftime("%Y-%m-%d")

                if _is_chunk_done(db, security_id, timeframe, from_str, to_str):
                    logger.info(f"  [{from_str} → {to_str}] already DONE — skipping")
                    continue

                try:
                    candles = fetch_intraday(
                        security_id=security_id,
                        symbol=symbol,
                        interval_minutes=interval_min,
                        from_date=chunk_from,
                        to_date=chunk_to,
                        exchange_segment=exchange,
                        instrument=instr_type,
                    )
                    inserted = upsert_candles(candles)
                    total_inserted += inserted
                    _log_job(db, security_id, symbol, timeframe, from_str, to_str,
                             IngestionJobStatus.DONE, rows_inserted=inserted)
                    logger.info(f"  [{from_str} → {to_str}] ✅ {inserted} rows inserted")

                except Exception as e:
                    err_msg = str(e)
                    _log_job(db, security_id, symbol, timeframe, from_str, to_str,
                             IngestionJobStatus.FAILED, error=err_msg)
                    logger.error(f"  [{from_str} → {to_str}] ❌ FAILED: {err_msg}")
                    # Continue to next chunk — don't abort the whole job

        else:
            # Daily candles: single request per symbol (no chunking needed)
            from_str = effective_from.strftime("%Y-%m-%d")
            to_str   = to_date.strftime("%Y-%m-%d")

            if _is_chunk_done(db, security_id, "1d", from_str, to_str):
                logger.info(f"  {symbol} daily: already DONE — skipping")
                continue

            try:
                candles = fetch_daily(
                    security_id=security_id,
                    symbol=symbol,
                    from_date=effective_from,
                    to_date=to_date,
                    exchange_segment=exchange,
                    instrument=instr_type,
                )
                inserted = upsert_candles(candles)
                total_inserted += inserted
                _log_job(db, security_id, symbol, "1d", from_str, to_str,
                         IngestionJobStatus.DONE, rows_inserted=inserted)
                logger.info(f"  {symbol} daily: ✅ {inserted} rows inserted")

            except Exception as e:
                err_msg = str(e)
                _log_job(db, security_id, symbol, "1d", from_str, to_str,
                         IngestionJobStatus.FAILED, error=err_msg)
                logger.error(f"  {symbol} daily: ❌ FAILED: {err_msg}")
                failed_symbols.append(symbol)

    db.close()

    logger.info(f"\n{'='*60}")
    logger.info(f"Backfill complete. Total rows inserted: {total_inserted}")
    if failed_symbols:
        logger.warning(f"Failed symbols ({len(failed_symbols)}): {', '.join(failed_symbols)}")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill NIFTY 50 historical candles from Dhan")
    parser.add_argument("--timeframe", default="5m",
                        choices=["1m", "5m", "15m", "25m", "60m", "1d"],
                        help="Candle interval (default: 5m)")
    parser.add_argument("--years", type=int, default=2,
                        help="Years of history to fetch (default: 2)")
    parser.add_argument("--symbols", nargs="*",
                        help="Optional: limit to specific symbols (e.g. RELIANCE TCS)")
    args = parser.parse_args()

    run_backfill(timeframe=args.timeframe, years=args.years, symbols=args.symbols)
