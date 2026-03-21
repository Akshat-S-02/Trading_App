"""
app/broker/paper_broker.py

Realistic paper-trading fill simulator.
Routes from OutboxWorker when EXECUTION_MODE == "paper".

Behaviour:
  - Reads latest LTP from tick store
  - Adds configurable slippage (in ticks, where 1 tick = ₹0.05)
  - Adds randomised latency (configurable min/max ms)
  - Marks Order → FILLED, inserts TradeFill with PAPER_xxx broker ID
"""

import logging
import random
import time
import uuid
from decimal import Decimal
from typing import Dict, Any

from app.config import config
from app.core.tick_store import get_cached_ltp

logger = logging.getLogger("PaperBroker")

TICK_SIZE = Decimal("0.05")


def _simulate_latency() -> float:
    """
    Sleep for a random duration between configured min/max ms.
    Returns the actual delay in milliseconds (for metrics).
    """
    delay_ms = random.randint(
        config.PAPER_FILL_DELAY_MS_MIN,
        config.PAPER_FILL_DELAY_MS_MAX,
    )
    time.sleep(delay_ms / 1000.0)
    return float(delay_ms)


def _apply_slippage(ltp: Decimal, direction: str) -> Decimal:
    """
    Apply slippage in tick increments.
    BUY  fills ABOVE ltp  (unfavourable)
    SELL fills BELOW ltp  (unfavourable)
    """
    slippage = TICK_SIZE * config.PAPER_SLIPPAGE_TICKS
    if direction.upper() in ("BUY", "LONG"):
        return ltp + slippage
    else:
        return ltp - slippage


def place_order(
    symbol: str,
    qty: int,
    direction: str,
    price: float = 0.0,
    order_type: str = "MARKET",
    correlation_id: str | None = None,
) -> Dict[str, Any]:
    """
    Simulate a realistic fill for paper-trading.

    Returns the same response shape as dhan_service.place_order() so the
    OutboxWorker can handle it identically:
        {"status": "success", "order_id": "PAPER_...", ...}
        {"status": "error", "error": "..."}
    """
    # 1. Get latest price from tick store
    tick = get_cached_ltp(symbol)
    if tick and tick.get("ltp"):
        ltp = Decimal(str(tick["ltp"]))
    elif price > 0:
        # Fallback to the signal price in the outbox payload
        ltp = Decimal(str(price))
    else:
        return {
            "status": "error",
            "error": f"No LTP available for {symbol} — tick store empty and no price in payload",
        }

    # 2. Apply slippage
    fill_price = _apply_slippage(ltp, direction)

    # 3. Simulate network/exchange latency
    latency_ms = _simulate_latency()

    # 4. Generate paper broker ID
    broker_order_id = f"PAPER_{uuid.uuid4().hex[:10].upper()}"

    logger.info(
        f"PAPER FILL: {direction} {qty}x {symbol} "
        f"| LTP={ltp} fill={fill_price} "
        f"| slippage={config.PAPER_SLIPPAGE_TICKS} ticks "
        f"| latency={latency_ms:.0f}ms "
        f"| id={broker_order_id}"
    )

    return {
        "status": "success",
        "order_id": broker_order_id,
        # Extra metadata for downstream metrics logging
        "paper_meta": {
            "ltp_at_fill": float(ltp),
            "fill_price": float(fill_price),
            "slippage_ticks": config.PAPER_SLIPPAGE_TICKS,
            "latency_ms": latency_ms,
            "correlation_id": correlation_id or "",
        },
    }
