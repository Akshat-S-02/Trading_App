import asyncio
from datetime import datetime

from app.core.tick_store import get_all_ticks
from app.ai.strategies import evaluate_strategies
from app.ai.executor import execute_signal


AI_INTERVAL_MS = 500   # engine runs every 500 ms (adjust as needed)
running = True


async def ai_engine_loop():
    print("🤖 AI Engine Started...")

    while running:
        try:
            # 1. Pull latest ticks (non-blocking)
            ticks = get_all_ticks()

            if not ticks:
                await asyncio.sleep(AI_INTERVAL_MS / 1000)
                continue

            # 2. Pass ticks to your strategies
            decisions = evaluate_strategies(ticks)

            # 3. For each decision, send to executor
            for symbol, decision in decisions.items():
                if decision["action"] != "hold":
                    print(f"⚡ AI Decision → {symbol} → {decision}")
                    await execute_signal(symbol, decision)

        except Exception as e:
            print("🔥 AI Engine Error:", e)

        # 4. Wait before next evaluation cycle
        await asyncio.sleep(AI_INTERVAL_MS / 1000)
