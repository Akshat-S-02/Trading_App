import sys
import os
import time
from decimal import Decimal
from datetime import datetime, timezone, time as dt_time

# Add the parent directory so we can import 'app'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

from app.db import SessionLocal, Base, engine as db_engine
from app.models import User, RiskCategory, UserStrategyAllocation, Order, Strategy, OrderStatus, OutboxEvent, OutboxEventStatus
from app.engines.strategy_engine import Signal
from app.engines.execution_engine import ExecutionEngine
from app.workers.outbox_worker import OutboxWorker
from app.services import dhan_service
import app.services.token_renewal as token_renewal
from app.config import config
import multiprocessing

config.ACCESS_TOKEN = "MOCKED_TOKEN"
token_renewal.is_token_valid = lambda: True

# Patch the mock to simulate a Dhan crash exactly inside
def mock_place_order(symbol, qty, direction, price, order_type, correlation_id):
    if os.getenv("CRASH_DURING_API") == "1":
        print(f"[Broker API] ! NETWORK CORD PULLED ! Raising generic TimeoutError over the wire for {correlation_id}.")
        raise TimeoutError("Simulated Network Drop from Dhan servers.")
    
    if os.getenv("CRASH_AFTER_API") == "1":
        print(f"[Broker API] Returning success, but preparing fatal process death... {correlation_id}")
        return {"status": "success", "order_id": f"LIVE_ID_{correlation_id}_123"}
        
    print(f"[Broker API] Order accepted. {correlation_id}")
    return {"status": "success", "order_id": f"LIVE_ID_{correlation_id}_123"}

dhan_service.place_order = mock_place_order

def prepare_db():
    Base.metadata.create_all(bind=db_engine)
    db = SessionLocal()
    
    existing_user = db.query(User).filter(User.username == 'OutboxTester').first()
    if existing_user:
        db.query(OutboxEvent).delete()
        db.query(UserStrategyAllocation).filter(UserStrategyAllocation.user_id == existing_user.id).delete()
        db.query(Order).filter(Order.user_id == existing_user.id).delete()
        db.query(User).filter(User.id == existing_user.id).delete()
        db.commit()

    user = User(
        username="OutboxTester",
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

def step_1_generate_signal_and_enqueue(signal_hash):
    db = SessionLocal()
    engine = ExecutionEngine(db)
    target_signal = Signal(
        strategy_id=998,
        symbol="OUTBOX_TEST",
        direction="LONG",
        entry_price=Decimal("150.0"),
        stop_loss=Decimal("140.0"),
        timestamp=datetime.now(timezone.utc)
    )
    target_signal.signal_hash = signal_hash
    
    print(f"\n[Strategy Engine] Generating Signal {signal_hash}...")
    order_ids = engine.process_signal(target_signal)
    
    if order_ids:
        print(f"[Execution Engine] Signal processed transactionally.")
        for oid in order_ids:
            order = db.query(Order).filter(Order.id == oid).first()
            event = db.query(OutboxEvent).filter(OutboxEvent.order_id == oid).first()
            print(f"[Execution Engine] Local DB -> Order {order.id} is {order.status.name}. OutboxEvent {event.id} is {event.status.name}. Broker NOT called yet.")
    
    db.close()

def step_2_outbox_worker_crash(crash_type):
    db = SessionLocal()
    if crash_type == "DURABILITY":
        # Simulating process death immediately after waking up, before touching Dhan
        print("[Outbox Worker] Waking up to process Outbox... OH NO A CPU FIRE.")
        os._exit(1)
        
    elif crash_type == "AFTER_API_NATIVE":
        os.environ["CRASH_AFTER_API"] = "1"
        worker = OutboxWorker(db)
        print("[Outbox Worker] Waking up. Processing...")
        # We need to manually simulate the crash since os._exit inside worker breaks test flow.
        # So we inject a mock bug.
        
        # Pull the task exactly like the worker would
        event = db.query(OutboxEvent).filter(OutboxEvent.status == OutboxEventStatus.PENDING).first()
        if event:
            payload = event.payload
            resp = mock_place_order(payload['symbol'], payload['qty'], payload['direction'], payload['price'], payload['order_type'], payload['correlation_id'])
            
            # CRASH EXACTLY HERE before DB write
            print("[Outbox Worker] Received API SUCCESS. OOM Killer terminating process before db.commit().")
            os._exit(1)

def run_test_1_durability():
    print("\n--- TEST 1: Worker crashes before touching the network ---")
    sig_hash = f"sig_durability_{time.time()}"
    step_1_generate_signal_and_enqueue(sig_hash)
    
    p = multiprocessing.Process(target=step_2_outbox_worker_crash, args=("DURABILITY",))
    p.start()
    p.join()
    
    # Observe Recovery State
    db = SessionLocal()
    event = db.query(OutboxEvent).filter(OutboxEvent.status == OutboxEventStatus.PENDING).first()
    if event:
        print(f"[Recovery Checker] Found PENDING Outbox Event {event.id}. No orders stranded in abyss.")
        print(f"[Recovery Checker] Booting fresh worker to process it safely...")
        worker = OutboxWorker(db)
        worker.process_pending_events()
        
        order = db.query(Order).filter(Order.id == event.order_id).first()
        print(f"[Final DB State] Order Status: {order.status.name}, Broker ID: {order.broker_order_id}")
    else:
        print("FAILED to retain event.")
    db.close()


def run_test_2_network_death_retry():
    print("\n--- TEST 2: Network Timeout/500 (Broker Dead) -> Exponential Backoff ---")
    sig_hash = f"sig_timeout_{time.time()}"
    step_1_generate_signal_and_enqueue(sig_hash)
    
    os.environ["CRASH_DURING_API"] = "1"
    
    db = SessionLocal()
    worker = OutboxWorker(db)
    print("\n[Outbox Worker] Attempt 1...")
    worker.process_pending_events()
    
    event = db.query(OutboxEvent).first()
    print(f"[DB State] Event Status is {event.status.name}. Retry Count: {event.retry_count}. Next Attempt: {event.next_attempt_at}")
    
    print("\n[Outbox Worker] Removing network error environment variable. Waiting and retrying...")
    os.environ["CRASH_DURING_API"] = "0"
    
    # Force bypass of the time lock for the test
    event.next_attempt_at = datetime.now(timezone.utc)
    db.commit()
    
    worker.process_pending_events()
    
    db.refresh(event)
    order = db.query(Order).filter(Order.id == event.order_id).first()
    print(f"[Final DB State] Event is {event.status.name}. Order Status: {order.status.name}, Broker ID: {order.broker_order_id}")
    db.close()


if __name__ == '__main__':
    prepare_db()
    
    run_test_1_durability()
    
    # clear db for test 2
    SessionLocal().query(OutboxEvent).delete()
    SessionLocal().commit()
    
    run_test_2_network_death_retry()
