"""
research/data/candle_repository.py

Repository for reading and writing historical candles to/from research.db.

V1 scope — 3 public methods:
  - upsert_candles(candles)
  - get_candles(security_id, timeframe, from_dt, to_dt) -> pd.DataFrame
  - get_latest_timestamp(security_id, timeframe) -> datetime | None

All queries use security_id as the canonical key. symbol is display-only.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from research.db import SessionLocal
from research.data.models import HistoricalCandle

logger = logging.getLogger("CandleRepository")


def upsert_candles(candles: list[dict]) -> int:
    """
    Bulk-insert candles. Silently ignores duplicates via INSERT OR IGNORE
    (the UNIQUE constraint on (security_id, timeframe, timestamp) handles dedup).

    Each dict must have:
      security_id, symbol, exchange_segment, instrument, timeframe, timestamp (datetime UTC),
      open, high, low, close, volume
    Optional: open_interest (defaults to 0)

    Returns: number of rows actually inserted.
    """
    if not candles:
        return 0

    db: Session = SessionLocal()
    inserted = 0
    try:
        for candle in candles:
            stmt = text("""
                INSERT OR IGNORE INTO historical_candles
                  (security_id, symbol, exchange_segment, instrument,
                   timeframe, timestamp, open, high, low, close, volume, open_interest)
                VALUES
                  (:security_id, :symbol, :exchange_segment, :instrument,
                   :timeframe, :timestamp, :open, :high, :low, :close, :volume, :open_interest)
            """)
            result = db.execute(stmt, {
                "security_id":      candle["security_id"],
                "symbol":           candle["symbol"],
                "exchange_segment": candle.get("exchange_segment", "NSE_EQ"),
                "instrument":       candle.get("instrument", "EQUITY"),
                "timeframe":        candle["timeframe"],
                "timestamp":        candle["timestamp"],   # must be datetime, UTC
                "open":             float(candle["open"]),
                "high":             float(candle["high"]),
                "low":              float(candle["low"]),
                "close":            float(candle["close"]),
                "volume":           int(candle["volume"]),
                "open_interest":    int(candle.get("open_interest", 0)),
            })
            inserted += result.rowcount
        db.commit()
        logger.info(f"upsert_candles: {inserted}/{len(candles)} rows inserted (rest were duplicates)")
    except Exception as e:
        db.rollback()
        logger.error(f"upsert_candles failed: {e}")
        raise
    finally:
        db.close()

    return inserted


def get_candles(
    security_id: str,
    timeframe: str,
    from_dt: datetime,
    to_dt: datetime,
) -> pd.DataFrame:
    """
    Fetch candles for a given security_id + timeframe in [from_dt, to_dt].

    Returns a pandas DataFrame with columns:
      timestamp, open, high, low, close, volume, open_interest, symbol

    Timestamps are returned as timezone-aware UTC datetimes.
    Candles outside the 09:15–15:30 IST session window are already excluded at
    ingestion time for intraday timeframes; this method trusts the stored data.

    DataFrame is sorted by timestamp ascending (oldest first) — correct for backtesting.
    """
    db: Session = SessionLocal()
    try:
        rows = (
            db.query(HistoricalCandle)
            .filter(
                HistoricalCandle.security_id == security_id,
                HistoricalCandle.timeframe   == timeframe,
                HistoricalCandle.timestamp   >= from_dt,
                HistoricalCandle.timestamp   <= to_dt,
            )
            .order_by(HistoricalCandle.timestamp.asc())
            .all()
        )

        if not rows:
            logger.warning(f"get_candles: no data for {security_id}/{timeframe} [{from_dt.date()} → {to_dt.date()}]")
            return pd.DataFrame(columns=["timestamp","open","high","low","close","volume","open_interest","symbol"])

        data = [
            {
                "timestamp":      row.timestamp,
                "open":           float(row.open),
                "high":           float(row.high),
                "low":            float(row.low),
                "close":          float(row.close),
                "volume":         row.volume,
                "open_interest":  row.open_interest or 0,
                "symbol":         row.symbol,
            }
            for row in rows
        ]
        df = pd.DataFrame(data)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        return df

    finally:
        db.close()


def get_latest_timestamp(security_id: str, timeframe: str) -> Optional[datetime]:
    """
    Return the most recent timestamp stored for this security_id+timeframe.
    Returns None if no data exists yet.
    Used by the daily sync job to determine where to start incremental fetch.
    """
    db: Session = SessionLocal()
    try:
        row = (
            db.query(HistoricalCandle.timestamp)
            .filter(
                HistoricalCandle.security_id == security_id,
                HistoricalCandle.timeframe   == timeframe,
            )
            .order_by(HistoricalCandle.timestamp.desc())
            .first()
        )
        return row[0] if row else None
    finally:
        db.close()
