import sys
import os
import json
import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.db import SessionLocal
from app.models import TradeFill, Order
from research.data.candle_repository import get_candles

def compute_metrics():
    db = SessionLocal()
    # Fetch paper fills for today (or all paper fills)
    fills = db.query(TradeFill).filter(TradeFill.paper_meta != None).all()
    
    if not fills:
        print("No paper fills found!")
        return

    print("=== Paper Metrics Analysis ===")
    
    total_trades = len(fills)
    total_slippage_ticks = 0
    total_latency_ms = 0
    
    results = []

    # Map SIDs for candles
    research_engine = create_engine("sqlite:///research.db")
    
    for f in fills:
        meta = f.paper_meta or {}
        order = db.query(Order).filter(Order.id == f.order_id).first()
        if not order:
            continue
            
        sym = order.symbol
        dir = order.direction.value
        signal_price = meta.get("signal_price", float(order.entry_price))
        fill_price = f.price
        
        # We know tick_size is 0.05
        slippage_pct = abs(float(fill_price) - float(signal_price)) / float(signal_price) * 100
        slippage_ticks = meta.get("slippage_ticks", 0)
        latency = meta.get("latency_ms", 0)
        
        total_slippage_ticks += float(slippage_ticks)
        total_latency_ms += float(latency)
        
        # Calculate MAE/MFE
        # Fetch candles after fill time
        fill_time = f.timestamp
        # find SID
        with research_engine.connect() as conn:
            import sqlalchemy
            res = conn.execute(sqlalchemy.text(f"SELECT security_id FROM historical_candles WHERE symbol='{sym}' LIMIT 1;"))
            row = res.fetchone()
            sid = str(row[0]) if row else None
            
        mae, mfe = 0.0, 0.0
        r_multiple = 0.0
        
        if sid:
            # End of day
            eod_time = fill_time.replace(hour=15, minute=15)
            df = get_candles(sid, "5m", fill_time, eod_time)
            if not df.empty:
                high_post = df["high"].max()
                low_post = df["low"].min()
                
                # Assume 1R = 0.5% (approx, based on ORB stop loss configs if not available)
                risk_amt = float(fill_price) * 0.005 # rough default 0.5% risk
                
                if dir == "LONG":
                    mfe_abs = high_post - float(fill_price)
                    mae_abs = float(fill_price) - low_post
                else:
                    mfe_abs = float(fill_price) - low_post
                    mae_abs = high_post - float(fill_price)
                    
                mfe = mfe_abs / risk_amt
                mae = mae_abs / risk_amt
                
                # estimate R realized end of day
                last_price = df.iloc[-1]["close"]
                if dir == "LONG":
                    r_multiple = (last_price - float(fill_price)) / risk_amt
                else:
                    r_multiple = (float(fill_price) - last_price) / risk_amt
                    
        results.append({
            "symbol": sym,
            "dir": dir,
            "signal_price": signal_price,
            "fill_price": float(fill_price),
            "slippage_ticks": float(slippage_ticks),
            "latency_ms": float(latency),
            "mfe_r": round(mfe, 2),
            "mae_r": round(mae, 2),
            "realized_r": round(r_multiple, 2)
        })

    avg_slip = total_slippage_ticks / total_trades
    avg_lat = total_latency_ms / total_trades
    
    df_res = pd.DataFrame(results)
    
    # PF approx
    wins = df_res[df_res["realized_r"] > 0]["realized_r"].sum()
    losses = abs(df_res[df_res["realized_r"] < 0]["realized_r"].sum())
    pf = wins / losses if losses > 0 else float('inf')
    
    avg_mfe = df_res["mfe_r"].mean()
    avg_mae = df_res["mae_r"].mean()
    avg_r = df_res["realized_r"].mean()
    win_rate = len(df_res[df_res["realized_r"] > 0]) / total_trades * 100
    
    print(f"Total Trades: {total_trades}")
    print(f"Avg Slippage: {avg_slip:.2f} ticks")
    print(f"Avg Latency:  {avg_lat:.0f} ms")
    print("-" * 30)
    print("Paper vs Backtest Estimates:")
    print(f"Profit Factor: {pf:.2f}")
    print(f"Win Rate:      {win_rate:.1f}%")
    print(f"Avg R:         {avg_r:.2f} R")
    print(f"Avg MFE:       {avg_mfe:.2f} R")
    print(f"Avg MAE:       {avg_mae:.2f} R")
    print("-" * 30)
    print(df_res[["symbol", "dir", "mfe_r", "mae_r", "realized_r"]].head(10))

if __name__ == "__main__":
    compute_metrics()
