"""Market data REST routes: search, LTP, candles, news (all require login)."""
from fastapi import APIRouter, HTTPException
from app.services.dhan_service import get_ltp, get_ltp_batch
from app.core.tick_store import get_cached_ltp, latest_ticks

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

    # 1. Trigger WebSocket subscription for all requested symbols
    from app.websocket.market_ws import subscribe_dynamic_symbols
    await subscribe_dynamic_symbols(clean_symbols)

    results = {}
    missing = []
    
    # 2. Try to answer from fast local cache or stale ticks first
    for sym in clean_symbols:
        cached = get_cached_ltp(sym)
        if cached:
            price = cached.get("ltp", 0.0) if isinstance(cached, dict) else float(cached)
            if price > 0:
                results[sym] = {"ltp": price, "source": "websocket"}
                continue
                
        found = False
        for _, data in latest_ticks.items():
            if data.get("symbol") == sym and data.get("ltp", 0) > 0:
                results[sym] = {"ltp": data["ltp"], "source": "websocket-stale"}
                found = True
                break
                
        if not found:
            missing.append(sym)

    # 3. Hit the Dhan REST batch API for the remainder
    if missing:
        api_results = get_ltp_batch(missing)
        for sym, price in api_results.items():
            results[sym] = {"ltp": price, "source": "rest" if price > 0 else "unavailable"}

    return {"results": results}

# ── Dhan Search & Metadata ─────────────────────────────────────────────────

import asyncio
import logging
import time as _time
from datetime import datetime, timedelta, timezone

_candle_logger = logging.getLogger("CandlesAPI")

# interval -> lookback in days (keeps responses a few hundred to ~2k bars)
_CANDLE_LOOKBACK_DAYS = {"1": 3, "5": 10, "15": 30, "60": 90, "D": 730}
_CANDLE_CACHE_TTL_S = 30
_candle_cache: dict[tuple[str, str], tuple[float, list[dict]]] = {}


def _fetch_candles_dhan(symbol: str, interval: str) -> list[dict]:
    from app.core.instruments import get_security_id_multi
    from research.services.historical_data_service import fetch_intraday, fetch_daily

    sid = get_security_id_multi([symbol]).get(symbol)
    if not sid:
        raise ValueError(f"Unknown symbol {symbol}")
    to_date = datetime.now() + timedelta(days=1)
    from_date = to_date - timedelta(days=_CANDLE_LOOKBACK_DAYS[interval])
    if interval == "D":
        raw = fetch_daily(str(sid), symbol, from_date, to_date)
    else:
        raw = fetch_intraday(str(sid), symbol, int(interval), from_date, to_date)
    return [
        {
            "t": int(c["timestamp"].timestamp() * 1000),
            "o": c["open"], "h": c["high"], "l": c["low"], "c": c["close"],
            "v": int(c.get("volume") or 0),
        }
        for c in raw
    ]


def _fetch_candles_yf(symbol: str, interval: str) -> list[dict]:
    import yfinance as yf

    yf_interval = {"1": "1m", "5": "5m", "15": "15m", "60": "60m", "D": "1d"}[interval]
    period = {"1": "5d", "5": "1mo", "15": "1mo", "60": "3mo", "D": "2y"}[interval]
    df = yf.Ticker(f"{symbol}.NS").history(period=period, interval=yf_interval)
    out = []
    for ts, row in df.iterrows():
        out.append({
            "t": int(ts.to_pydatetime().astimezone(timezone.utc).timestamp() * 1000),
            "o": float(row["Open"]), "h": float(row["High"]),
            "l": float(row["Low"]), "c": float(row["Close"]),
            "v": int(row["Volume"] or 0),
        })
    return out


@router.get("/candles/{symbol}")
async def fetch_candles(symbol: str, interval: str = "5"):
    """
    OHLCV candles for the chart view, oldest first.
    interval: 1 | 5 | 15 | 60 (minutes) or D (daily).
    Source: Dhan historical API, falling back to yfinance. Cached for 30 s.
    """
    interval = interval.upper()
    if interval not in _CANDLE_LOOKBACK_DAYS:
        raise HTTPException(422, f"interval must be one of {list(_CANDLE_LOOKBACK_DAYS)}")
    symbol = symbol.upper().split(".")[0]

    key = (symbol, interval)
    hit = _candle_cache.get(key)
    if hit and _time.monotonic() - hit[0] < _CANDLE_CACHE_TTL_S:
        return {"symbol": symbol, "interval": interval, "source": "cache", "candles": hit[1]}

    source = "dhan"
    try:
        candles = await asyncio.to_thread(_fetch_candles_dhan, symbol, interval)
    except Exception as e:
        _candle_logger.warning(f"Dhan candles failed for {symbol} {interval}: {e}; trying yfinance")
        candles = []
    if not candles:
        source = "yfinance"
        try:
            candles = await asyncio.to_thread(_fetch_candles_yf, symbol, interval)
        except Exception as e:
            raise HTTPException(502, f"No candle data for {symbol}: {e}")
    if not candles:
        raise HTTPException(404, f"No candle data for {symbol}")

    candles.sort(key=lambda c: c["t"])
    _candle_cache[key] = (_time.monotonic(), candles)
    return {"symbol": symbol, "interval": interval, "source": source, "candles": candles}


