import sys
import os
import asyncio
from datetime import datetime
import zoneinfo

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from research.services.historical_data_service import fetch_intraday
from app.core.instruments import load_instruments, get_security_id_multi

async def main():
    load_instruments()
    _IST = zoneinfo.ZoneInfo("Asia/Kolkata")
    now = datetime.now(_IST)
    start = now.replace(hour=9, minute=15, second=0, microsecond=0)
    end = start + timedelta(minutes=30)
    
    symbols = ["INFY", "RELIANCE"]
    resolved = get_security_id_multi(symbols)
    
    for sym in symbols:
        sid = resolved.get(sym)
        if not sid: continue
        candles = fetch_intraday(str(sid), sym, 5, start, end)
        if not candles:
            print(f"{sym}: No candles found")
            continue
            
        low = min(c["low"] for c in candles)
        high = max(c["high"] for c in candles)
        print(f"{sym} OR (09:15-09:45): Low={low}, High={high}")

if __name__ == "__main__":
    from datetime import timedelta
    asyncio.run(main())
