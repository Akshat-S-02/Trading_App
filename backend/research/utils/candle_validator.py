"""
research/utils/candle_validator.py

Candle quality validator for the research warehouse.

Runs a suite of checks on stored candles per symbol and generates
both a console summary and a JSON diagnostics report.

Checks performed per symbol per day:
  - First bar timestamp is exactly 09:15 IST
  - No bars outside 09:15–15:30 IST session
  - No duplicate timestamps
  - Timestamps strictly increasing
  - 5-minute spacing between consecutive bars
  - No weekend candles
  - No NSE holiday candles
  - OHLC sanity: high >= open,close,low and low <= open,close,high
  - Volume not negative
  - Per-day candle count distribution

Usage:
  cd backend
  python -m research.utils.candle_validator --symbols RELIANCE TCS HDFCBANK --timeframe 5m
  python -m research.utils.candle_validator --symbols RELIANCE --timeframe 5m --from 2024-01-01 --to 2024-06-30
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import os
from collections import defaultdict
from datetime import datetime, date, timedelta, timezone, time as dtime
from pathlib import Path
from typing import Optional

import pandas as pd
import zoneinfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from research.db import init_db
from research.data.candle_repository import get_candles
from research.data.instrument_repository import get_instrument, get_nifty50_instruments
from research.utils.market_calendar import is_trading_day

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CandleValidator")

_IST = zoneinfo.ZoneInfo("Asia/Kolkata")
_UTC = timezone.utc

# Expected 5-minute session: 09:15 to 15:30 = 75 bars
_SESSION_START_IST = dtime(9, 15)
_SESSION_END_IST   = dtime(15, 30)
_FULL_DAY_BARS     = 75           # (15:30 - 09:15) / 5min + 1 = 75 bars
_SPACING_MINUTES   = 5


# ---------------------------------------------------------------------------
# Core validator
# ---------------------------------------------------------------------------

def validate_symbol(
    symbol: str,
    security_id: str,
    timeframe: str,
    from_dt: datetime,
    to_dt: datetime,
) -> dict:
    """
    Run all quality checks on candles for one symbol.
    Returns a diagnostics dict with pass/fail summary + per-day details.
    """
    df = get_candles(security_id, timeframe, from_dt, to_dt)

    result = {
        "symbol":         symbol,
        "security_id":    security_id,
        "timeframe":      timeframe,
        "from":           from_dt.date().isoformat(),
        "to":             to_dt.date().isoformat(),
        "total_rows":     0,
        "total_days":     0,
        "pass":           True,
        "issues":         [],
        "per_day":        {},
        "candle_count_distribution": {},
    }

    if df.empty:
        result["pass"] = False
        result["issues"].append("NO DATA: no candles found for this symbol/timeframe/range")
        return result

    result["total_rows"] = len(df)

    # Convert timestamps to IST for session checks
    df["ts_ist"] = df["timestamp"].dt.tz_convert(_IST)
    df["date_ist"] = df["ts_ist"].dt.date
    df["time_ist"] = df["ts_ist"].dt.time

    trading_days = {
        d for d in (from_dt.date() + timedelta(days=i)
                    for i in range((to_dt.date() - from_dt.date()).days + 1))
        if is_trading_day(d)
    }
    result["total_days"] = len(trading_days)

    issues_global = []
    per_day = {}
    candle_counts = defaultdict(int)

    for day_date, day_df in df.groupby("date_ist"):
        day_issues = []
        day_df = day_df.sort_values("ts_ist").reset_index(drop=True)
        times = day_df["time_ist"].tolist()
        ts_list = day_df["ts_ist"].tolist()

        # --- Weekend / Holiday check ---
        if day_date.weekday() >= 5:
            day_issues.append("WEEKEND_DATA: candles present on a weekend")
        if day_date not in trading_days and day_date.weekday() < 5:
            day_issues.append("HOLIDAY_DATA: candles present on an NSE holiday")

        # --- First bar ---
        if times and times[0] != _SESSION_START_IST:
            day_issues.append(f"FIRST_BAR: expected 09:15 IST, got {times[0]}")

        # --- Out-of-session bars ---
        out_of_session = [
            str(t) for t in times
            if not (_SESSION_START_IST <= t <= _SESSION_END_IST)
        ]
        if out_of_session:
            day_issues.append(f"OUT_OF_SESSION: {len(out_of_session)} bars — {out_of_session[:3]}")

        # --- Duplicate timestamps ---
        dupes = day_df[day_df.duplicated("ts_ist", keep=False)]
        if not dupes.empty:
            day_issues.append(f"DUPLICATES: {len(dupes)} duplicate timestamps")

        # --- Strict ascending timestamps ---
        for i in range(1, len(ts_list)):
            if ts_list[i] <= ts_list[i - 1]:
                day_issues.append(f"NOT_ASCENDING: timestamp at index {i} not > previous")
                break

        # --- 5-minute spacing ---
        bad_spacing = []
        for i in range(1, len(ts_list)):
            diff_min = (ts_list[i] - ts_list[i - 1]).seconds // 60
            if diff_min != _SPACING_MINUTES:
                bad_spacing.append(f"{ts_list[i - 1].time()}->{ts_list[i].time()}={diff_min}m")
        if bad_spacing:
            day_issues.append(f"BAD_SPACING ({len(bad_spacing)} gaps): {bad_spacing[:3]}")

        # --- OHLC sanity ---
        ohlc_bad = day_df[
            (day_df["high"] < day_df["open"])  |
            (day_df["high"] < day_df["close"]) |
            (day_df["high"] < day_df["low"])   |
            (day_df["low"]  > day_df["open"])  |
            (day_df["low"]  > day_df["close"]) |
            (day_df["volume"] < 0)
        ]
        if not ohlc_bad.empty:
            day_issues.append(f"BAD_OHLC: {len(ohlc_bad)} candles with invalid OHLC/volume")

        # --- Bar count ---
        count = len(day_df)
        candle_counts[count] += 1
        if count < _FULL_DAY_BARS:
            day_issues.append(f"MISSING_BARS: {count}/{_FULL_DAY_BARS} bars (missing {_FULL_DAY_BARS - count})")

        if day_issues:
            per_day[str(day_date)] = day_issues
            issues_global.extend([f"[{day_date}] {iss}" for iss in day_issues])

    result["per_day"] = per_day
    result["issues"] = issues_global
    result["candle_count_distribution"] = {str(k): v for k, v in sorted(candle_counts.items())}

    # --- Days with no data when they should have data ---
    days_with_data = set(df["date_ist"].unique())
    missing_days = trading_days - days_with_data
    if missing_days:
        for md in sorted(missing_days):
            result["issues"].append(f"[{md}] MISSING_DAY: no candles stored for this trading day")

    result["pass"] = len(result["issues"]) == 0
    return result


# ---------------------------------------------------------------------------
# Multi-symbol runner
# ---------------------------------------------------------------------------

def run_validation(
    symbols: list[str],
    timeframe: str,
    from_date: str,
    to_date: str,
    output_path: Optional[str] = None,
) -> list[dict]:
    init_db()

    from_dt = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=_UTC)
    to_dt   = datetime.strptime(to_date,   "%Y-%m-%d").replace(tzinfo=_UTC)

    results = []

    print(f"\n{'='*60}")
    print(f"CANDLE QUALITY VALIDATOR")
    print(f"Symbols : {symbols}")
    print(f"Timeframe: {timeframe}")
    print(f"Range   : {from_date} -> {to_date}")
    print(f"{'='*60}\n")

    for symbol in symbols:
        inst = get_instrument(symbol)
        if not inst:
            print(f"  [{symbol}] NOT FOUND in registry — skip")
            continue

        print(f"Validating {symbol} ...", end=" ", flush=True)
        result = validate_symbol(
            symbol=symbol,
            security_id=inst["security_id"],
            timeframe=timeframe,
            from_dt=from_dt,
            to_dt=to_dt,
        )
        results.append(result)

        status = "[PASS]" if result["pass"] else f"[FAIL] ({len(result['issues'])} issues)"
        print(status)
        print(f"  Total rows : {result['total_rows']}")
        print(f"  Trading days: {result['total_days']}")

        # Candle count distribution
        dist = result["candle_count_distribution"]
        if dist:
            most_common = max(dist, key=lambda k: dist[k])
            print(f"  Most common bars/day: {most_common} ({dist[most_common]} days)")

        # Show first 5 issues
        if result["issues"]:
            print(f"  Sample issues:")
            for iss in result["issues"][:5]:
                print(f"    [!] {iss}")
            if len(result["issues"]) > 5:
                print(f"    ... and {len(result['issues']) - 5} more")
        print()

    # Summary table
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"{'Symbol':<15} {'Status':<10} {'Rows':>8} {'Days':>6} {'Issues':>8}")
    print(f"{'-'*15} {'-'*10} {'-'*8} {'-'*6} {'-'*8}")
    for r in results:
        status = "PASS" if r["pass"] else "FAIL"
        print(f"{r['symbol']:<15} {status:<10} {r['total_rows']:>8} {r['total_days']:>6} {len(r['issues']):>8}")

    all_pass = all(r["pass"] for r in results)
    print(f"\nOverall: {'[ALL PASS]' if all_pass else '[ISSUES FOUND] -- fix before backtesting'}")

    # Write JSON report
    if output_path:
        Path(output_path).write_text(json.dumps(results, indent=2, default=str))
        print(f"\nDiagnostics written to: {output_path}")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate candle quality in research.db")
    parser.add_argument("--symbols", nargs="+", required=True, help="Symbols to validate")
    parser.add_argument("--timeframe", default="5m",
                        choices=["1m", "5m", "15m", "25m", "60m", "1d"])
    parser.add_argument("--from", dest="from_date", default="2024-01-01")
    parser.add_argument("--to",   dest="to_date",
                        default=datetime.now(_UTC).strftime("%Y-%m-%d"))
    parser.add_argument("--output", default=None,
                        help="Path to write JSON diagnostics report (optional)")
    args = parser.parse_args()

    run_validation(
        symbols=args.symbols,
        timeframe=args.timeframe,
        from_date=args.from_date,
        to_date=args.to_date,
        output_path=args.output,
    )
