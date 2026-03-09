import sys
import os
import pandas as pd
from datetime import datetime, timedelta
from decimal import Decimal

# Add root backend dir to sys.path so 'app' imports work
sys.path.append(os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.db import SessionLocal, Base, engine
from app.models import User, Strategy, UserStrategyAllocation, RiskCategory, Direction, OrderStatus
from app.engines.strategy_engine import NiftyBreakoutStrategy
from app.engines.execution_engine import ExecutionEngine

def generate_dummy_candles(days: int = 1) -> pd.DataFrame:
    """Generate fake NIFTY 1-min candles that trigger breakout signals AND stop losses"""
    base_time = datetime.now().replace(hour=9, minute=15, second=0, microsecond=0)
    records = []
    
    price = 22000.0
    for i in range(days * 375): # 375 mins in NSE session
        # Simulate a small drift
        if i % 50 == 0: 
            price *= 1.003 # 0.3% breakout spike
        elif i % 100 == 0:
            price *= 0.990 # 1.0% drop (fake SL hunt)
            
        records.append({
            "timestamp": base_time + timedelta(minutes=i),
            "Open": price,
            "High": price + 10,
            "Low": price - 10,
            "Close": price + 2,
            "Volume": 10000
        })
        price += 1 # small upward bias
        
    df = pd.DataFrame(records).set_index("timestamp")
    return df

def seed_simulation_db(db):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    # 1. Create Strategy
    strat = Strategy(name="NIFTY_BREAKOUT_SIM", strategy_type="INTRADAY", risk_profile="LOW")
    db.add(strat)
    db.commit()
    db.refresh(strat)
    
    # 2. Create User (50,000 capital, 2% max daily loss)
    user = User(
        username="sim_user", 
        capital_initial=50000.0, 
        capital_current=50000.0,
        max_daily_dd=2.0 # Max loss 1000 rupees
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # 3. Enrol User in Strategy (1.0% risk per trade)
    alloc = UserStrategyAllocation(
        user_id=user.id, 
        strategy_id=strat.id, 
        allocation_percentage=100.0,
        risk_per_trade=1.0 # 500 rupees risk
    )
    db.add(alloc)
    db.commit()
    
    return strat.id, user.id

def run_simulation():
    print("STARTING DETERMINISTIC BACKTEST ENGINE")
    db = SessionLocal()
    strat_id, user_id = seed_simulation_db(db)
    
    strategy = NiftyBreakoutStrategy(strategy_id=strat_id, symbol="NIFTY")
    executor = ExecutionEngine(db)
    
    df = generate_dummy_candles(days=1)
    
    print("GENERATED 1 day of 1-minute OHLCV candles (NIFTY)")
    
    signals_fired = 0
    orders_placed = 0
    
    # Iterate through candle stream as if it's "live"
    for i in range(len(df)):
        # Stream one candle at a time
        row = df.iloc[i].copy()
        row['timestamp'] = df.index[i]
        bar_dict = row.to_dict()
        
        signal = strategy.on_bar(bar_dict)
        
        if signal:
            signals_fired += 1
            print(f"\\nSIGNAL GENERATED: {signal.symbol} {signal.direction} @ {signal.entry_price:.2f}")
            
            # Execute
            order_ids = executor.process_signal(signal)
            orders_placed += len(order_ids)
            
            if order_ids:
                user = db.query(User).filter_by(id=user_id).first()
                if not user.portfolio_metrics:
                    from app.models import PortfolioMetrics
                    user.portfolio_metrics = PortfolioMetrics(user_id=user.id, realized_pnl=Decimal('0.0'))
                    db.add(user.portfolio_metrics)
                    db.commit()
                    db.refresh(user.portfolio_metrics)
                    
                from app.models import Order
                order = db.query(Order).filter_by(id=order_ids[0]).first()
                qty = Decimal(str(order.quantity))
                entry_price = Decimal(str(signal.entry_price))
                exit_price = Decimal(str(signal.stop_loss)) if signal.stop_loss else entry_price
                
                # Slippage Model: 0.05% bidirectional
                slippage_pct = Decimal('0.0005')
                entry_slip = entry_price * slippage_pct * qty
                exit_slip = exit_price * slippage_pct * qty
                total_slippage = entry_slip + exit_slip
                
                # Calculate True Loss
                real_loss = (entry_price - exit_price) * qty
                total_loss = real_loss + total_slippage
                
                current_pnl = user.portfolio_metrics.realized_pnl or Decimal('0.0')
                user.portfolio_metrics.realized_pnl = current_pnl - total_loss
                user.capital_current -= total_loss
                db.commit()
                print(f"SIMULATED SL HIT w/ SLIPPAGE! Loss: {real_loss:.2f}, Slip: {total_slippage:.2f}, Capital: {user.capital_current:.2f}")
                
    
    print("\\n===============================")
    print("SIMULATION COMPLETE")
    print(f"Total Signals: {signals_fired}")
    print(f"Total Orders Executed: {orders_placed}")
    print("===============================\\n")

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    run_simulation()
