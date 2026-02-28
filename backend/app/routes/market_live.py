

# from fastapi import APIRouter
# from app.services.dhan_service import get_live_price, place_order, get_portfolio

# router = APIRouter()

# @router.get("/live_stock/{symbol}")
# def live_stock(symbol: str):
#     return get_live_price(symbol.upper())

# @router.post("/trade")
# def trade(symbol: str, qty: int, type: str):
#     return place_order(symbol.upper(), qty, type)

# @router.get("/portfolio")
# def portfolio():
#     return get_portfolio()

# market_live.py

# from fastapi import APIRouter, HTTPException
# from typing import Any
# from app.services import dhan_service
# from app import db
# from pydantic import BaseModel

# router = APIRouter()

# # Quick stocks list endpoint (seed your favorites)
# @router.get("/stocks")
# def stocks():
#     # you can make this dynamic or keep static seeds
#     seed = [
#         {"symbol": "RELIANCE", "price": 0.0},
#         {"symbol": "TCS", "price": 0.0},
#         {"symbol": "INFY", "price": 0.0},
#         {"symbol": "HDFCBANK", "price": 0.0},
#         {"symbol": "SBIN", "price": 0.0},
#     ]
#     # attempt to populate live prices (best-effort)
#     symbols = [f"NSE_EQ:{s['symbol']}" for s in seed]
#     try:
#         resp = dhan_service.get_ltp_for_symbols(symbols)
#         data = resp.get("data", {}) or {}
#         for s in seed:
#             key = next((k for k in data.keys() if s["symbol"] in k), None)
#             if key:
#                 entry = data.get(key, {})
#                 s["price"] = float(entry.get("LTP", 0.0) or 0.0)
#     except Exception:
#         pass
#     return {"stocks": seed}

# @router.get("/live_stock/{symbol}")
# def live_stock(symbol: str):
#     res = dhan_service.get_live_price(symbol)
#     if res.get("error"):
#         raise HTTPException(status_code=500, detail=res["error"])
#     return res


from fastapi import APIRouter, HTTPException
from app.services.dhan_service import find_instrument, get_ltp, get_ltp_batch
from app.core.tick_store import get_tick, get_cached_ltp, latest_ticks




router = APIRouter()


@router.get("/stocks")
def list_stocks():
    """Return a list of sample stocks or full instrument list (trimmed)."""
    return {
        "status": "ok",
        "message": "Stocks API working",
        "samples": ["RELIANCE", "TCS", "HDFCBANK"]
    }


@router.get("/search")
def search_stocks(query: str):
    """
    Search for stocks by symbol or name.
    """
    from app.services.dhan_service import search_instruments
    results = search_instruments(query)
    return {"results": results}


@router.get("/ltp/{symbol}")
async def fetch_ltp(symbol: str):
    """
    Price priority:
      1. Live WebSocket tick (always freshest)
      2. Stale WebSocket tick from latest_ticks dict (even if old — beats 0)
      3. Dhan REST API (with 10s per-symbol cooldown to avoid 429)
      4. 0.0 if nothing is available (market may be closed)

    Also triggers a WebSocket subscription for the symbol so future
    ticks update the cache automatically.
    """
    symbol = symbol.upper()
    if '.' in symbol:
        symbol = symbol.split('.')[0]

    # Always subscribe to WS so we get live ticks going forward
    from app.websocket.market_ws import subscribe_dynamic_symbols
    await subscribe_dynamic_symbols([symbol])

    # 1. WebSocket cache hit (live tick)
    cached = get_cached_ltp(symbol)
    if cached:
        price = cached.get("ltp", 0.0) if isinstance(cached, dict) else float(cached)
        if price and price > 0:
            return {"symbol": symbol, "ltp": price, "source": "websocket"}

    # 2. Stale in-memory tick (any prior WS tick — beats calling REST)
    for _, data in latest_ticks.items():
        if data.get("symbol") == symbol and data.get("ltp", 0) > 0:
            return {"symbol": symbol, "ltp": data["ltp"], "source": "websocket-stale"}

    # 3. REST fallback (with cooldown guard — returns 0.0 if in cooldown)
    rest_price = get_ltp(symbol)
    if rest_price and rest_price > 0:
        return {"symbol": symbol, "ltp": rest_price, "source": "rest"}

    # 4. Nothing — market likely closed, return 0
    return {"symbol": symbol, "ltp": 0.0, "source": "unavailable"}

from pydantic import BaseModel
class BatchLTPRequest(BaseModel):
    symbols: list[str]

@router.post("/ltp/batch")
async def fetch_ltp_batch(req: BatchLTPRequest):
    """
    Fetch LTP for multiple symbols at once.
    Massively improves app startup time by reducing 20 HTTP requests to 1.
    """
    clean_symbols = []
    for s in req.symbols:
        s = s.upper()
        if '.' in s: s = s.split('.')[0]
        clean_symbols.append(s)

    # Always subscribe to WS so we get live ticks going forward
    from app.websocket.market_ws import subscribe_dynamic_symbols
    await subscribe_dynamic_symbols(clean_symbols)

    results = {}
    missing_from_cache = []

    # 1. Check WebSocket / local cache 
    for sym in clean_symbols:
        cached = get_cached_ltp(sym)
        if cached:
            price = cached.get("ltp", 0.0) if isinstance(cached, dict) else float(cached)
            if price > 0:
                results[sym] = {"ltp": price, "source": "websocket"}
                continue
        
        # Check stale tick
        stale_tick = False
        for _, data in latest_ticks.items():
            if data.get("symbol") == sym and data.get("ltp", 0) > 0:
                results[sym] = {"ltp": data["ltp"], "source": "websocket-stale"}
                stale_tick = True
                break
        
        if not stale_tick:
            missing_from_cache.append(sym)

    # 2. REST fallback ONLY for symbols missing from cache
    if missing_from_cache:
        rest_prices = get_ltp_batch(missing_from_cache)
        for sym, price in rest_prices.items():
            if price > 0:
                results[sym] = {"ltp": price, "source": "rest"}
            else:
                results[sym] = {"ltp": 0.0, "source": "unavailable"}

    return {"results": results}



@router.post("/order")
def place_order(order: dict):
    """
    Stub for future real order placement.
    You will connect Dhan Place Order API here.
    """
    return {
        "status": "ok",
        "message": "Order endpoint stub — integrate Dhan orders here",
        "order": order
    }


@router.get("/portfolio")
def get_portfolio():
    """
    Dummy portfolio endpoint — connect portfolio API later.
    """
    return {
        "status": "ok",
        "holdings": [],
        "message": "Portfolio API not yet wired"
    }



@router.get("/ticks/{symbol}")
def get_tick_route(symbol: str):
    symbol = symbol.upper().strip()

    # 1. Try Redis first
    redis_tick = get_tick(symbol)
    if redis_tick:
        return {"symbol": symbol, "redis": redis_tick}

    # 2. Fallback to in-memory tick store
    memory_tick = get_cached_ltp(symbol)
    if memory_tick:
        return {"symbol": symbol, "memory": memory_tick}

    # 3. Nothing found
    return {"symbol": symbol, "error": "No tick found"}


@router.get("/ticks/all")
def get_all_ticks_route():
    from app.core.tick_store import get_all_ticks
    data = get_all_ticks()
    return {"count": len(data), "ticks": data}
