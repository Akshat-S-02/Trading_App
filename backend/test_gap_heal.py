import sys
import os
import asyncio
from datetime import datetime
import zoneinfo

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.websocket.market_ws import heal_historical_gap
from app.engines.paper_strategy_runner import get_runner

import logging
from app.core.instruments import load_instruments

logging.basicConfig(level=logging.INFO)

async def main():
    load_instruments()
    print("Testing gap healing independently...")
    await heal_historical_gap(500)
    runner = get_runner()
    print("Processed Historical Candles:", runner._candles_processed)
    
if __name__ == "__main__":
    asyncio.run(main())
