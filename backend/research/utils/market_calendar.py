"""
research/utils/market_calendar.py

NSE trading calendar utilities.
Used by the ingestion layer and backtester to validate session times
and determine valid trading days.

Note: NSE holiday list is maintained for 2024-2026.
Add new years as needed.
"""

from __future__ import annotations

import zoneinfo
from datetime import date, datetime, time

_IST = zoneinfo.ZoneInfo("Asia/Kolkata")

# NSE session times (IST)
SESSION_START = time(9, 15)
SESSION_END   = time(15, 30)
SQUAREOFF_TIME = time(15, 15)   # hard exit for intraday strategies

# NSE declared holidays 2024 + 2025 + 2026
# Source: NSE India official holiday list
_NSE_HOLIDAYS: set[date] = {
    # 2024
    date(2024, 1, 22),  # Ram Mandir inauguration (special closure)
    date(2024, 1, 26),  # Republic Day
    date(2024, 3, 25),  # Holi
    date(2024, 3, 29),  # Good Friday
    date(2024, 4, 14),  # Dr Ambedkar Jayanti / Ram Navami
    date(2024, 4, 17),  # Ram Navami
    date(2024, 4, 21),  # Mahavir Jayanti
    date(2024, 5, 23),  # Buddha Purnima
    date(2024, 6, 17),  # Eid ul-Adha
    date(2024, 7, 17),  # Muharram
    date(2024, 8, 15),  # Independence Day
    date(2024, 10, 2),  # Gandhi Jayanti
    date(2024, 10, 14), # Dussehra
    date(2024, 11, 1),  # Diwali Laxmi Puja
    date(2024, 11, 15), # Guru Nanak Jayanti
    date(2024, 11, 20), # Occasional holiday (Maharashtra)
    date(2024, 12, 25), # Christmas
    # 2025
    date(2025, 1, 26),  # Republic Day
    date(2025, 2, 26),  # Maha Shivaratri
    date(2025, 3, 14),  # Holi
    date(2025, 3, 31),  # Id-ul-Fitr
    date(2025, 4, 10),  # Shri Mahavir Jayanti
    date(2025, 4, 14),  # Dr Ambedkar Jayanti
    date(2025, 4, 18),  # Good Friday
    date(2025, 5, 1),   # Maharashtra Day / Labour Day (NSE closed)
    date(2025, 5, 12),  # Buddha Purnima
    date(2025, 6, 7),   # Id-ul-Adha (Bakri id)
    date(2025, 7, 6),   # Muharram
    date(2025, 8, 15),  # Independence Day
    date(2025, 8, 25),  # Ganesh Chaturthi (actual NSE closure)
    date(2025, 8, 27),  # Ganesh Chaturthi (observed in some years — retained)
    date(2025, 10, 2),  # Gandhi Jayanti / Dussehra
    date(2025, 10, 21), # Diwali Laxmi Puja (+ Muhurat trading evening — treat as holiday for strategy)
    date(2025, 10, 22), # Diwali – Balipratipada
    date(2025, 11, 5),  # Guru Nanak Jayanti
    date(2025, 11, 19), # Guru Nanak Jayanti observed / additional closure
    date(2025, 12, 25), # Christmas
    # 2026
    date(2026, 1, 15),  # Makar Sankranti (NSE closed)
    date(2026, 1, 26),  # Republic Day
    date(2026, 2, 13),  # Maha Shivaratri
    date(2026, 3, 3),   # Holi
    date(2026, 3, 20),  # Good Friday (tentative — update if NSE publishes)
    date(2026, 4, 14),  # Dr Ambedkar Jayanti
    date(2026, 8, 15),  # Independence Day
    date(2026, 10, 2),  # Gandhi Jayanti
    date(2026, 12, 25), # Christmas
}


def is_trading_day(d: date) -> bool:
    """Return True if d is a valid NSE trading day (not weekend, not holiday)."""
    if d.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    if d in _NSE_HOLIDAYS:
        return False
    return True


def trading_days_between(from_date: date, to_date: date) -> list[date]:
    """Return list of NSE trading days in [from_date, to_date] inclusive."""
    from datetime import timedelta
    days = []
    current = from_date
    while current <= to_date:
        if is_trading_day(current):
            days.append(current)
        current += timedelta(days=1)
    return days


def is_in_session(dt: datetime) -> bool:
    """
    Return True if dt (timezone-aware UTC or IST) falls within NSE equity session
    09:15–15:30 IST.
    """
    dt_ist = dt.astimezone(_IST)
    t = dt_ist.time().replace(second=0, microsecond=0)
    return SESSION_START <= t <= SESSION_END


def is_past_squareoff(dt: datetime) -> bool:
    """Return True if dt is at or after the 15:15 IST hard squareoff cutoff."""
    dt_ist = dt.astimezone(_IST)
    t = dt_ist.time()
    return t >= SQUAREOFF_TIME


def to_ist(dt_utc: datetime) -> datetime:
    """Convert a UTC-aware datetime to IST."""
    return dt_utc.astimezone(_IST)
