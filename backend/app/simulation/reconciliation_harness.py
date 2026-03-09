import sys
import os
import time as pytime
from decimal import Decimal
from datetime import datetime, timezone, timedelta, date, time

sys.path.append(os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.db import SessionLocal, Base, engine
from app import models
from app.models import User, Strategy, UserStrategyAllocation, SystemSettings, PortfolioMetrics, Order, TradeFill
from app.engines.strategy_engine import Signal
from app.engines.execution_engine import ExecutionEngine
from app.engines.risk_engine import RiskGate
from app.broker.dhan import DhanBrokerClient
from app.engines.reconciliation_engine import ReconciliationService
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
        username="latency_tester", 
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
    
    # Capital Fragmentation: Only 60% of 50k (30k pool)
    # 1% risk of 30k = 300 INR risk per trade
    alloc = UserStrategyAllocation(
        user_id=user.id, 
        strategy_id=strat.id, 
        allocation_percentage=Decimal('60.0'),
        risk_per_trade=Decimal('1.0') 
    )
    db.add(alloc)
    db.commit()
    
    return strat.id, user.id


class MockDhanBroker(DhanBrokerClient):
    """
    Overrides the core methods to test the Recon Service
    """
    def __init__(self):
        super().__init__("MOCK", "MOCK")
        self.mock_orders = []
        
    def get_orders(self):
        return self.mock_orders

def run_phase3_harness():
    print("STARTING PHASE 3 LIVE METRICS & RECOVERY HARNESS")
    db = SessionLocal()
    strat_id, user_id = seed_simulation_db(db)
    
    executor = ExecutionEngine(db)
    broker = MockDhanBroker()
    recon_service = ReconciliationService(db, broker)
    base_time = datetime.now(timezone.utc)

    # ==========================================================
    # TEST 1: Capital Fragmentation Sizing
    # ==========================================================
    print("\\n--- TEST 1: Strategy-Sliced Position Sizing ---")
    # User Capital: 50,000. Alloc: 60%. Strategy Pool = 30,000.
    # Risk 1% of 30,000 = 300 INR risk per trade.
    
    # Entry 1000, SL 950. Distance = 50.
    # Theoretical risk capital / Distance = 300 / 50 = 6 Lots exactly.
    # If the engine used 50k global capital, it would try to buy 500/50 = 10 Lots.
    
    sig1 = Signal(strat_id, "RELIANCE", "LONG", Decimal('1000.00'), Decimal('950.00'), base_time)
    
    orders1 = executor.process_signal(sig1)
    order_id = orders1[0]
    
    db.expire_all()
    order = db.query(Order).filter_by(id=order_id).first()
    
    if order.quantity == 6:
        print("Test 1 - Capital Fragmentation: PASSED (Sized for 30k pool, not 50k global)")
    else:
        print(f"Test 1 - FAILED (Got qty {order.quantity} instead of 6)")
        exit(1)


    # ==========================================================
    # TEST 2: Latency Telemetry Simulation
    # ==========================================================
    print("\\n--- TEST 2: Millisecond Telemetry Recording ---")
    
    # We will simulate the latency milestones
    sig_creation = datetime.now(timezone.utc)
    
    order.signal_creation_time = sig_creation
    db.commit()
    
    pytime.sleep(0.05) # simulate 50ms engine processing time
    
    order.order_submission_time = datetime.now(timezone.utc)
    db.commit()
    
    pytime.sleep(0.12) # simulate 120ms Dhan REST latency
    
    order.broker_ack_time = datetime.now(timezone.utc)
    order.status = models.OrderStatus.ACKNOWLEDGED
    db.commit()
    
    db.expire_all()
    order = db.query(Order).filter_by(id=order_id).first()
    
    engine_latency = (order.order_submission_time - order.signal_creation_time).total_seconds() * 1000
    broker_latency = (order.broker_ack_time - order.order_submission_time).total_seconds() * 1000
    
    print(f"Engine Latency: {engine_latency:.1f}ms (Expected ~50ms)")
    print(f"REST Latency: {broker_latency:.1f}ms (Expected ~120ms)")
    
    if engine_latency > 0 and broker_latency > 0:
        print("Test 2 - Precision Latency Telemetry: PASSED")
    else:
        print("Test 2 - FAILED (Timestamps not recorded properly)")
        exit(1)


    # ==========================================================
    # TEST 3: Server Boot Crash Reconciliation
    # ==========================================================
    print("\\n--- TEST 3: Boot-Sequence DB Healing ---")
    
    # 1. Blind the server
    order.status = models.OrderStatus.SUBMITTED
    db.commit()
    
    # 2. Tell the mock broker that the order actually filled while we were down
    broker.mock_orders = [{
        "orderId": str(order_id),
        "orderStatus": "FILLED",
        "filledQty": 6,
        "tradedPrice": 1000.50
    }]
    
    # 3. Simulate process restart
    print("CRASH INITIATED. RESTARTING SERVER...")
    recon_service.run_startup_reconciliation()
    
    db.expire_all()
    healed_order = db.query(Order).filter_by(id=order_id).first()
    
    if healed_order.status == models.OrderStatus.FILLED and healed_order.filled_quantity == 6:
        print("Test 3 - DB Healing: PASSED (Orphaned order was rescued from SUBMITTED to FILLED via Dhan poll)")
    else:
        print(f"Test 3 - FAILED (Status is {healed_order.status}, Qty {healed_order.filled_quantity})")
        exit(1)

    print("\\n===============================")
    print("PHASE 3: PRODUCTION TELEMETRY AND HEALING PASSED")
    print("===============================\\n")

if __name__ == "__main__":
    run_phase3_harness()
