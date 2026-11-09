"""Debug routes for the in-process tick cache (require login)."""
from fastapi import APIRouter

from app.core.tick_store import get_cached_ltp, latest_ticks

router = APIRouter(prefix="/ticks", tags=["Ticks"])


@router.get("/{symbol}")
def get_ltp_for_symbol(symbol: str):
    """Latest in-memory tick for one symbol."""
    tick = get_cached_ltp(symbol)
    return tick or {"symbol": symbol, "error": "No tick found"}


@router.get("/")
def get_all_ticks():
    """All ticks currently in memory, keyed by security id."""
    return latest_ticks
