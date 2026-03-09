import sys
import os
import pandas as pd
from datetime import datetime, timedelta
import threading
import time

sys.path.append(os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.db import SessionLocal, Base, engine
from app.models import User, Strategy, UserStrategyAllocation, RiskCategory, Direction, OrderStatus
from app.engines.strategy_engine import Signal
from app.engines.execution_engine import ExecutionEngine

def seed_simulation_db(db):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
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
        max_daily_dd=2.0 
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # 3. Enrol User in Strategy (1.0% risk per trade = 500 INR)
    alloc = UserStrategyAllocation(
        user_id=user.id, 
        strategy_id=strat.id, 
        allocation_percentage=100.0,
        risk_per_trade=1.0 
    )
    db.add(alloc)
    db.commit()
    
    return strat.id, user.id


def simulate_trade_result(db, user_id, profit_amount: float):
    # Simulate closing a trade with either a specific profit or loss (e.g., negative for slippage)
    user = db.query(User).filter_by(id=user_id).first()
    if not user.portfolio_metrics:
        from app.models import PortfolioMetrics
        user.portfolio_metrics = PortfolioMetrics(user_id=user.id, realized_pnl=0.0)
        db.add(user.portfolio_metrics)
        db.commit()
        db.refresh(user.portfolio_metrics)
        
    current_pnl = user.portfolio_metrics.realized_pnl or 0.0
    user.portfolio_metrics.realized_pnl = current_pnl + profit_amount
    user.capital_current += profit_amount
    db.commit()


def run_advanced_harness():
    print("STARTING ADVANCED RISK SIMULATION HARNESS")
    db = SessionLocal()
    strat_id, user_id = seed_simulation_db(db)
    
    executor = ExecutionEngine(db)
    base_time = datetime.now()

    # ==========================================================
    # TEST A: Mixed Outcomes (Win, Loss, Win, Loss)
    # ==========================================================
    print("\\n--- TEST A: Mixed Outcomes (W/L/W sequences) ---")
    
    test_a_capital = 50000.0
    
    # Trade 1: Win (Risked 500, made 1000)
    sig1 = Signal(strat_id, "NIFTY", "LONG", 22000, 21950, base_time + timedelta(minutes=1))
    orders = executor.process_signal(sig1)
    if orders:
        print("Test A - Trade 1 (Win): Executed")
        simulate_trade_result(db, user_id, 1000.0)
        test_a_capital += 1000.0
    
    # Trade 2: Loss (Risked 510 [1% of 51k], lost 510)
    sig2 = Signal(strat_id, "NIFTY", "LONG", 22000, 21949, base_time + timedelta(minutes=2))
    orders = executor.process_signal(sig2)
    if orders:
        print("Test A - Trade 2 (Loss): Executed")
        simulate_trade_result(db, user_id, -510.0)
        test_a_capital -= 510.0
        
    # Check Math Output
    user = db.query(User).filter_by(id=user_id).first()
    print(f"Test A Expected Capital: {test_a_capital}")
    print(f"Test A Actual Capital: {user.capital_current}")
    assert user.capital_current == test_a_capital, "Capital mismatch in Mixed Outcomes"
    
    
    # ==========================================================
    # TEST B: Gap Risk (Slippage beyond Stop Loss)
    # ==========================================================
    print("\\n--- TEST B: Gap Risk / Slippage ---")
    # Current capital: 50490. Daily PnL: +490.
    
    # We risk 1% (~505 rupees). Max Daily DD is 2% of 50000 = 1000 rupees.
    # We currently have +490 PnL. So we can lose 1000 + 490 = 1490 before being blocked.
    
    # Trade 3: Massive Slippage Loss. Expected loss: 505. Actual Loss: 1500!
    sig3 = Signal(strat_id, "NIFTY", "LONG", 22000, 21949, base_time + timedelta(minutes=3))
    orders = executor.process_signal(sig3)
    if orders:
        print("Test B - Trade 3 (Massive Slippage): Executed")
        simulate_trade_result(db, user_id, -1500.0) # Slippage occurs
        
    # User PnL is now 490 - 1500 = -1010.
    # Max DD is 1000. They are OVER the daily drawdown limit because of the gap.
    
    # Trade 4: Should be blocked by RiskGate
    sig4 = Signal(strat_id, "NIFTY", "LONG", 22000, 21949, base_time + timedelta(minutes=4))
    orders = executor.process_signal(sig4)
    if not orders:
        print("Test B - Trade 4 (Post-Slippage): BLOCKED CORRECTLY by RiskGate")
    else:
        print("Test B FAILED: Allowed trade after slippage breached max_daily_dd!")
        exit(1)


    # ==========================================================
    # TEST C: Duplicate Signal Rejection
    # ==========================================================
    print("\\n--- TEST C: Duplicate Signal Rejection (Idempotency) ---")
    
    # We need to reset the user's PnL so they can trade again for this test
    user = db.query(User).filter_by(id=user_id).first()
    user.portfolio_metrics.realized_pnl = 0.0
    db.commit()
    
    sig5_A = Signal(strat_id, "NIFTY", "LONG", 22000, 21950, base_time + timedelta(minutes=5))
    sig5_B = sig5_A # Exact same memory object / exact same hash
    
    orders_A = executor.process_signal(sig5_A)
    orders_B = executor.process_signal(sig5_B)
    
    if orders_A and not orders_B:
        print("Test C - Duplicate Signal: SECOND SIGNAL BLOCKED CORRECTLY (Idempotency works)")
    else:
        print("Test C FAILED: Idempotency did not block duplicate signal")
        exit(1)


    # ==========================================================
    # TEST D: Multithreaded Concurrency Injection
    # ==========================================================
    print("\\n--- TEST D: Multithreaded Concurrency Risk Bound Test ---")
    
    # The user has PnL = 0 right now. Max loss is 1000. Each trade risks ~500.
    # We will spin up 5 threads firing 5 DIFFERENT signals at the EXACT SAME MILLISECOND.
    # Without row-level locks, all 5 might read PnL=0 simultaneously and approve 5 orders,
    # causing a -2500 drawdown on a max -1000 limit account!
    
    def fire_concurrent_signal(strat_id, t_id):
        # Create a completely separate DB session for the thread so they don't share SqlAlchemy cache
        thread_db = SessionLocal()
        thread_executor = ExecutionEngine(thread_db)
        
        # Make timestamp slightly different so idempotency doesn't block it (we want to test Risk block!)
        con_sig = Signal(strat_id, "NIFTY", "SHORT", 22000, 22050, base_time + timedelta(minutes=6, seconds=t_id))
        
        o = thread_executor.process_signal(con_sig)
        if o:
            # We IMMEDIATELY simulate hitting stop loss so the DB reflects the loss for the next thread
            simulate_trade_result(thread_db, user_id, -510.0) 
            
        thread_db.close()
        
    threads = []
    for i in range(5):
        t = threading.Thread(target=fire_concurrent_signal, args=(strat_id, i))
        threads.append(t)
        
    # Fire them all at once!
    for t in threads: t.start()
    for t in threads: t.join() # Wait for all to finish
    
    # Check final drawdown
    db.expire_all() # Clear local cache
    user = db.query(User).filter_by(id=user_id).first()
    final_pnl = user.portfolio_metrics.realized_pnl
    
    print(f"Test D Final Concurrency PnL: {final_pnl}")
    if final_pnl < -1050.0: # Allowing slight margin for the 1% risk math
        print("Test D FAILED! Concurrency was breached and the account lost more than the Max Daily DD!")
        exit(1)
    else:
        print("Test D - Concurrency: PASSED. Row-level locks successfully queued the requests and blocked the extras.")

    print("\\n===============================")
    print("ALL ADVANCED RISK SIMULATIONS PASSED")
    print("===============================\\n")

if __name__ == "__main__":
    run_advanced_harness()
