import sys
import os
import sqlalchemy

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.db import engine

def apply_migration():
    try:
        with engine.connect() as conn:
            conn.execute(sqlalchemy.text('ALTER TABLE orders ADD COLUMN IF NOT EXISTS signal_timestamp TIMESTAMP WITH TIME ZONE;'))
            conn.commit()
        print('SUCCESS: Added signal_timestamp to orders table')
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    apply_migration()
