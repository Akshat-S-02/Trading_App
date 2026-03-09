import asyncio
from .logger import system_logger

async def simple_momentum_loop(interval_seconds: int = 60):
    """
    Deprecated Sandbox AI Loop.
    Will be replaced by the pure SignalEngine in Phase 2.
    """
    system_logger.info("ℹ️ Old AI Agent disabled. Awaiting Signal Engine architecture.")
    while True:
        await asyncio.sleep(86400)
