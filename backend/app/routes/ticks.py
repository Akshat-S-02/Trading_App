# from fastapi import APIRouter, HTTPException
# from app.websocket.market_ws import get_ltp_by_symbol, get_all_ltps

# router = APIRouter(prefix="/ltp", tags=["LTP"])

# @router.get("/")
# def get_single_ltp(symbol: str):
#     """
#     Returns the latest LTP for a given symbol from live tick store.
#     """
#     tick = get_ltp_by_symbol(symbol)
#     if not tick:
#         raise HTTPException(status_code=404, detail=f"No live tick for {symbol}")

#     return tick


# @router.get("/all")
# def get_every_ltp():
#     """
#     Return ALL ticks currently available.
#     """
#     return get_all_ltps()


# @router.post("/bulk")
# def get_bulk_ltps(symbols: list[str]):
#     """
#     Return ticks for multiple symbols at once.
#     """
#     result = {}
#     for s in symbols:
#         tick = get_ltp_by_symbol(s)
#         if tick:
#             result[s.upper()] = tick
#         else:
#             result[s.upper()] = None
#     return result


# # app/routes/ticks.py

# from fastapi import APIRouter
# from app.websocket.market_ws import get_cached_ltp, latest_ticks

# router = APIRouter(prefix="/ticks", tags=["Ticks"])

# @router.get("/{symbol}")
# def get_ltp_for_symbol(symbol: str):
#     """
#     Return the latest tick for a given symbol or SID.
#     """
#     tick = get_cached_ltp(symbol)
#     if tick:
#         return tick
#     return {"symbol": symbol, "error": "No tick found"}

# @router.get("/")
# def get_all_ticks():
#     """
#     Return all latest ticks currently in memory.
#     WARNING: For 5000 stocks this can be large.
#     """
#     return latest_ticks


# app/routes/ticks.py
# app/routes/ticks.py

# app/routes/ticks.py

# app/routes/ticks.py

from fastapi import APIRouter
from app.core.tick_store import get_cached_ltp, latest_ticks

router = APIRouter(prefix="/ticks", tags=["Ticks"])


@router.get("/{symbol}")
def get_ltp_for_symbol(symbol: str):
    """
    Return the latest tick for a given symbol.
    """
    tick = get_cached_ltp(symbol)
    if tick:
        return tick

    return {"symbol": symbol, "error": "No tick found"}


@router.get("/")
def get_all_ticks():
    """
    Return all ticks currently in memory.
    """
    return latest_ticks
