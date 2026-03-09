"""
Integration test: validator + exporter + strategy signal meta.
"""
import sys, os
sys.path.insert(0, r'C:\Users\Administrator\Desktop\Flutter\backend')

print("=" * 60)
print("TEST 1: NiftyBreakout signal meta captures volume + buffer")
print("=" * 60)

from research.strategies.nifty_breakout import NiftyBreakoutStrategy
from datetime import datetime, timezone
import zoneinfo

_IST = zoneinfo.ZoneInfo("Asia/Kolkata")
_UTC = timezone.utc

strategy = NiftyBreakoutStrategy()

def make_bar(dt_ist_str, o, h, l, c, vol):
    dt_ist = datetime.strptime(dt_ist_str, "%Y-%m-%d %H:%M").replace(tzinfo=_IST)
    return {"timestamp": dt_ist.astimezone(_UTC), "open":o, "high":h, "low":l, "close":c, "volume":vol}

# Simulate a trading day
strategy.on_day_start(datetime(2024, 1, 2, tzinfo=_UTC), "TEST")

or_bar1 = make_bar("2024-01-02 09:15", 2000, 2020, 1990, 2010, 100000)
or_bar2 = make_bar("2024-01-02 09:20", 2010, 2025, 2005, 2015, 90000)
or_bar3 = make_bar("2024-01-02 09:25", 2015, 2030, 2000, 2008, 95000)
or_bars = [or_bar1, or_bar2, or_bar3]

# Feed OR bars — should return None (building OR)
for bar in or_bars:
    result = strategy.on_bar(bar, [], None)
    assert result is None, "Should not signal during OR formation"

# OR is now: high=2030, low=1990
# Breakout level = 2030 * 1.001 = 2032.03
# Build some history for volume average
history = list(or_bars)
history_times = ["09:30","09:35","09:40","09:45","09:50","09:55","10:00","10:05","10:10","10:15"]
prev_bars = [make_bar(f"2024-01-02 {t}", 2020, 2035, 2010, 2025, 120000) for t in history_times]
for bar in prev_bars:
    history.append(bar)

# Now trigger breakout: close = 2035 (above 2032.03), high volume
breakout_bar = make_bar("2024-01-02 10:30", 2030, 2040, 2025, 2035, 250000)  # 2× avg
signal = strategy.on_bar(breakout_bar, history, None)

assert signal is not None, "Should produce a LONG signal"
assert signal.direction == "LONG"
assert "volume_at_entry" in signal.meta, "Missing volume_at_entry in signal meta"
assert "rolling_avg_volume" in signal.meta, "Missing rolling_avg_volume in signal meta"
assert "breakout_buffer_pct" in signal.meta, "Missing breakout_buffer_pct in signal meta"
assert signal.meta["volume_at_entry"] == 250000
assert signal.meta["breakout_buffer_pct"] == 0.10
assert signal.entry_reason == "breakout_entry"
print(f"PASS: Signal generated with volume_at_entry={signal.meta['volume_at_entry']}")
print(f"      rolling_avg_volume={signal.meta['rolling_avg_volume']}")
print(f"      breakout_buffer_pct={signal.meta['breakout_buffer_pct']}")

print()
print("=" * 60)
print("TEST 2: Trade exporter CSV output")
print("=" * 60)

from research.backtest.trade_exporter import export_trades_csv
from datetime import timedelta

mock_trades = [
    {
        "symbol": "RELIANCE",
        "security_id": "2885",
        "direction": "LONG",
        "entry_time": datetime(2024, 1, 2, 3, 45, tzinfo=_UTC),   # 09:15 IST
        "exit_time":  datetime(2024, 1, 2, 5, 15, tzinfo=_UTC),   # 10:45 IST
        "entry_price": 2035.0,
        "exit_price":  2080.0,
        "quantity": 49,
        "gross_pnl": 2205.0,
        "charges": 75.0,
        "net_pnl": 2130.0,
        "slippage_entry": 2.45,
        "slippage_exit": 2.45,
        "entry_reason": "breakout_entry",
        "exit_reason": "target_hit",
        "stop_loss": 1990.0,
        "target": 2102.5,
        "opening_range_high": 2030.0,
        "opening_range_low":  1990.0,
        "volume_at_entry": 250000,
        "rolling_avg_volume": 121000.0,
        "breakout_buffer_pct": 0.10,
        "r_multiple": 0.97,
    }
]

out_path = r"C:\Users\Administrator\Desktop\Flutter\backend\test_trades_export.csv"
export_trades_csv(mock_trades, out_path)

import csv
with open(out_path, "r") as f:
    rows = list(csv.DictReader(f))

assert len(rows) == 1
assert rows[0]["symbol"] == "RELIANCE"
assert rows[0]["entry_time"] == "09:15"
assert rows[0]["exit_reason"] == "target_hit"
assert rows[0]["R_multiple"] != ""
assert rows[0]["volume_at_entry"] == "250000"
assert rows[0]["breakout_buffer_pct"] == "0.1"
print(f"PASS: CSV exported. R_multiple={rows[0]['R_multiple']} | volume_at_entry={rows[0]['volume_at_entry']}")
print(f"      exit_time={rows[0]['exit_time']} | exit_reason={rows[0]['exit_reason']}")

print()
print("=" * 60)
print("TEST 3: Candle validator dry run (no data yet — expects NO DATA message)")
print("=" * 60)

from research.utils.candle_validator import validate_symbol

result = validate_symbol(
    symbol="RELIANCE",
    security_id="2885",
    timeframe="5m",
    from_dt=datetime(2024, 1, 1, tzinfo=_UTC),
    to_dt=datetime(2024, 1, 31, tzinfo=_UTC),
)
# Before backfill, should fail with NO DATA
assert result["pass"] == False
assert any("NO DATA" in iss for iss in result["issues"]), f"Expected NO DATA, got: {result['issues']}"
print(f"PASS: Validator correctly reports NO DATA (as expected before backfill)")
print(f"      Symbol={result['symbol']} | total_rows={result['total_rows']}")

print()
print("ALL 3 TESTS PASSED")
