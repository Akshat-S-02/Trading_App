import sys
import os
import zoneinfo
from datetime import datetime

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.engines.tick_aggregator import TickAggregator

def test_aggregator():
    candles = []
    
    def on_candle(sym, c):
        candles.append(c)
        
    agg = TickAggregator(on_candle=on_candle)
    
    _IST = zoneinfo.ZoneInfo("Asia/Kolkata")
    
    # Send some fake ticks around 09:15-09:20 IST
    base_time = datetime(2024, 1, 1, 9, 15, 5, tzinfo=_IST)
    
    agg.on_tick("RELIANCE", 2500.0, 100, tick_time=base_time)
    agg.on_tick("RELIANCE", 2505.0, 200, tick_time=base_time.replace(minute=16))
    agg.on_tick("RELIANCE", 2495.0,  50, tick_time=base_time.replace(minute=17))
    agg.on_tick("RELIANCE", 2510.0, 300, tick_time=base_time.replace(minute=19))
    
    # This tick rolls the bucket to 09:20 and flushes the 09:15-09:20 bucket
    agg.on_tick("RELIANCE", 2515.0, 150, tick_time=base_time.replace(minute=20, second=1))
    
    print("--- LIVE AGGREGATOR OUTPUT ---")
    for c in candles:
        print(f"Candle: timestamp={c['timestamp'].isoformat()} (UTC)")
        print(f"        O={c['open']} H={c['high']} L={c['low']} C={c['close']} V={c['volume']}")
        
    print("\n--- RESEARCH STRATEGY ADAPTER BAR MATCH ---")
    for c in candles:
        bar = {
            "timestamp": c["timestamp"],
            "open":      float(c["open"]),
            "high":      float(c["high"]),
            "low":       float(c["low"]),
            "close":     float(c["close"]),
            "volume":    int(c.get("volume", 0)),
        }
        print("Mapped to bar dict for strategy.on_bar():")
        print(f"{{ 'timestamp': {repr(bar['timestamp'])}, 'open': {bar['open']}, 'high': {bar['high']}, 'low': {bar['low']}, 'close': {bar['close']}, 'volume': {bar['volume']} }}")

if __name__ == "__main__":
    test_aggregator()
