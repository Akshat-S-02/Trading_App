import sys
import os
import asyncio
from datetime import datetime, timedelta
import zoneinfo

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from research.services.historical_data_service import fetch_intraday
from app.core.instruments import load_instruments, get_security_id_multi

async def main():
    load_instruments()
    _IST = zoneinfo.ZoneInfo("Asia/Kolkata")
    now_ist = datetime.now(_IST)
    
    # Check 15:25 - 15:30 window
    close_time = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
    start = close_time - timedelta(minutes=10)
    
    symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]
    resolved = get_security_id_multi(symbols)
    
    for sym in symbols:
        sid = resolved.get(sym)
        if not sid: continue
        try:
            candles = fetch_intraday(str(sid), sym, 5, start, close_time)
            if not candles:
                print(f"{sym}: No close price found")
                continue
            last_close = candles[-1]["close"]
            print(f"{sym} CLOSE (15:30): {last_close}")
        except Exception as e:
            print(f"{sym} ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(main())
