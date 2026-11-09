import sys
import os
import sqlalchemy
from decimal import Decimal
from datetime import datetime, timezone
import zoneinfo

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.db import require_test_db; require_test_db()  # this script deletes data
from app.db import SessionLocal
from app.models import User, Order, OrderStatus, Direction, SystemSettings
from app.engines.execution_engine import ExecutionEngine
from app.engines.strategy_engine import Signal
from app.workers.outbox_worker import OutboxWorker
from app.core.tick_store import save_tick

def test_outbox_guard():
    print("--- Testing Outbox Worker Crash Guard ---")
    db = SessionLocal()
    worker = OutboxWorker(db)
    
    # Monkeypatch to force crash
    original_retry = worker._schedule_retry
    def broken_retry(*args, **kwargs):
        raise Exception("Simulated DB connection failure inside _schedule_retry")
        
    worker._schedule_retry = broken_retry
    
    # Create fake event
    from app.models import OutboxEvent, OutboxEventStatus
    
    tester = db.query(User).filter(User.username == "worker_tester").first()
    if not tester:
        tester = User(username="worker_tester")
        db.add(tester)
        db.commit()
        
    dummy_o = Order(user_id=tester.id, symbol="DUMMY", direction=Direction.LONG, quantity=1, entry_price=Decimal('1.0'))
    db.add(dummy_o)
    db.commit()
    
    evt = OutboxEvent(order_id=dummy_o.id, status=OutboxEventStatus.PENDING)
    db.add(evt)
    db.commit()
    
    print("Firing process_pending_events (expecting FATAL wrapper error, not complete death)...")
    worker.process_pending_events()
    
    # Restore
    db.query(OutboxEvent).filter(OutboxEvent.order_id == dummy_o.id).delete()
    db.query(Order).filter(Order.id == dummy_o.id).delete()
    db.commit()
    db.close()
    print("Passed: Worker survived the double-fault.\n")

def test_risk_snapshot():
    print("--- Testing Risk Engine Floating PNL Guard ---")
    db = SessionLocal()
    
    user = db.query(User).filter(User.username == "algo1").first()
    if not user:
        user = User(username="algo1", automation_enabled=True, capital_current=Decimal('50000.0'))
        db.add(user)
        db.commit()
        db.refresh(user)
        
    engine = ExecutionEngine(db)
    valid_time = datetime.now(zoneinfo.ZoneInfo("Asia/Kolkata")).replace(hour=10, minute=0, second=0)
    sig1 = Signal(strategy_id=1, symbol="RELIANCE", direction="LONG", entry_price=Decimal('2500.0'), stop_loss=Decimal('2450.0'), timestamp=valid_time)
    settings = db.query(SystemSettings).first()
    
    # Clean previous test states
    db.query(Order).filter(Order.symbol.in_(["TEST_MISS", "TEST_LOSS", "TEST_WIN"])).delete()
    db.commit()
    
    # TEST A: Missing CMP
    o_miss = Order(user_id=user.id, symbol="TEST_MISS", direction=Direction.LONG, quantity=100, filled_quantity=100, entry_price=Decimal('100.0'), average_price=Decimal('100.0'), status=OrderStatus.FILLED)
    db.add(o_miss)
    db.commit()
    print("Test A: Submitting new signal with Missing CMP open position...")
    snap_a = engine._build_portfolio_snapshot(user.id)
    approved_a = RiskGate.validate_risk(db, user, settings, sig1, snap_a, valid_time)
    print(f"Snapshot A flags: {snap_a}")
    print(f"Missing CMP Approved? {approved_a} (Expected: False)\n")
    db.delete(o_miss)
    db.commit()
    
    # TEST B: Floating Loss hitting Max DD
    o_loss = Order(user_id=user.id, symbol="TEST_LOSS", direction=Direction.LONG, quantity=100, filled_quantity=100, entry_price=Decimal('100.0'), average_price=Decimal('100.0'), status=OrderStatus.FILLED)
    db.add(o_loss)
    db.commit()
    save_tick("TEST_LOSS", 50.0) # Down 5000 on 50k max capital (10% DD)
    print("Test B: Providing CMP=50 (Floating loss = 5000) which easily triggers 2% max DD...")
    snap_b = engine._build_portfolio_snapshot(user.id)
    approved_b = RiskGate.validate_risk(db, user, settings, sig1, snap_b, valid_time)
    print(f"Snapshot B flags: {snap_b}")
    print(f"Floating DD Crash Approved? {approved_b} (Expected: False)\n")
    db.delete(o_loss)
    db.commit()
    
    # TEST C: Floating Win
    o_win = Order(user_id=user.id, symbol="TEST_WIN", direction=Direction.LONG, quantity=100, filled_quantity=100, entry_price=Decimal('100.0'), average_price=Decimal('100.0'), status=OrderStatus.FILLED)
    db.add(o_win)
    db.commit()
    save_tick("TEST_WIN", 150.0) # Up 5000
    print("Test C: Providing CMP=150 (Floating win = +5000) so a new trade should be approved...")
    snap_c = engine._build_portfolio_snapshot(user.id)
    approved_c = RiskGate.validate_risk(db, user, settings, sig1, snap_c, valid_time)
    print(f"Snapshot C flags: {snap_c}")
    print(f"Floating Win Approved? {approved_c} (Expected: True)\n")
    db.delete(o_win)
    db.commit()

    db.close()

if __name__ == "__main__":
    from app.engines.risk_engine import RiskGate
    test_outbox_guard()
    test_risk_snapshot()
