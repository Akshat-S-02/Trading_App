import sys
import os
import time
import zoneinfo
from datetime import datetime, timedelta
import pandas as pd
from sqlalchemy import create_engine
import sqlalchemy

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.engines.paper_strategy_runner import get_runner, MOMENTUM5_UNIVERSE
from research.data.candle_repository import get_candles
from app.core.instruments import get_security_id_multi
from app.db import SessionLocal
import app.models as models
from app.config import config

def get_best_date():
    engine = create_engine("sqlite:///research.db")
    with engine.connect() as conn:
        res = conn.execute(sqlalchemy.text("SELECT date(timestamp) as dt FROM historical_candles WHERE timeframe='5m' AND symbol='HDFCBANK' AND date(timestamp) < '2026-03-13' GROUP BY dt ORDER BY dt DESC LIMIT 1;"))
        row = res.fetchone()
        if row:
            return str(row[0])
    return "2026-03-12"

def run_session():
    print(f"Current Execution Mode: {config.EXECUTION_MODE}")
    if config.EXECUTION_MODE != "paper":
        print("WARNING: EXECUTION_MODE in .env should be 'paper'!")
        
    date_str = get_best_date()
    print(f"=== Starting Paper Session Replay for Date: {date_str} ===")
    
    _IST = zoneinfo.ZoneInfo("Asia/Kolkata")
    dt = datetime.strptime(date_str, "%Y-%m-%d").date()
    start_dt = datetime.combine(dt - timedelta(days=10), datetime.min.time(), tzinfo=timezone.utc if False else _IST).replace(hour=9, minute=15)
    end_dt = datetime.combine(dt, datetime.min.time(), tzinfo=timezone.utc if False else _IST).replace(hour=15, minute=30)
    
    # 1. Start Runner
    runner = get_runner()
    runner.start()
    
    # 2. Fetch candles for MOMENTUM5_UNIVERSE
    engine = create_engine("sqlite:///research.db")
    sids_map = {}
    with engine.connect() as conn:
        for sym in MOMENTUM5_UNIVERSE:
            res = conn.execute(sqlalchemy.text(f"SELECT security_id FROM historical_candles WHERE symbol='{sym}' LIMIT 1;"))
            row = res.fetchone()
            if row:
                sids_map[sym] = str(row[0])
    
    all_candles = []
    
    for sym in MOMENTUM5_UNIVERSE:
        sid = sids_map.get(sym)
        if not sid:
            print(f"Skipping {sym}, SID not found.")
            continue
        df = get_candles(str(sid), "5m", start_dt, end_dt)
        if not df.empty:
            for _, row in df.iterrows():
                # Yield 4 ticks per 5-minute candle to simulate movement
                ts = row["timestamp"]  # UTC datetime of candle START
                # Our TickAggregator bins by 5min. Ticks must fall within this 5min bucket.
                all_candles.append((ts + timedelta(seconds=1), sym, row["open"], 0)) 
                all_candles.append((ts + timedelta(seconds=60), sym, row["high"], row['volume'] // 4))
                all_candles.append((ts + timedelta(seconds=120), sym, row["low"], row['volume'] // 4))
                all_candles.append((ts + timedelta(seconds=299), sym, row["close"], row['volume'] // 4))

    # sort chronologically across all symbols
    all_candles.sort(key=lambda x: x[0])
    
    print(f"Loaded {len(all_candles)} simulated ticks across {len(MOMENTUM5_UNIVERSE)} symbols.")
    
    # 3. Replay Phase (Async Burst)
    import asyncio
    import app.websocket.market_ws as market_ws
    
    async def async_replay():
        market_ws._running = True
        processor_task = asyncio.create_task(market_ws._tick_processor())
        
        c = 0
        t0 = time.time()
        print("BURSTING TICKS into WebSocket Decoupled Queue...")
        
        for ts_utc, sym, price, vol in all_candles:
            try:
                market_ws.tick_queue.put_nowait((sym, float(price), int(vol), ts_utc))
            except asyncio.QueueFull:
                print(f"Queue Full! Lagging too hard at {c}")
                await asyncio.sleep(0.1)
                await market_ws.tick_queue.put((sym, float(price), int(vol), ts_utc))
                
            c += 1
            if c % 10000 == 0:
                print(f"Enqueued {c}/{len(all_candles)}")
                await asyncio.sleep(0.001)  # Yield explicitly to allow processor to catch up if needed
                
        print(f"Enqueuing Complete! Queue depth is {market_ws.tick_queue.qsize()}. Waiting for DRAIN...")
        # Await queue draining
        await market_ws.tick_queue.join()
        
        tf = time.time()
        print(f"Replay complete in {tf-t0:.2f}s!")
        market_ws._running = False
        processor_task.cancel()
        
    asyncio.run(async_replay())
    
    print("Waiting 10s for outbox worker to simulate broker fills...")
    time.sleep(10)
    
    status = runner.get_status()
    print("Runner Status:", status)

if __name__ == "__main__":
    run_session()
