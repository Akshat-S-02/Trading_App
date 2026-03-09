import sys
import os
from decimal import Decimal
from datetime import datetime, timezone, timedelta, date, time

sys.path.append(os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.db import SessionLocal, Base, engine
from app import models
from app.models import User, Strategy, UserStrategyAllocation, SystemSettings, PortfolioMetrics, Order, TradeFill
from app.engines.strategy_engine import Signal
from app.engines.execution_engine import ExecutionEngine
from app.engines.risk_engine import RiskGate
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
        username="risk_desk", 
        capital_initial=Decimal('50000.0000'), 
        capital_current=Decimal('50000.0000'),
        max_daily_dd=Decimal('2.0000'), # 1000 INR Max Loss Allowed
        max_orders_per_minute=10, 
        max_open_positions=10,
        session_start_time=time(9, 15),
        session_end_time=time(15, 30),
        last_reset_date=date(2026, 1, 1)
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # User starts with EXACTLY 500 INR loss already today.
    pm = PortfolioMetrics(user_id=user.id, realized_pnl=Decimal('-500.0000')) 
    db.add(pm)
    
    # User risks 1.1% per trade (550 INR theoretical risk)
    alloc = UserStrategyAllocation(
        user_id=user.id, 
        strategy_id=strat.id, 
        allocation_percentage=Decimal('100.0'),
        risk_per_trade=Decimal('1.1000') 
    )
    db.add(alloc)
    db.commit()
    
    return strat.id, user.id


def run_final_harness():
    print("STARTING FINAL RISK-DESK PRE-API HARNESS")
    db = SessionLocal()
    strat_id, user_id = seed_simulation_db(db)
    
    executor = ExecutionEngine(db)
    base_time = datetime.now(timezone.utc)

    # ==========================================================
    # TEST 1: Forward-Looking DD Block
    # ==========================================================
    print("\\n--- TEST 1: Theoretical DD Blocking ---")
    # Current loss = 500. Limit = 1000. Trade theoretical risk = 550.
    # 500 + 550 = 1050 > 1000. This TRADE MUST BE BLOCKED BEFORE EXECUTING.
    
    sig1 = Signal(strat_id, "NIFTY", "LONG", Decimal('22000.00'), Decimal('21950.00'), base_time)
    
    # We must mock that RiskGate sees today's date so it doesn't auto-reset it to 0
    db.query(User).filter_by(id=user_id).update({"last_reset_date": base_time.date()})
    db.commit()

    orders1 = executor.process_signal(sig1)
    
    if not orders1:
        print("Test 1 - Forward-Looking DD Block: PASSED (Prevented breach before execution)")
    else:
        print("Test 1 - FAILED (Allowed trade through!)")
        exit(1)


    # ==========================================================
    # TEST 2: DB-Level Idempotency Check
    # ==========================================================
    print("\\n--- TEST 2: DB-Enforced Idempotency ---")
    # We reset the user's PnL so they can actually trade
    db.query(PortfolioMetrics).filter_by(user_id=user_id).update({"realized_pnl": Decimal('0.0000')})
    db.commit()
    
    sig2 = Signal(strat_id, "BANKNIFTY", "LONG", Decimal('46000.00'), Decimal('45950.00'), base_time + timedelta(seconds=1))
    
    orders2 = executor.process_signal(sig2)
    assert len(orders2) == 1
    
    # Now simulate a second thread firing the exact same signal object 
    # (Memory cache is gone, it MUST rely on the PostgreSQL Order table)
    orders2_dup = executor.process_signal(sig2)
    
    if not orders2_dup:
        print("Test 2 - DB Idempotency: PASSED (Second process_signal call rejected)")
    else:
        print("Test 2 - FAILED (It executed twice!)")
        exit(1)


    # ==========================================================
    # TEST 3: WebSocket Deduplication and State Constraints
    # ==========================================================
    print("\\n--- TEST 3: WebSocket Fill Reconciliation ---")
    order_id = orders2[0]
    
    # Dhan Webhook sends Fill A
    executor.handle_partial_fill(order_id, 2, Decimal('46000.00'), "DHAN_ID_001")
    
    # Network lag causes Dhan Webhook to send Fill A again!
    executor.handle_partial_fill(order_id, 2, Decimal('46000.00'), "DHAN_ID_001")
    
    db.expire_all()
    order = db.query(models.Order).filter_by(id=order_id).first()
    
    if order.filled_quantity == 2:
        print("Test 3A - Deduplication: PASSED")
    else:
        print(f"Test 3A - FAILED (Filled Qty is {order.filled_quantity})")
        exit(1)
        
    # Send another valid fill to finish it out (Qty 11 remaining is 9)
    executor.handle_partial_fill(order_id, 9, Decimal('46010.00'), "DHAN_ID_002")
    
    db.expire_all()
    order = db.query(models.Order).filter_by(id=order_id).first()
    assert order.status == models.OrderStatus.FILLED
    assert round(order.average_price, 2) == Decimal('46008.18')
    
    # Send anomalous rogue fill when order is ALREADY FILLED
    executor.handle_partial_fill(order_id, 5, Decimal('46015.00'), "DHAN_ID_003")
    
    db.expire_all()
    order = db.query(models.Order).filter_by(id=order_id).first()
    
    if order.filled_quantity == 11 and order.status == models.OrderStatus.FILLED:
         print("Test 3B - State Locking: PASSED")
    else:
         print("Test 3B - FAILED (Order quantities were altered after terminal state!)")
         exit(1)

    print("\\n===============================")
    print("ALL PRODUCTION HARDENINGS PASSED")
    print("===============================\\n")

if __name__ == "__main__":
    run_final_harness()
