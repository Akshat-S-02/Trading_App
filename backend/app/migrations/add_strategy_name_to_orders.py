import asyncio
import sys
import os

# Add backend to path so we can import app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from sqlalchemy.ext.asyncio import create_async_engine
from app.config import config

async def migrate():
    # Replace posgresql:// with postgresql+asyncpg:// if needed, but SQLAlchemy 2.0 async engine requires it
    db_url = config.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    print(f"Connecting to {db_url}...")
    engine = create_async_engine(db_url, echo=True)
    async with engine.begin() as conn:
        print("Running migration: add strategy_name to orders")
        try:
            # We use IF NOT EXISTS just in case
            await conn.execute(
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS strategy_name VARCHAR"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_orders_strategy_name ON orders (strategy_name)"
            )
            print("Migration successful.")
        except Exception as e:
            print(f"Migration failed or already applied: {e}")
            
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(migrate())
