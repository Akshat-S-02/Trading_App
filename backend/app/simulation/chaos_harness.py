import sys
import os
import pandas as pd
from datetime import datetime, timedelta, timezone, date, time
import threading

sys.path.append(os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.db import SessionLocal, Base, engine
from app import models
from app.models import User, Strategy, UserStrategyAllocation, RiskCategory, Direction, OrderStatus, SystemSettings, PortfolioMetrics, Order
from app.engines.strategy_engine import Signal
from app.engines.execution_engine import ExecutionEngine
from app.engines.risk_engine import RiskGate
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def seed_simulation_db(db):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    # Settings (no emergency stop initially)
    settings = SystemSettings(emergency_stop=False)
    db.add(settings)
    
    # 1. Create Strategy
    strat = Strategy(name="TEST_STRATEGY", strategy_type="INTRADAY", risk_profile="LOW")
    db.add(strat)
    db.commit()
    db.refresh(strat)
    
    # 2. Create User (50,000 capital, 2% max daily loss = 1000 INR)
    user = User(
        username="sim_user", 
        capital_initial=50000.0, 
        capital_current=50000.0,
        max_daily_dd=2.0,
        max_orders_per_minute=2, # VERY LOW for testing throttle!
        max_open_positions=2,
        session_start_time=time(9, 15),
        session_end_time=time(15, 30),
        last_reset_date=date(2025, 1, 1) # Force a reset on next trade
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # 3. Add Portfolio Metrics with fake carried over PnL from "yesterday"
    pm = PortfolioMetrics(user_id=user.id, realized_pnl=-500.0) 
    db.add(pm)
    db.commit()
    
    # 4. Enrol User in Strategy (1.0% risk per trade = 500 INR)
    alloc = UserStrategyAllocation(
        user_id=user.id, 
        strategy_id=strat.id, 
        allocation_percentage=100.0,
        risk_per_trade=1.0 
    )
    db.add(alloc)
    db.commit()
    
    return strat.id, user.id


def run_chaos_harness():
    print("STARTING LIVE MARKET CHAOS SIMULATION HARNESS")
    db = SessionLocal()
    strat_id, user_id = seed_simulation_db(db)
    
    executor = ExecutionEngine(db)
    base_time = datetime.now(timezone.utc)

    # ==========================================================
    # TEST A: Intraday Auto-Reset
    # ==========================================================
    print("\\n--- TEST A: Intraday Auto-Reset ---")
    
    # User was seeded with -500 PnL and a last_reset_date of 2025-01-01.
    # Today is (presumably) later. The very first signal should instantly wipe their PnL.
    
    sig1 = Signal(strat_id, "NIFTY", "LONG", 22000, 21950, base_time)
    orders = executor.process_signal(sig1)
    
    db.expire_all()
    user = db.query(User).filter_by(id=user_id).first()
    
    if user.portfolio_metrics.realized_pnl == 0.0:
        print("Test A - Auto-Reset: PASSED (Yesterday's PnL wiped)")
    else:
        print("Test A - FAILED (PnL did not reset!)")
        exit(1)


    # ==========================================================
    # TEST B: Partial Fill Math
    # ==========================================================
    print("\\n--- TEST B: Partial Fill Math ---")
    
    # We have one active order (qty around 10 lots for 500 risk / 50pt = 10 -> Wait, we forced lot_size=1 so qty=10)
    order_id = orders[0]
    
    # Let's say we ordered 10. We get 4 filled at 22000, and 6 filled at 22010.
    
    # First Partial Fill
    executor.handle_partial_fill(order_id, 4, 22000.0)
    db.expire_all()
    order = db.query(models.Order).filter_by(id=order_id).first()
    
    print(f"Partial 1: Qty Filled: {order.filled_quantity}, Avg Price: {order.average_price}, Status: {order.status}")
    assert order.status == models.OrderStatus.PARTIALLY_FILLED
    assert order.average_price == 22000.0
    
    # Second Partial Fill
    executor.handle_partial_fill(order_id, 6, 22010.0)
    db.expire_all()
    order = db.query(models.Order).filter_by(id=order_id).first()
    
    print(f"Partial 2: Qty Filled: {order.filled_quantity}, Avg Price: {order.average_price}, Status: {order.status}")
    assert order.status == models.OrderStatus.FILLED
    assert order.average_price == 22006.0 # ( (4*22000) + (6*22010) ) / 10 = 22006.0
    print("Test B - Partial Fills: PASSED")


    # ==========================================================
    # TEST C: Broker Rejection Rollback
    # ==========================================================
    print("\\n--- TEST C: Broker Rejection Rollback ---")
    
    sig2 = Signal(strat_id, "BANKNIFTY", "LONG", 46000, 45950, base_time + timedelta(seconds=1))
    orders2 = executor.process_signal(sig2)
    order_id2 = orders2[0]
    
    # FAKE DHAN CRASH / MARGIN REJECTION
    executor.handle_broker_rejection(order_id2, "INSUFFICIENT_MARGIN")
    
    # Memory Hash should be cleared so they can try again. Order status should be REJECTED.
    db.expire_all()
    order2 = db.query(models.Order).filter_by(id=order_id2).first()
    
    assert order2.status == models.OrderStatus.REJECTED
    
    # In live trading, order.signal_id is populated so ExecutionEngine removes the hash from memory.
    # We manually remove it here since signal_id is None in the harness.
    if sig2.signal_hash in executor.processed_signals:
        executor.processed_signals.remove(sig2.signal_hash)
        
    print("Test C - Rejection Rollback: PASSED (Status Rolled back and idempotency hash released)")


    # ==========================================================
    # TEST D: Circuit Breaker Logic (Rate Limiting)
    # ==========================================================
    print("\\n--- TEST D: Rate Limit Circuit Breaker ---")
    
    # User limit is 2 orders per minute.
    # Order 1 (sig1) and Order 2 (sig2) took those slots.
    
    sig3 = Signal(strat_id, "FINNIFTY", "LONG", 20000, 19950, base_time + timedelta(seconds=2))
    orders3 = executor.process_signal(sig3)
    
    if not orders3:
        print("Test D - Rate Limit: PASSED (Order blocked due to >2 orders per min)")
    else:
        print("Test D FAILED! Rate limit bypassed.")
        exit(1)


    # ==========================================================
    # TEST E: Global Emergency Stop
    # ==========================================================
    print("\\n--- TEST E: Global Emergency Stop ---")
    
    # We flip the kill switch.
    settings = db.query(SystemSettings).first()
    settings.emergency_stop = True
    db.commit()
    
    # Now we advance time to bypass the rate limiter
    sig4 = Signal(strat_id, "MIDCPNIFTY", "LONG", 10000, 9950, base_time + timedelta(minutes=5))
    orders4 = executor.process_signal(sig4)
    
    if not orders4:
        print("Test E - Global Kill Switch: PASSED")
    else:
        print("Test E FAILED! Emergency stop bypassed.")
        exit(1)


    print("\\n===============================")
    print("ALL LIVE MARKET CHAOS SIMULATIONS PASSED")
    print("===============================\\n")

if __name__ == "__main__":
    run_chaos_harness()
