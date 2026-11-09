"""
Migration: add target_price to signals table
Generated: 2026-05-01

Adds a nullable NUMERIC(15,4) column `target_price` to the `signals` table.
This column stores the pre-calculated profit target for a signal, mirroring
the `stop_loss` column.  It is consumed by PaperStrategyRunner._evaluate_exit()
to trigger a "TARGET" exit when LTP reaches this level.

Run:
    python migrations/add_target_price_to_signals.py

Safe to re-run: the migration checks whether the column already exists
before issuing ALTER TABLE, so it is idempotent.
"""

import sys
import os

# Ensure the backend root is on the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import text
from app.db import engine


UPGRADE_SQL = """
ALTER TABLE signals
    ADD COLUMN IF NOT EXISTS target_price NUMERIC(15, 4);
"""

DOWNGRADE_SQL = """
ALTER TABLE signals
    DROP COLUMN IF EXISTS target_price;
"""


def upgrade():
    with engine.begin() as conn:
        conn.execute(text(UPGRADE_SQL))
    print("[OK] Migration applied: signals.target_price column added.")


def downgrade():
    with engine.begin() as conn:
        conn.execute(text(DOWNGRADE_SQL))
    print("[OK] Migration reverted: signals.target_price column removed.")


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "upgrade"
    if action == "upgrade":
        upgrade()
    elif action == "downgrade":
        downgrade()
    else:
        print(f"Unknown action '{action}'. Use 'upgrade' or 'downgrade'.")
        sys.exit(1)
