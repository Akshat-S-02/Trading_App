# app/core/tick_store.py

from typing import Dict
import json
import time
from redis import Redis

# Single Redis connection (thread-safe)
redis = Redis(host="127.0.0.1", port=6379, decode_responses=True)

REDIS_KEY_PREFIX = "tick:"  # tick:RELIANCE, tick:TCS, tick:HDFCBANK

# Store: { security_id: {"symbol": str, "ltp": float, "time": int} }
latest_ticks: Dict[int, Dict] = {}

# Public function to update ticks
def update_tick(security_id: int, symbol: str, ltp: float, timestamp: int):
    latest_ticks[security_id] = {
        "symbol": symbol,
        "ltp": ltp,
        "time": timestamp,
    }

# Public function to get LTP by symbol name
def get_cached_ltp(symbol: str):
    symbol = symbol.upper().strip()
    for sec_id, data in latest_ticks.items():
        if data["symbol"] == symbol:
            return data
    return None  # not found

# Public function to get tick by security id
def get_tick_by_sid(security_id: int):
    return latest_ticks.get(security_id)



# def save_tick(symbol: str, ltp: float):
#     """Store the latest tick for a symbol."""
#     data = {
#         "symbol": symbol,
#         "ltp": ltp,
#         "timestamp": time.time()
#     }
#     key = f"{REDIS_KEY_PREFIX}{symbol}"
#     redis.set(key, json.dumps(data))

# def save_tick(symbol: str, ltp: float):
#     try:
#         key = f"{REDIS_KEY_PREFIX}{symbol.upper()}"
#         redis.set(key, json.dumps({
#             "symbol": symbol,
#             "ltp": ltp,
#             "timestamp": time.time(),
#         }))
#         # print("REDIS ADDRESS:", redis.connection_pool.connection_kwargs)
#         print("PING:", redis.ping())
#         print("REAL REDIS INFO:", redis.info())

#     except Exception as e:
#         print("🔥 redis.set FAILED:", e)


# near the top of file (if not present)


def save_tick(symbol: str, ltp: float):
    try:
        key = f"{REDIS_KEY_PREFIX}{symbol.upper()}"
        # DEBUG: show connection info & ping + keys BEFORE writing
        # try:
        #     print("DEBUG: redis-ping ->", redis.ping())
        # except Exception as _e:
        #     print("DEBUG: redis.ping FAILED:", _e)
        # try:
        #     print("DEBUG: redis connection pool settings:", getattr(redis, "connection_pool", None) and redis.connection_pool.connection_kwargs)
        # except Exception:
        #     pass
        # try:
        #     print("DEBUG: existing keys (sample):", redis.keys("*")[:50])
        # except Exception as _e:
        #     print("DEBUG: keys() failed:", _e)

        redis.set(key, json.dumps({
            "symbol": symbol,
            "ltp": float(ltp),
            "timestamp": time.time(),
        }))

        # DEBUG: read back the key we just set
        # try:
        #     print("DEBUG: read-back:", redis.get(key))
        # except Exception as _e:
        #     print("DEBUG: read-back failed:", _e)

    except Exception as e:
        print("⚠ redis.set FAILED:", e)



def get_tick(symbol: str):
    """Get latest tick for one symbol."""
    key = f"{REDIS_KEY_PREFIX}{symbol.upper()}"
    raw = redis.get(key)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception as e:
        print("⚠ redis.get decode FAILED:", e, "raw:", raw)
        return None

def get_all_ticks():
    """Return all available ticks (fast)."""
    keys = redis.keys(f"{REDIS_KEY_PREFIX}*")
    out = []

    for k in keys:
        raw = redis.get(k)
        if raw:
            out.append(json.loads(raw))

    return out
