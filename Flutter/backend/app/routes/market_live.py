

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
from app.services.dhan_service import find_instrument, get_ltp
# from app.websocket.market_ws import get_cached_ltp
from app.core.tick_store import get_tick, get_cached_ltp



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
    Priority:
    1. Use WebSocket cached tick if available
    2. Fallback to REST LTP
    """
    symbol = symbol.upper()
    # Strip exchange suffix if present (e.g. "ETERNAL.NS" -> "ETERNAL")
    if '.' in symbol:
        symbol = symbol.split('.')[0]

    # check instrument existence
    inst = find_instrument(symbol)
    if not inst:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")

    # First use WebSocket cache
    cached = get_cached_ltp(symbol)
    if cached:
        return {"symbol": symbol, "ltp": cached, "source": "websocket"}

    # Ensure we are subscribed to this symbol for future updates
    from app.websocket.market_ws import subscribe_dynamic_symbols
    await subscribe_dynamic_symbols([symbol])

    # fallback: REST API
    ltp_data = get_ltp(inst)
    return {"symbol": symbol, "ltp": ltp_data, "source": "rest-api"}


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
