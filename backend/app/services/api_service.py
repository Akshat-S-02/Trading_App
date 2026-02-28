import httpx, os, time, traceback
from fastapi import HTTPException
from functools import lru_cache

API_KEY = os.getenv("FINNHUB_API_KEY", "d47n749r01qkdqhrg7o0d47n749r01qkdqhrg7og")
BASE_URL = "https://finnhub.io/api/v1"

_cache = {}
CACHE_TTL = 60  # seconds


def _get_cached(key: str):
    entry = _cache.get(key)
    if entry and (time.time() - entry["time"] < CACHE_TTL):
        return entry["data"]
    return None


def _set_cache(key: str, data):
    _cache[key] = {"data": data, "time": time.time()}


async def get_quote(symbol: str):
    symbol = symbol.upper().strip()
    cached = _get_cached(f"quote:{symbol}")
    if cached:
        print(f"⚡ Using cached quote for {symbol}")
        return cached

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # ✅ Step 1: Only auto-search if symbol is short and >= 2 chars
            if 2 <= len(symbol) <= 4:
                print(f"🔍 Searching for NSE match for '{symbol}'...")
                search_resp = await client.get(
                    f"{BASE_URL}/search",
                    params={"q": symbol, "token": API_KEY}
                )

                if search_resp.status_code != 200 or not search_resp.text.strip():
                    print(f"⚠️ Finnhub search returned empty response for '{symbol}'")
                    raise HTTPException(status_code=404, detail=f"No NSE match found for '{symbol}'")

                try:
                    search_data = search_resp.json()
                except Exception:
                    print(f"⚠️ Invalid JSON in search response for '{symbol}' — skipping")
                    raise HTTPException(status_code=404, detail=f"Search failed for '{symbol}'")

                candidates = [
                    r for r in search_data.get("result", [])
                    if r["symbol"].endswith(".NS")
                ]

                if candidates:
                    symbol = candidates[0]["symbol"].replace(".NS", "")
                    print(f"✅ Auto-resolved '{symbol}' to '{symbol}.NS'")
                else:
                    raise HTTPException(status_code=404, detail=f"No NSE stock found for '{symbol}'")

            elif len(symbol) < 2:
                print(f"⏸️ Skipping lookup for very short symbol '{symbol}'")
                raise HTTPException(status_code=400, detail="Query too short")

            # # ✅ Step 2: Fetch live quote
            # print(f"🔹 Fetching live quote for {symbol}.NS")
            # response = await client.get(
            #     f"{BASE_URL}/quote",
            #     params={"symbol": f"{symbol}.NS", "token": API_KEY}
            # )

            # data = response.json()
            # if "error" in data or data.get("c") in (0, None):
            #     raise HTTPException(status_code=404, detail=f"No live data found for '{symbol}'")

            # result = {
            #     "symbol": symbol,
            #     "price": float(data["c"]),
            #     "high": float(data["h"]),
            #     "low": float(data["l"]),
            #     "open": float(data["o"]),
            #     "prev_close": float(data["pc"]),
            #     "timestamp": int(time.time())
            # }

            # _set_cache(f"quote:{symbol}", result)
            # return result
                        # ✅ Step 2: Fetch live quote with fallbacks
            possible_symbols = [f"{symbol}.NS", symbol, f"{symbol}.BO"]
            last_error = None

            for s in possible_symbols:
                print(f"🔹 Trying live quote for {s}")
                response = await client.get(
                    f"{BASE_URL}/quote",
                    params={"symbol": s, "token": API_KEY}
                )

                if response.status_code == 200 and response.text.strip():
                    data = response.json()
                    if data.get("c") and data["c"] > 0:
                        result = {
                            "symbol": s.replace(".NS", "").replace(".BO", ""),
                            "price": float(data["c"]),
                            "high": float(data["h"]),
                            "low": float(data["l"]),
                            "open": float(data["o"]),
                            "prev_close": float(data["pc"]),
                            "timestamp": int(time.time())
                        }
                        _set_cache(f"quote:{symbol}", result)
                        return result

                last_error = response.text

            print(f"❌ No valid quote found for {symbol}, last response: {last_error}")
            raise HTTPException(status_code=404, detail=f"No live data found for '{symbol}'")


    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error fetching quote for {symbol}: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


async def search_stocks(query: str):
    query = query.upper()
    cached = _get_cached(f"search:{query}")
    if cached:
        return cached

    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"{BASE_URL}/search", params={"q": query, "token": API_KEY})
        data = r.json()
        if "result" not in data:
            raise HTTPException(status_code=404, detail="No results found")

        nse_stocks = [
            {"symbol": item["symbol"], "name": item.get("description", ""), "exchange": item.get("displaySymbol")}
            for item in data["result"]
            if item["symbol"].endswith(".NS")
        ]

        _set_cache(f"search:{query}", nse_stocks)
        return nse_stocks


async def get_historical_data(symbol: str, resolution="D", count=30):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = f"{BASE_URL}/stock/candle"
            params = {
                "symbol": f"{symbol}.NS",
                "resolution": resolution,
                "count": count,
                "token": API_KEY
            }
            r = await client.get(url, params=params)
            data = r.json()
            if data.get("s") != "ok":
                raise HTTPException(status_code=404, detail=f"No candle data for {symbol}")
            return data
    except Exception as e:
        print(f"❌ Error fetching candles for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
