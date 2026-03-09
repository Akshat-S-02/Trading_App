import sys
import os
import threading
import time
from unittest import mock
from decimal import Decimal
from datetime import datetime, timezone, time

# Add the parent directory so we can import 'app'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

from app.db import SessionLocal, Base, engine as db_engine
from app.models import User, RiskCategory, UserStrategyAllocation, Order
from app.engines.strategy_engine import Signal
from app.engines.execution_engine import ExecutionEngine
from app.services import dhan_service

# Ensure DB is clean for the test
Base.metadata.create_all(bind=db_engine)

# DB Setup
db = SessionLocal()

# Migrations patch for the test
from sqlalchemy import text
try:
    db.execute(text("ALTER TABLE portfolio_metrics ADD COLUMN IF NOT EXISTS available_margin NUMERIC(15, 4) DEFAULT 100000;"))
    db.execute(text("ALTER TABLE portfolio_metrics ADD COLUMN IF NOT EXISTS last_margin_sync TIMESTAMP WITH TIME ZONE;"))
    db.execute(text("ALTER TABLE portfolio_metrics ADD COLUMN IF NOT EXISTS consecutive_loss_days INTEGER DEFAULT 0;"))
    db.execute(text("ALTER TABLE portfolio_metrics ADD COLUMN IF NOT EXISTS consecutive_dd_hits INTEGER DEFAULT 0;"))
    db.commit()
except Exception as e:
    db.rollback()
    print(f"Migration patch skipped or failed: {e}")

# 1. Clean existing test users if any
existing_user = db.query(User).filter(User.username == 'RaceTester').first()
if existing_user:
    db.query(UserStrategyAllocation).filter(UserStrategyAllocation.user_id == existing_user.id).delete()
    db.query(Order).filter(Order.user_id == existing_user.id).delete()
    db.query(User).filter(User.id == existing_user.id).delete()
    db.commit()

user = User(
    username="RaceTester",
    hashed_password="hashed_pw",
    capital_current=100000.0,
    max_daily_dd=2.0,
    max_monthly_dd=6.0,
    risk_category=RiskCategory.HIGH,
    automation_enabled=True,
    max_open_positions=5,
    max_orders_per_minute=10,
    session_start_time=time(0, 0),
    session_end_time=time(23, 59)
)
db.add(user)
db.commit()
db.refresh(user)

from app.models import Strategy

# 2. Create target strategy if it doesn't exist
strat = db.query(Strategy).filter(Strategy.id == 999).first()
if not strat:
    strat = Strategy(id=999, name="RaceTestStrategy", active=True)
    db.add(strat)
    db.commit()

alloc = UserStrategyAllocation(
    user_id=user.id,
    strategy_id=999,
    allocation_percentage=100,
    risk_per_trade=1.0
)
db.add(alloc)
db.commit()

# Ensure SystemSettings is allowed
from app.models import SystemSettings
sys_sets = db.query(SystemSettings).first()
if sys_sets:
    sys_sets.emergency_stop = False
    db.commit()

# Mock Token & Health Guard
from app.config import config
config.ACCESS_TOKEN = "MOCKED_TOKEN"

import app.services.token_renewal as token_renewal
token_renewal.is_token_valid = lambda: True

# Mock place_order
api_calls = []

def mock_place_order(symbol, qty, direction, price, order_type):
    api_calls.append({"symbol": symbol, "qty": qty})
    import time as time_module
    print(f"   [MOCK API CALLED] Thread {threading.current_thread().name} placed live order for {qty}x {symbol}")
    return {"status": "success", "order_id": f"LIVE_ID_{time_module.time()}"}

dhan_service.place_order = mock_place_order
db.close()

# The unique identical Signal
target_signal = Signal(
    strategy_id=999,
    symbol="RACER",
    direction="LONG",
    entry_price=Decimal("100.0"),
    stop_loss=Decimal("90.0"),
    timestamp=datetime.now(timezone.utc)
)

print(f"[START] Generated unique Signal Hash: {target_signal.signal_hash}")

# Worker function
def worker_task(barrier):
    # Wait for the other thread so they fire EXACTLY at the same time
    barrier.wait()
    
    local_db = SessionLocal()
    engine = ExecutionEngine(local_db)
    
    print(f"[{threading.current_thread().name}] Firing process_signal...")
    try:
        order_ids = engine.process_signal(target_signal)
        if order_ids:
            for oid in order_ids:
                order_record = local_db.query(Order).filter(Order.id == oid).first()
                if order_record:
                    # Explicit API Call Simulation as built into Execution Worker
                    resp = dhan_service.place_order(
                        symbol=order_record.symbol,
                        qty=order_record.quantity,
                        direction=order_record.direction.value,
                        price=float(order_record.entry_price),
                        order_type="LIMIT"
                    )
                    order_record.broker_order_id = resp.get("order_id")
                    local_db.commit()
        else:
            print(f"[{threading.current_thread().name}] Signal rejected or duplicated. No order IDs returned.")
    except Exception as e:
        print(f"[{threading.current_thread().name}] CRASH: {e}")
    finally:
        local_db.close()


print("\n--- INITIATING DOUBLE WORKER RACE TEST ---")

# Setup Barrier for 2 threads
barrier = threading.Barrier(2)

t1 = threading.Thread(target=worker_task, args=(barrier,), name="Worker-A")
t2 = threading.Thread(target=worker_task, args=(barrier,), name="Worker-B")

t1.start()
t2.start()

t1.join()
t2.join()

print("\n--- RACE TEST COMPLETE ---")

db = SessionLocal()
total_orders = db.query(Order).filter(Order.signal_hash == target_signal.signal_hash).all()

print(f"Total DB Orders generated for signal: {len(total_orders)}")
print(f"Total Dhan API calls made: {len(api_calls)}")

if len(total_orders) == 1 and len(api_calls) == 1:
    print("[PASS] Idempotency constraint protected the API call.")
else:
    print("[FAIL] Concurrency broke the boundaries!")

db.close()
