import sys
import os
import threading
import time
from decimal import Decimal
from datetime import datetime, timezone, time as dt_time

# Add the parent directory so we can import 'app'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

from app.db import SessionLocal, Base, engine as db_engine
from app.models import User, RiskCategory, UserStrategyAllocation, Order, Strategy, OrderStatus
from app.engines.strategy_engine import Signal
from app.engines.execution_engine import ExecutionEngine
from app.services import dhan_service
import app.services.token_renewal as token_renewal
from app.config import config
import multiprocessing

config.ACCESS_TOKEN = "MOCKED_TOKEN"
token_renewal.is_token_valid = lambda: True

# DB Setup Function
def prepare_db():
    Base.metadata.create_all(bind=db_engine)
    db = SessionLocal()
    
    # Migrations patch for the test
    from sqlalchemy import text
    try:
        db.execute(text("ALTER TABLE portfolio_metrics ADD COLUMN IF NOT EXISTS available_margin NUMERIC(15, 4) DEFAULT 100000;"))
        db.execute(text("ALTER TABLE portfolio_metrics ADD COLUMN IF NOT EXISTS last_margin_sync TIMESTAMP WITH TIME ZONE;"))
        db.execute(text("ALTER TABLE portfolio_metrics ADD COLUMN IF NOT EXISTS consecutive_loss_days INTEGER DEFAULT 0;"))
        db.execute(text("ALTER TABLE portfolio_metrics ADD COLUMN IF NOT EXISTS consecutive_dd_hits INTEGER DEFAULT 0;"))
        db.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS broker_order_id VARCHAR;"))
        db.commit()
    except Exception as e:
        db.rollback()

    existing_user = db.query(User).filter(User.username == 'CrashTester').first()
    if existing_user:
        db.query(UserStrategyAllocation).filter(UserStrategyAllocation.user_id == existing_user.id).delete()
        db.query(Order).filter(Order.user_id == existing_user.id).delete()
        db.query(User).filter(User.id == existing_user.id).delete()
        db.commit()

    user = User(
        username="CrashTester",
        hashed_password="hashed_pw",
        capital_current=100000.0,
        max_daily_dd=2.0,
        max_monthly_dd=6.0,
        risk_category=RiskCategory.HIGH,
        automation_enabled=True,
        max_open_positions=5,
        max_orders_per_minute=10,
        session_start_time=dt_time(0, 0),
        session_end_time=dt_time(23, 59)
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    strat = db.query(Strategy).filter(Strategy.id == 998).first()
    if not strat:
        strat = Strategy(id=998, name="CrashTestStrategy", active=True)
        db.add(strat)
        db.commit()

    alloc = UserStrategyAllocation(
        user_id=user.id,
        strategy_id=998,
        allocation_percentage=100,
        risk_per_trade=1.0
    )
    db.add(alloc)
    db.commit()
    return user

# Worker simulated run
def execute_signal_with_crash_injection(signal_hash, crash_point):
    db = SessionLocal()
    engine = ExecutionEngine(db)
    target_signal = Signal(
        strategy_id=998,
        symbol="CRASH_TEST",
        direction="LONG",
        entry_price=Decimal("150.0"),
        stop_loss=Decimal("140.0"),
        timestamp=datetime.now(timezone.utc)
    )
    target_signal.signal_hash = signal_hash
    
    print(f"\n[Worker] Processing Signal {signal_hash}")
    order_ids = engine.process_signal(target_signal)
    if order_ids:
        print(f"[Worker] Step 1 Complete: Orders inserted into DB. Status = CREATED.")
        
        if crash_point == "BEFORE_API":
            print("[Worker] ! FATAL ! Crashing exactly before Broker API call.")
            os._exit(1) # Brutal kill to simulate segmentation fault / unhandled segfault / power loss
            
        for oid in order_ids:
            order_record = db.query(Order).filter(Order.id == oid).first()
            if order_record:
                print(f"[Worker] Step 2: Hitting Broker API for {order_record.quantity}x {order_record.symbol}...")
                
                # Mock Dhan call
                broker_response = {"status": "success", "order_id": f"LIVE_ID_{time.time()}"}
                
                if crash_point == "AFTER_API":
                    print("[Worker] ! FATAL ! Crashing exactly after successful API firing, but BEFORE local db commit.")
                    os._exit(1)
                    
                order_record.status = OrderStatus.SUBMITTED
                order_record.broker_order_id = broker_response.get("order_id")
                db.commit()
                print(f"[Worker] Step 3 Complete: DB updated. Status = SUBMITTED. OrderID: {order_record.broker_order_id}")
    else:
        print(f"[Worker] Rejected or Duplicate signal.")
    
    db.close()


def run_experiment(crash_point):
    hash_id = f"crash_sig_{crash_point}_{time.time()}"
    p = multiprocessing.Process(target=execute_signal_with_crash_injection, args=(hash_id, crash_point))
    p.start()
    p.join()
    
    # Check what DB state is in right now
    db = SessionLocal()
    order = db.query(Order).filter(Order.signal_hash == hash_id).first()
    if order:
        print(f"--- DB State post-crash ({crash_point}) ---")
        print(f"Status: {order.status}")
        print(f"Broker ID: {order.broker_order_id}")
        if crash_point == "BEFORE_API" and order.status == OrderStatus.CREATED:
            print("[DANGER] System restarted but order is left stranded in CREATED forever.")
        elif crash_point == "AFTER_API" and order.broker_order_id is None:
            print("[CATASTROPHIC] System restarted. Live order exists in Market, but DB has no record of the broker ID and status is still CREATED. Double Execution inevitable on retry.")
    else:
        print("No order found.")
    db.close()

if __name__ == '__main__':
    prepare_db()
    
    print("\n--- TEST 1: Crash between DB insert and Broker call ---")
    run_experiment("BEFORE_API")
    
    print("\n--- TEST 2: Crash AFTER Broker call but BEFORE DB commit ---")
    run_experiment("AFTER_API")
