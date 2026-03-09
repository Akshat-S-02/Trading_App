import sys
import os
import time as pytime
from decimal import Decimal
from datetime import datetime, timezone, timedelta, date, time
import random

sys.path.append(os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.db import SessionLocal, Base, engine
from app import models
from app.models import User, Strategy, UserStrategyAllocation, SystemSettings, PortfolioMetrics, Order, TradeFill
from app.engines.strategy_engine import Signal
from app.engines.execution_engine import ExecutionEngine
from app.engines.risk_engine import RiskGate
from app.broker.dhan import DhanBrokerClient
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

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
        username="failure_tester", 
        capital_initial=Decimal('50000.0000'), 
        capital_current=Decimal('50000.0000'),
        max_daily_dd=Decimal('5.0000'), 
        max_orders_per_minute=10, 
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


class FlakyDhanBroker(DhanBrokerClient):
    """
    Simulates token expiries, rate limits, and 500 server errors.
    """
    def __init__(self, failure_mode="500"):
        super().__init__("MOCK", "MOCK")
        self.failure_mode = failure_mode
        self.calls = 0

    def place_order(self, symbol: str, direction: str, quantity: int, price: Decimal, order_type: str = "LIMIT") -> dict:
        self.calls += 1
        
        if self.failure_mode == "500":
            # Simulate Dhan server going down hard
            raise Exception("HTTP 500: Internal Server Error on Dhan HQ")
            
        elif self.failure_mode == "401":
            # Token expiry
            raise Exception("HTTP 401: Unauthorized. Token Expired.")
            
        elif self.failure_mode == "429":
            # Rate limit
            raise Exception("HTTP 429: Too Many Requests.")
            
        else:
            return super().place_order(symbol, direction, quantity, price, order_type)

def simulate_engine_rest_call(executor: ExecutionEngine, broker: FlakyDhanBroker, order_id: int):
    """
    Simulates the async worker picking up the DB order and firing the REST call.
    """
    db = executor.db
    order = db.query(Order).filter_by(id=order_id).first()
    
    if not order:
        return
        
    order.status = models.OrderStatus.SUBMITTED
    order.order_submission_time = datetime.now(timezone.utc)
    db.commit()
    
    try:
        res = broker.place_order(order.symbol, order.direction.value, order.quantity, order.entry_price)
        order.status = models.OrderStatus.ACKNOWLEDGED
        order.broker_ack_time = datetime.now(timezone.utc)
        db.commit()
    except Exception as e:
        db.rollback()
        # Trigger Execution Engine rollback routine
        executor.handle_broker_rejection(order_id, str(e))


def run_failure_harness():
    print("STARTING API FAILURE HARNESS")
    db = SessionLocal()
    strat_id, user_id = seed_simulation_db(db)
    
    executor = ExecutionEngine(db)
    base_time = datetime.now(timezone.utc)

    # ==========================================================
    # TEST 1: HTTP 500 Dhan Internal Server Error
    # ==========================================================
    print("\\n--- TEST 1: HTTP 500 Trapping ---")
    broker500 = FlakyDhanBroker(failure_mode="500")
    
    sig1 = Signal(strat_id, "RELIANCE", "LONG", Decimal('1000.00'), Decimal('990.00'), base_time)
    orders1 = executor.process_signal(sig1)
    order_id = orders1[0]
    
    simulate_engine_rest_call(executor, broker500, order_id)
    
    db.expire_all()
    order = db.query(Order).filter_by(id=order_id).first()
    
    if order.status == models.OrderStatus.REJECTED and order.signal_hash is None:
        print("Test 1 - HTTP 500 Graceful Handle: PASSED (Order REJECTED, Signal Hash freed)")
    else:
        print(f"Test 1 - FAILED (State is {order.status}, Hash is {order.signal_hash})")
        exit(1)


    # ==========================================================
    # TEST 2: Double-Try on Transient Failure Matrix
    # ==========================================================
    print("\\n--- TEST 2: Successful Retry After Token Expiry ---")
    # Because signal_hash was freed, the Strategy can re-evaluate on the next tick and try again.
    
    broker401 = FlakyDhanBroker(failure_mode="401")
    sig2 = Signal(strat_id, "RELIANCE", "LONG", Decimal('1000.00'), Decimal('990.00'), base_time + timedelta(minutes=1))
    
    # Attempt 1 -> 401
    orders2 = executor.process_signal(sig2)
    order2_id = orders2[0]
    simulate_engine_rest_call(executor, broker401, order2_id)
    
    # Now simulate token refresh logic running in background ...
    broker401.failure_mode = "SUCCESS" 
    
    # Because Attempt 1 failed and freed the hash, Strategy firing it again on tick 2 works
    orders3 = executor.process_signal(sig2)
    order3_id = orders3[0]
    simulate_engine_rest_call(executor, broker401, order3_id)
    
    db.expire_all()
    o2 = db.query(Order).filter_by(id=order2_id).first()
    o3 = db.query(Order).filter_by(id=order3_id).first()
    
    if o2.status == models.OrderStatus.REJECTED and o3.status == models.OrderStatus.ACKNOWLEDGED:
        print("Test 2 - Idempotency Token Recovery: PASSED (Orphan hash was cleared, retry succeeded)")
    else:
        print(f"Test 2 - FAILED (O2: {o2.status}, O3: {o3.status})")
        exit(1)

    print("\\n===============================")
    print("PHASE 3.5: ORPHAN LOCK PREVENTION AND FAILURE HANDLING PASSED")
    print("===============================\\n")

if __name__ == "__main__":
    run_failure_harness()
