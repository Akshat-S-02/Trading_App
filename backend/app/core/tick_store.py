"""
app/core/tick_store.py

Latest prices, two ways:
  - Redis  tick:<SYMBOL> -> {"symbol", "ltp", "timestamp"}: shared across processes
    (the OutboxWorker / PaperBroker read it); timestamp = when we received it.
  - latest_ticks {security_id: {"symbol", "ltp", "time"}}: in-process cache that
    market_ws fills and the /ws/market proxy streams to the app.
"""
import json
import time
from typing import Dict

from redis import Redis

redis = Redis(host="127.0.0.1", port=6379, decode_responses=True)

REDIS_KEY_PREFIX = "tick:"  # tick:RELIANCE, tick:TCS, ...
MAX_TICK_AGE_S = 30  # older than this = feed down / symbol not trading: not a live price

latest_ticks: Dict[int, Dict] = {}


def get_cached_ltp(symbol: str):
    """In-process tick for a symbol (API process only), or None."""
    symbol = symbol.upper().strip()
    for data in latest_ticks.values():
        if data["symbol"] == symbol:
            return data
    return None


def save_tick(symbol: str, ltp: float):
    try:
        redis.set(f"{REDIS_KEY_PREFIX}{symbol.upper()}", json.dumps({
            "symbol": symbol,
            "ltp": float(ltp),
            "timestamp": time.time(),
        }))
    except Exception as e:
        print("⚠ redis.set FAILED:", e)


def get_tick(symbol: str):
    """Latest Redis tick for one symbol, whatever its age (see get_live_ltp)."""
    raw = redis.get(f"{REDIS_KEY_PREFIX}{symbol.upper()}")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception as e:
        print("⚠ redis.get decode FAILED:", e, "raw:", raw)
        return None


def tick_is_live(tick: dict | None, max_age_s: float = MAX_TICK_AGE_S) -> bool:
    """True if the Redis tick has a price and was written within max_age_s."""
    if not tick or not tick.get("ltp"):
        return False
    ts = tick.get("timestamp")
    return ts is not None and time.time() - float(ts) <= max_age_s


def get_live_ltp(symbol: str, max_age_s: float = MAX_TICK_AGE_S):
    """Latest price only if it is fresh; None if missing, stale, or Redis is down."""
    try:
        tick = get_tick(symbol)
    except Exception:
        return None
    return float(tick["ltp"]) if tick_is_live(tick, max_age_s) else None