# ── Live news headlines (Dhan /v2/data/newsheadline) ──────────────────────

import requests as _requests

_NEWS_URL = "https://api.dhan.co/v2/data/newsheadline"
_NEWS_CATEGORIES = {
    "ALL", "COMPANIES", "EQUITY_MARKETS", "DEBT_MARKETS", "IPO", "GLOBAL",
    "INDIAN_ECONOMY", "GLOBAL_ECONOMY", "CURRENCY", "COMMODITIES",
    "CRYPTOCURRENCIES", "GOVERNMENT_POLICY_AND_REGULATION", "INFRASTRUCTURE",
    "INTERNATIONAL_TRADE", "INVESTMENT_IDEAS", "REAL_ESTATE", "STARTUPS",
    "TECHNOLOGY", "MUTUAL_FUNDS",
}
_NEWS_CACHE_TTL_S = 60
_news_cache: dict[tuple, tuple[float, list[dict]]] = {}


def _fetch_news_dhan(category: str, security_ids: list[str], limit: int) -> list[dict]:
    from app.config import config

    body = {"dhanClientId": config.CLIENT_ID, "categories": [category], "limit": limit}
    if security_ids:
        body["stockList"] = security_ids  # Dhan wants security IDs as strings
    r = _requests.post(
        _NEWS_URL,
        json=body,
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "access-token": config.ACCESS_TOKEN},
        timeout=15,
    )
    data = r.json() if r.content else {}
    if r.status_code != 200:
        # DH-907 = nothing published for these filters; not an error for the UI
        if data.get("errorCode") == "DH-907":
            return []
        if data.get("errorCode") == "DH-901":
            raise RuntimeError("Dhan access token has expired. Restart the backend to renew it, "
                               "or paste a fresh token into ACCESS_TOKEN in backend/.env")
        raise RuntimeError(f"{data.get('errorCode', r.status_code)}: {data.get('errorMessage', r.text[:200])}")

    out = []
    for item in (data.get("data") or {}).get("latestNews") or []:
        news = item.get("newsObject") or {}
        title = (news.get("title") or "").strip()
        if not title:
            continue
        # Only items with an NSE scrip code are tradable stocks; for general
        # news Dhan puts a free-text topic ("India", "commodities") in smSymbol.
        raw_sym = (item.get("smSymbol") or "").strip()
        is_nse_stock = bool(item.get("nseScripCode"))
        topic = None
        if not is_nse_stock:
            topic = (item.get("displaySymbol") or "").strip() or raw_sym
            norm = topic.lower().replace("-", " ").replace("_", " ")
            if norm in {"", "markets", (item.get("category") or "").lower().replace("_", " ")}:
                topic = None
        out.append({
            "title": title,
            "text": (news.get("text") or "").strip(),
            "sentiment": (news.get("overallSentiment") or "neutral").lower(),
            "category": item.get("category"),
            "sub_category": item.get("subCategory"),
            "date": item.get("publishDate"),
            "symbol": raw_sym if is_nse_stock else None,
            "topic": topic,
            "name": item.get("displaySymbol") or item.get("stockName"),
        })
    return out


@router.get("/news")
async def fetch_news(category: str = "ALL", symbols: str = "", limit: int = 50):
    """
    Latest news headlines, newest first.
    category: one of Dhan's news categories (ALL, COMPANIES, IPO, ...).
    symbols:  optional comma-separated NSE symbols to restrict to those stocks.
    Cached for 60 s per (category, symbols, limit).
    """
    category = category.upper()
    if category not in _NEWS_CATEGORIES:
        raise HTTPException(422, f"category must be one of {sorted(_NEWS_CATEGORIES)}")
    limit = max(1, min(limit, 50))
    wanted = sorted({s.strip().upper().split(".")[0] for s in symbols.split(",") if s.strip()})

    key = (category, tuple(wanted), limit)
    hit = _news_cache.get(key)
    if hit and _time.monotonic() - hit[0] < _NEWS_CACHE_TTL_S:
        return {"category": category, "symbols": wanted, "news": hit[1]}

    security_ids: list[str] = []
    if wanted:
        from app.core.instruments import get_security_id_multi
        ids = get_security_id_multi(wanted)
        security_ids = [str(ids[s]) for s in wanted if ids.get(s)]
        if not security_ids:
            return {"category": category, "symbols": wanted, "news": []}

    try:
        news = await asyncio.to_thread(_fetch_news_dhan, category, security_ids, limit)
    except Exception as e:
        _candle_logger.warning(f"Dhan news failed ({category}, {wanted}): {e}")
        if hit:  # serve stale rather than nothing
            return {"category": category, "symbols": wanted, "news": hit[1], "stale": True}
        raise HTTPException(502, str(e))

    _news_cache[key] = (_time.monotonic(), news)
    return {"category": category, "symbols": wanted, "news": news}
