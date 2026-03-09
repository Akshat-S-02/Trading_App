import os
import sys
from decimal import Decimal
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import User, Order, OrderStatus, Direction, RiskCategory
from app.engines.reconciliation_engine import ReconciliationService

DATABASE_URL = "postgresql://postgres:Akshat%401311@localhost:5432/trading_sandbox"
engine = create_engine(DATABASE_URL)
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class MockBroker:
    def get_orders(self):
        return []

    def get_positions(self):
        # Pretend the broker has 100 shares of RELIANCE long that aren't in the DB.
        return [
            {
                "tradingSymbol": "RELIANCE",
                "netQty": 100
            }
        ]

def run_test():
    db = SessionLocal()
    print("--- 1. Setting Up Simulated Broken State ---")
    user = db.query(User).filter(User.username == "test_crash").first()
    if not user:
        user = User(
            username="test_crash", 
            hashed_password="xxx", 
            capital_current=100000.0,
            risk_category=RiskCategory.LOW,
            automation_enabled=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    # 1. Clean up existing RELIANCE orders in DB to simulate "Commit Failed/Rolled Back"
    db.query(Order).filter(Order.user_id == user.id, Order.symbol == "RELIANCE").delete()
    db.commit()

    longs = sum(o.filled_quantity for o in db.query(Order).filter(Order.user_id == user.id, Order.symbol == "RELIANCE", Order.direction == Direction.LONG).all() if o.filled_quantity)
    shorts = sum(o.filled_quantity for o in db.query(Order).filter(Order.user_id == user.id, Order.symbol == "RELIANCE", Order.direction == Direction.SHORT).all() if o.filled_quantity)
    print(f"DB Net Position for RELIANCE: {longs - shorts}")

    print("\n--- 2. App Crashes Mid-Execution... Restarting... ---")
    print("--- 3. Engaging Reconciliation Engine ---")
    
    broker = MockBroker()
    recon = ReconciliationService(db, broker)
    recon.sync_broker_positions(user.id)
    
    print("\n--- 4. DB State After Reconciliation ---")
    longs = sum(o.filled_quantity for o in db.query(Order).filter(Order.user_id == user.id, Order.symbol == "RELIANCE", Order.direction == Direction.LONG).all() if o.filled_quantity)
    shorts = sum(o.filled_quantity for o in db.query(Order).filter(Order.user_id == user.id, Order.symbol == "RELIANCE", Order.direction == Direction.SHORT).all() if o.filled_quantity)
    net = longs - shorts
    print(f"DB Net Position for RELIANCE: {net}")
    
    if net == 100:
        print("SUCCESS! Synthetic order was generated and successfully injected to heal DB drift.")
    else:
        print("FAILURE! DB drifted and did not heal.")
        
    db.close()

if __name__ == "__main__":
    run_test()
