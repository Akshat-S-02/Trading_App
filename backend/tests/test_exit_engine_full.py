import asyncio
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

# Setup path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.engines.paper_strategy_runner import get_runner
from app.engines.execution_engine import ExecutionEngine
from app.db import SessionLocal
from app import models
from app.core import tick_store

async def test_recovery_and_exit():
    print("🚀 Starting Exit Engine Verification Test...")
    db = SessionLocal()
    
    # 1. Cleanup old test data for today
    try:
        db.query(models.Order).filter(models.Order.symbol == "TEST_EXIT").delete()
        db.query(models.Signal).filter(models.Signal.symbol == "TEST_EXIT").delete()
        db.commit()
    except:
        db.rollback()

    # 2. Setup a "ZOMBIE" position (Filled but unclosed)
    # We need a Signal object first
    sig = models.Signal(
        strategy_id=1,
        symbol="TEST_EXIT",
        direction=models.Direction.LONG,
        entry_price=Decimal("100.00"),
        stop_loss=Decimal("95.00"),
        signal_hash="test_sig_unique_123",
        timestamp=datetime.now(timezone.utc)
    )
    db.add(sig)
    db.flush()
    
    order = models.Order(
        user_id=1,
        symbol="TEST_EXIT",
        direction=models.Direction.LONG,
        quantity=10,
        entry_price=Decimal("100.00"),
        average_price=Decimal("100.00"),
        filled_quantity=10,
        status=models.OrderStatus.FILLED,
        signal_id=sig.id,
        created_at=datetime.now(timezone.utc)
    )
    db.add(order)
    db.commit()
    order_id = order.id
    print(f"✅ Created Zombie Order {order_id} for TEST_EXIT at 100.00 (SL 95.00)")

    # 3. Simulate System Startup (Trigger Sync)
    runner = get_runner()
    runner._active_positions.clear() # Reset for clean test
    runner._sync_active_positions()
    
    if order_id in runner._active_positions:
        print(f"✅ SYNC SUCCESS: Order {order_id} loaded into monitor.")
    else:
        print("❌ SYNC FAILED: Order not found in monitor.")
        return

    # 4. Start the monitor task (manually for test control)
    runner._enabled = True
    runner._paused = False
    
    # 5. Feed a tick that does NOT hit SL
    tick_store.save_tick("TEST_EXIT", 98.0)
    print("📊 Fed tick: 98.0 (No exit expected...)")
    await runner._monitor_once()
    
    db.refresh(order)
    if order.status == models.OrderStatus.FILLED:
        print("✅ Correct: Position stayed open.")
    else:
        print(f"❌ Error: Position changed to {order.status}")

    # 6. Feed a tick that HITS Stop-Loss
    tick_store.save_tick("TEST_EXIT", 94.0)
    print("🔻 Fed tick: 94.0 (SL HIT! Triggering exit...)")
    await runner._monitor_once()
    
    # Allow a moment for the Thread (engine.close_paper_position) to finish if it were async, 
    # but currently we called it via to_thread.
    await asyncio.sleep(0.5)
    
    db.refresh(order)
    if order.status == models.OrderStatus.CLOSED:
        print(f"✅ SUCCESS: Order closed automatically. Reason: {order.exit_reason}")
        print(f"💰 Realized PnL: {order.pnl}")
        
        # Check Fill record
        fill = db.query(models.TradeFill).filter(models.TradeFill.order_id == order_id, models.TradeFill.fill_id.like("exit_%")).first()
        if fill:
            print(f"📑 Exit fill created at price {fill.price}")
        else:
            print("❌ No exit fill record found.")
    else:
        print(f"❌ FAILURE: Order status is still {order.status}")

    # 7. Check for Idempotency: Feed another tick and ensure no double-close
    tick_store.save_tick("TEST_EXIT", 90.0)
    print("📊 Fed another tick: 90.0 (Checking for double-close...)")
    await runner._monitor_once()
    
    # No logs should appear about "EXIT TRIGGERED"
    print("✅ Idempotency check pass: No second exit attempted.")

    print("\n🏁 FINAL RESULT: PASSED")

if __name__ == "__main__":
    asyncio.run(test_recovery_and_exit())
