import sys
import os
import sqlalchemy

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.db import require_test_db; require_test_db()  # this script deletes data
from app.db import engine
from run_paper_session import run_session

def verify():
    # 1. Clear existing orders
    try:
        with engine.connect() as conn:
            conn.execute(sqlalchemy.text('DELETE FROM trade_fills;'))
            conn.execute(sqlalchemy.text('DELETE FROM outbox_events;'))
            conn.execute(sqlalchemy.text('DELETE FROM orders;'))
            conn.commit()
            print("Successfully cleared orders, trade_fills, and outbox_events.\n")
    except Exception as e:
        print(f"Failed to clear tables: {e}")

    # 2. Run Paper Session
    run_session()

    # 3. Verify Timestamps
    try:
        with engine.connect() as conn:
            res = conn.execute(sqlalchemy.text('SELECT id, signal_timestamp, created_at, symbol FROM orders ORDER BY id DESC LIMIT 1;')).fetchone()
            if res:
                print("\n=== TIMESTAMP VERIFICATION ===")
                print(f"Order ID: {res[0]}")
                print(f"Symbol: {res[3]}")
                print(f"Signal Timestamp (Strategy Date): {res[1]}")
                print(f"Created At (DB Time): {res[2]}")
                print("================================")
            else:
                print("No orders were created during the session replay.")
    except Exception as e:
         print(f"Failed to fetch order timestamps: {e}")

if __name__ == "__main__":
    verify()
