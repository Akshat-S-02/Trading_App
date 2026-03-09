"""
research/services/historical_data_service.py

Fetches historical candles from Dhan's v2 API and normalizes them into
row-wise dicts ready for upsert into research.db.

Endpoints:
  - POST https://api.dhan.co/v2/charts/historical  (daily OHLCV)
  - POST https://api.dhan.co/v2/charts/intraday    (1/5/15/25/60 min OHLCV)

Key design decisions:
  - Intraday requests auto-chunked into 85-day windows (Dhan limit is 90 days)
  - IST session filter applied at normalize time: intraday candles outside
    09:15–15:30 IST are dropped before storage
  - Timestamps stored as UTC datetime objects
  - Rate limit: 500ms sleep between API calls
  - _normalize_response is a pure function — easy to unit test without API calls
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
import zoneinfo

import requests

from app.config import config  # reuse existing Dhan credentials

logger = logging.getLogger("HistoricalDataService")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_IST = zoneinfo.ZoneInfo("Asia/Kolkata")
_UTC = timezone.utc

_DAILY_URL    = "https://api.dhan.co/v2/charts/historical"
_INTRADAY_URL = "https://api.dhan.co/v2/charts/intraday"

_CHUNK_DAYS   = 85      # Dhan limit is 90; use 85 with a safety margin
_RATE_LIMIT_S = 0.5     # seconds between requests

# NSE equity session in IST
_SESSION_START = (9, 15)   # 09:15 IST
_SESSION_END   = (15, 30)  # 15:30 IST


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_headers() -> dict:
    return {
        "Content-Type":  "application/json",
        "access-token":  config.ACCESS_TOKEN,
    }


def _ist_to_utc(dt_ist: datetime) -> datetime:
    return dt_ist.astimezone(_UTC)


def _is_in_session(dt_utc: datetime) -> bool:
    """Check whether a UTC datetime falls within NSE equity session (09:15–15:30 IST)."""
    dt_ist = dt_utc.astimezone(_IST)
    session_start = dt_ist.replace(hour=_SESSION_START[0], minute=_SESSION_START[1], second=0, microsecond=0)
    session_end   = dt_ist.replace(hour=_SESSION_END[0],   minute=_SESSION_END[1],   second=0, microsecond=0)
    return session_start <= dt_ist <= session_end


def _chunk_date_range(from_date: datetime, to_date: datetime, max_days: int = _CHUNK_DAYS) -> list[tuple[datetime, datetime]]:
    """Split [from_date, to_date] into chunks of at most max_days days."""
    chunks = []
    cursor = from_date
    while cursor < to_date:
        chunk_end = min(cursor + timedelta(days=max_days), to_date)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def _normalize_response(
    raw: dict,
    symbol: str,
    security_id: str,
    timeframe: str,
    exchange_segment: str = "NSE_EQ",
    instrument: str = "EQUITY",
    apply_session_filter: bool = True,
) -> list[dict]:
    """
    Convert Dhan's array-based response into a list of row dicts.

    Dhan returns: {open: [...], high: [...], low: [...], close: [...], volume: [...],
                   timestamp: [...unix epoch secs...], open_interest: [...]}

    apply_session_filter=True drops candles outside NSE session (for intraday only).
    For daily candles, pass apply_session_filter=False.
    """
    opens         = raw.get("open",           [])
    highs         = raw.get("high",           [])
    lows          = raw.get("low",            [])
    closes        = raw.get("close",          [])
    volumes       = raw.get("volume",         [])
    timestamps    = raw.get("timestamp",      [])
    open_interest = raw.get("open_interest",  [0] * len(opens))

    candles = []
    for i, ts in enumerate(timestamps):
        # Convert Unix epoch (seconds) → UTC datetime
        dt_utc = datetime.fromtimestamp(ts, tz=_UTC)

        # Session filter for intraday candles
        if apply_session_filter and not _is_in_session(dt_utc):
            continue

        try:
            candle = {
                "security_id":      security_id,
                "symbol":           symbol,
                "exchange_segment": exchange_segment,
                "instrument":       instrument,
                "timeframe":        timeframe,
                "timestamp":        dt_utc,
                "open":             float(opens[i]),
                "high":             float(highs[i]),
                "low":              float(lows[i]),
                "close":            float(closes[i]),
                "volume":           int(volumes[i]),
                "open_interest":    int(open_interest[i]) if i < len(open_interest) else 0,
            }
            candles.append(candle)
        except (IndexError, ValueError) as e:
            logger.warning(f"Skipping malformed candle at index {i} for {symbol}: {e}")

    return candles


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_daily(
    security_id: str,
    symbol: str,
    from_date: datetime,
    to_date: datetime,
    exchange_segment: str = "NSE_EQ",
    instrument: str = "EQUITY",
) -> list[dict]:
    """
    Fetch daily OHLCV candles from Dhan for a single instrument.
    No chunking needed — Dhan provides daily data from inception date.

    Returns normalized list of candle dicts ready for upsert_candles().
    """
    payload = {
        "securityId":      security_id,
        "exchangeSegment": exchange_segment,
        "instrument":      instrument,
        "expiryCode":      0,
        "oi":              False,
        "fromDate":        from_date.strftime("%Y-%m-%d"),
        "toDate":          to_date.strftime("%Y-%m-%d"),
    }

    logger.info(f"Fetching daily candles: {symbol} [{from_date.date()} → {to_date.date()}]")

    try:
        resp = requests.post(_DAILY_URL, json=payload, headers=_get_headers(), timeout=30)
        resp.raise_for_status()
        raw = resp.json()

        if "open" not in raw:
            logger.warning(f"No candle data returned for {symbol} daily. Response: {raw}")
            return []

        candles = _normalize_response(
            raw, symbol, security_id, "1d",
            exchange_segment=exchange_segment,
            instrument=instrument,
            apply_session_filter=False,  # daily candles have no session time component
        )
        logger.info(f"  → {len(candles)} daily candles fetched for {symbol}")
        return candles

    except requests.HTTPError as e:
        logger.error(f"HTTP error fetching daily candles for {symbol}: {e} — {e.response.text if e.response else ''}")
        raise
    except Exception as e:
        logger.error(f"Error fetching daily candles for {symbol}: {e}")
        raise


def fetch_intraday(
    security_id: str,
    symbol: str,
    interval_minutes: int,
    from_date: datetime,
    to_date: datetime,
    exchange_segment: str = "NSE_EQ",
    instrument: str = "EQUITY",
) -> list[dict]:
    """
    Fetch intraday OHLCV candles from Dhan for a single instrument.
    Auto-chunks into 85-day windows (Dhan limit is 90 days per request).
    Applies IST session filter (09:15–15:30) — non-session candles are dropped.

    interval_minutes: 1 | 5 | 15 | 25 | 60

    Returns normalized list of candle dicts ready for upsert_candles().
    """
    timeframe = f"{interval_minutes}m"
    chunks    = _chunk_date_range(from_date, to_date, max_days=_CHUNK_DAYS)
    all_candles: list[dict] = []

    logger.info(f"Fetching {timeframe} intraday: {symbol} — {len(chunks)} chunk(s)")

    for chunk_from, chunk_to in chunks:
        payload = {
            "securityId":      security_id,
            "exchangeSegment": exchange_segment,
            "instrument":      instrument,
            "interval":        str(interval_minutes),
            "oi":              False,
            "fromDate":        chunk_from.strftime("%Y-%m-%d %H:%M:%S"),
            "toDate":          chunk_to.strftime("%Y-%m-%d %H:%M:%S"),
        }

        try:
            resp = requests.post(_INTRADAY_URL, json=payload, headers=_get_headers(), timeout=30)
            resp.raise_for_status()
            raw = resp.json()

            if "open" not in raw:
                logger.warning(f"  No data for {symbol} {timeframe} [{chunk_from.date()} → {chunk_to.date()}]")
                time.sleep(_RATE_LIMIT_S)
                continue

            candles = _normalize_response(
                raw, symbol, security_id, timeframe,
                exchange_segment=exchange_segment,
                instrument=instrument,
                apply_session_filter=True,
            )
            all_candles.extend(candles)
            logger.info(f"  Chunk [{chunk_from.date()} → {chunk_to.date()}]: {len(candles)} candles")

        except requests.HTTPError as e:
            logger.error(f"  HTTP error [{chunk_from.date()} → {chunk_to.date()}] for {symbol}: {e}")
            raise

        except Exception as e:
            logger.error(f"  Error [{chunk_from.date()} → {chunk_to.date()}] for {symbol}: {e}")
            raise

        finally:
            time.sleep(_RATE_LIMIT_S)

    logger.info(f"  → Total: {len(all_candles)} {timeframe} candles fetched for {symbol}")
    return all_candles
