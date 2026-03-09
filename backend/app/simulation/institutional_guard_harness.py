import sys
import os
import time as pytime
import threading
from decimal import Decimal
from datetime import datetime, timezone, timedelta, date, time

sys.path.append(os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.db import SessionLocal, Base, engine
from app import models
from app.models import User, Strategy, UserStrategyAllocation, SystemSettings, PortfolioMetrics, Order, TradeFill
from app.engines.strategy_engine import Signal
from app.engines.execution_engine import ExecutionEngine
import logging

logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')

def seed_simulation_db(db):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    settings = SystemSettings(emergency_stop=False)
    db.add(settings)
    
    strat = Strategy(name="TEST_STRATEGY", strategy_type="INTRADAY", risk_profile="LOW")
    db.add(strat)
    db.commit()
    db.refresh(strat)
    
    user = User(
        username="cto_tester", 
        capital_initial=Decimal('50000.0000'), 
        capital_current=Decimal('50000.0000'),
        max_daily_dd=Decimal('5.0000'), 
        max_orders_per_minute=100, 
        max_open_positions=10,
        session_start_time=time(9, 15),
        session_end_time=time(15, 30),
        last_reset_date=date(2026, 1, 1)
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    pm = PortfolioMetrics(user_id=user.id) 
    db.add(pm)
    
    alloc = UserStrategyAllocation(
        user_id=user.id, 
        strategy_id=strat.id, 
        allocation_percentage=Decimal('100.0'),
        risk_per_trade=Decimal('1.0') 
    )
    db.add(alloc)
    db.commit()
    
    return strat.id, user.id


def test_integrity_error_handling(strat_id):
    print("\\n--- TEST 1: DB UniqueConstraint & IntegrityError Racing ---")
    sig = Signal(strat_id, "NIFTY", "LONG", Decimal('22000.00'), Decimal('21950.00'), datetime.now(timezone.utc))
    
    # We will spin up 3 threads that hit the engine exactly at the same time with the IDENTICAL mathematical signal
    def worker():
        db = SessionLocal()
        executor = ExecutionEngine(db)
        # This will race to insert
        executor.process_signal(sig)
        db.close()
        
    threads = []
    for _ in range(3):
        t = threading.Thread(target=worker)
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    db = SessionLocal()
    orders = db.query(Order).filter_by(signal_hash=sig.signal_hash).all()
    if len(orders) == 1:
        print("Test 1 - DB integrity bounds: PASSED (Only 1 order created, others triggered IntegrityError safely)")
        orders[0].status = models.OrderStatus.FILLED
        db.commit()
    else:
        print(f"Test 1 - FAILED (Found {len(orders)} orders for identical hash)")
        exit(1)


def test_rejection_loop_limit(strat_id):
    print("\\n--- TEST 2: Broker Rejection Infinite Loop Prevention ---")
    sig = Signal(strat_id, "NIFTY", "LONG", Decimal('22100.00'), Decimal('22050.00'), datetime.now(timezone.utc) + timedelta(minutes=10))
    db = SessionLocal()
    executor = ExecutionEngine(db)
    
    # 1. Fire signal, order is CREATED
    order_ids = executor.process_signal(sig)
    order_id = order_ids[0]
    
    # 2. Broker REJECTS
    executor.handle_broker_rejection(order_id, "HTTP 400: INSUFFICIENT MARGIN")
    
    db.expire_all()
    o1 = db.query(Order).filter_by(id=order_id).first()
    assert o1.status == models.OrderStatus.REJECTED
    assert o1.rejection_count == 1
    
    # 3. Strategy re-evaluates next tick -> identical signal. System should RECYCLE it.
    order_ids = executor.process_signal(sig)
    db.expire_all()
    o2 = db.query(Order).filter_by(id=order_id).first()
    assert o2.status == models.OrderStatus.CREATED
    assert o2.rejection_count == 1 # Hasn't failed next try yet
    
    # 4. Broker REJECTS again
    executor.handle_broker_rejection(order_id, "HTTP 400: INSUFFICIENT MARGIN")
    db.expire_all()
    o3 = db.query(Order).filter_by(id=order_id).first()
    assert o3.rejection_count == 2
    
    # 5. Retry 3
    executor.process_signal(sig)
    executor.handle_broker_rejection(order_id, "HTTP 400: INSUFFICIENT MARGIN")
    db.expire_all()
    o4 = db.query(Order).filter_by(id=order_id).first()
    assert o4.rejection_count == 3
    assert o4.status == models.OrderStatus.REJECTED
    
    # 6. Strategy re-evaluates tick 4. IT SHOULD BE BLOCKED because rejection_count is 3.
    new_ids = executor.process_signal(sig)
    assert len(new_ids) == 0, "Engine should have blocked a 4th recycle"
    
    print("Test 2 - Broker Loop Breaker: PASSED (Failed 3 times, successfully throttled the 4th)")


def run_checks():
    print("STARTING ALGO INSTITUTIONAL GUARD HARNESS")
    db = SessionLocal()
    strat_id, user_id = seed_simulation_db(db)
    
    test_integrity_error_handling(strat_id)
    test_rejection_loop_limit(strat_id)
    
    print("\\n===============================")
    print("PHASE 3.75: CTO AUDIT PASSED")
    print("===============================\\n")


if __name__ == "__main__":
    run_checks()
