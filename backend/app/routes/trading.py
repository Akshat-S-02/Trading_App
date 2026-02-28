# from fastapi import APIRouter, Request, Query
# import json, os
# from datetime import datetime
# import httpx
# import time
# import yfinance as yf
# from pydantic import BaseModel


# router = APIRouter()

# # File paths
# PORTFOLIO_FILE = "portfolio.json"
# TRADES_FILE = "trades.json"
# STOCKS_URL = "http://127.0.0.1:8000/stocks"  # get live prices from your own endpoint


# portfolio = []
# history = []

# class TradeRequest(BaseModel):
#     symbol: str
#     amount: float
#     type: str  # "buy" or "sell"

# @router.post("/trade")
# async def trade_stock(request: TradeRequest):
#     symbol = request.symbol.upper().replace(".NS", "") + ".NS"

#     # ✅ Fetch live price before trade
#     try:
#         data = yf.Ticker(symbol).fast_info
#         price = float(data["last_price"])
#     except Exception:
#         price = 0.0

#     # Update portfolio (add or modify entry)
#     existing = next((p for p in portfolio if p["symbol"] == symbol), None)
#     if request.type == "buy":
#         if existing:
#             # Weighted average for new buy
#             total_qty = existing["amount"] + request.amount
#             existing["avg_buy_price"] = (
#                 (existing["avg_buy_price"] * existing["amount"] + price * request.amount)
#                 / total_qty
#             )
#             existing["amount"] = total_qty
#         else:
#             portfolio.append({
#                 "symbol": symbol,
#                 "amount": request.amount,
#                 "avg_buy_price": price,
#                 "current_price": price,
#                 "unrealized_profit": 0.0,
#             })
#     elif request.type == "sell":
#         if existing:
#             sell_qty = min(request.amount, existing["amount"])
#             existing["amount"] -= sell_qty
#             profit = (price - existing["avg_buy_price"]) * sell_qty
#             if existing["amount"] <= 0:
#                 portfolio.remove(existing)
#         else:
#             profit = 0.0

#     # ✅ Add to history
#     history.append({
#         "symbol": symbol,
#         "amount": request.amount,
#         "type": request.type,
#         "price": price,
#         "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
#         "profit": (price - existing["avg_buy_price"]) * request.amount if request.type == "sell" and existing else 0.0
#     })

#     return {"message": f"{request.type.capitalize()} successful", "price": price}


# # @router.get("/search_stocks")
# # async def search_stocks(query: str):
# #     import yfinance as yf
# #     import json

# #     symbols = [
# #         "RELIANCE.NS", "TCS.NS", "INFY.NS",
# #         "HDFCBANK.NS", "SBIN.NS", "ICICIBANK.NS",
# #         "ITC.NS", "WIPRO.NS", "HINDUNILVR.NS", "BHARTIARTL.NS"
# #     ]

# #     results = []
# #     for sym in symbols:
# #         if query.lower() in sym.lower():
# #             try:
# #                 ticker = yf.Ticker(sym)
# #                 info = ticker.fast_info
# #                 name = ticker.info.get("longName", sym)
# #                 price = info["last_price"]
# #                 results.append({
# #                     "symbol": sym,
# #                     "name": name,
# #                     "price": round(price, 2)
# #                 })
# #             except Exception:
# #                 pass

# #     return {"results": results}

# @router.get("/search_stocks")
# async def search_stocks(query: str):
#     import yfinance as yf

#     symbols = [
#         "RELIANCE.NS", "TCS.NS", "INFY.NS",
#         "HDFCBANK.NS", "SBIN.NS", "ICICIBANK.NS",
#         "ITC.NS", "WIPRO.NS", "HINDUNILVR.NS", "BHARTIARTL.NS"
#     ]

#     results = []
#     for sym in symbols:
#         if query.lower() in sym.lower():
#             try:
#                 ticker = yf.Ticker(sym)
#                 info = ticker.fast_info or {}
#                 name = ticker.info.get("longName") or sym.replace(".NS", "")
#                 # price = float(info.get("last_price") or 0.0)
#                 price = float(info.get("last_price") or ticker.history(period="1d")['Close'].iloc[-1])

#                 results.append({
#                     "symbol": sym,
#                     "name": name,
#                     "price": round(price, 2)
#                 })
#             except Exception as e:
#                 print(f"Error fetching {sym}: {e}")
#                 continue

#     return {"results": results}


# # Helpers
# def load_file(path):
#     if not os.path.exists(path):
#         return []
#     with open(path, "r") as f:
#         return json.load(f)

# def save_file(path, data):
#     with open(path, "w") as f:
#         json.dump(data, f, indent=4)

# @router.get("/stocks")
# def get_stocks():
#     """
#     Fetch live stock prices or use cached prices if API fails.
#     """

#     CACHE_FILE = "stocks_cache.json"
#     CACHE_EXPIRY_MIN = 5  # minutes

#     def load_cache():
#         if os.path.exists(CACHE_FILE):
#             try:
#                 with open(CACHE_FILE, "r") as f:
#                     data = json.load(f)
#                     # Expire old cache after 5 minutes
#                     if time.time() - data.get("timestamp", 0) < CACHE_EXPIRY_MIN * 60:
#                         return data.get("stocks", [])
#             except Exception as e:
#                 print(f"Cache load failed: {e}")
#         return []

#     def save_cache(stocks):
#         try:
#             with open(CACHE_FILE, "w") as f:
#                 json.dump({"timestamp": time.time(), "stocks": stocks}, f, indent=4)
#         except Exception as e:
#             print(f"Cache save failed: {e}")

#     # Try live Yahoo fetch first
#     symbols = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "SBIN.NS"]
#     stocks = []

#     try:
#         with httpx.Client(timeout=10.0) as client:
#             for sym in symbols:
#                 r = client.get(f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={sym}")
#                 data = r.json()
#                 result = data.get("quoteResponse", {}).get("result", [])
#                 if result:
#                     stock = result[0]
#                     stocks.append({
#                         "symbol": sym.replace(".NS", ""),
#                         "price": round(stock["regularMarketPrice"], 2)
#                     })
#         if stocks:
#             save_cache(stocks)
#             return {"stocks": stocks}
#     except Exception as e:
#         print(f"Yahoo API error: {e}")

#     # Fallback: load from cache
#     cached = load_cache()
#     if cached:
#         print("⚠️ Using cached prices.")
#         return {"stocks": cached, "cached": True}

#     # Final fallback: hardcoded base list
#     print("⚠️ Using fallback hardcoded stock prices.")
#     return {
#         "stocks": [
#             {"symbol": "RELIANCE", "price": 2400.0},
#             {"symbol": "TCS", "price": 3200.0},
#             {"symbol": "INFY", "price": 1450.0},
#             {"symbol": "HDFCBANK", "price": 1600.0},
#             {"symbol": "SBIN", "price": 620.0},
#         ],
#         "cached": True
#     }


# # GET endpoints
# @router.get("/portfolio")
# async def get_portfolio():
#     import httpx

#     portfolio = load_file(PORTFOLIO_FILE)
#     trades = load_file(TRADES_FILE)
#     live_prices = {}

#     # Fetch current stock prices safely
#     try:
#         async with httpx.AsyncClient(timeout=10.0) as client:
#             r = await client.get(STOCKS_URL)
#             data = r.json()
#             stocks = data.get("stocks", [])

#             if r.status_code == 200:
#                 data = r.json()
#                 stocks = data.get("stocks", [])
#                 if isinstance(stocks, list):
#                     for s in stocks:
#                         if isinstance(s, dict) and "symbol" in s and "price" in s:
#                             live_prices[s["symbol"]] = s["price"]
#             else:
#                 print(f"Stock fetch failed: HTTP {r.status_code}")
#     except Exception as e:
#         print(f"Live price fetch failed: {e}")

#     result = []
#     for item in portfolio:
#         try:
#             symbol = item["symbol"]
#             qty = item["amount"]
#             current_price = live_prices.get(symbol, 0.0)

#             # Get average buy price
#             buys = [t for t in trades if t["symbol"] == symbol and t["type"] == "buy"]
#             if buys:
#                 total_cost = sum(t["price"] * t["amount"] for t in buys)
#                 total_qty = sum(t["amount"] for t in buys)
#                 avg_buy_price = total_cost / total_qty if total_qty > 0 else 0.0
#             else:
#                 avg_buy_price = 0.0

#             # Calculate unrealized profit/loss
#             profit = (current_price - avg_buy_price) * qty if avg_buy_price > 0 else 0.0

#             result.append({
#                 "symbol": symbol,
#                 "amount": qty,
#                 "avg_buy_price": round(avg_buy_price, 2),
#                 "current_price": round(current_price, 2),
#                 "unrealized_profit": round(profit, 2),
#             })
#         except Exception as e:
#             print(f"Portfolio entry error for {item}: {e}")

#     return {"portfolio": result}



# @router.get("/history")
# def get_trade_history():
#     trades = load_file(TRADES_FILE)
#     return {"history": trades}

# # POST endpoint
# @router.post("/trade")
# async def make_trade(request: Request):
#     data = await request.json()
#     symbol = data["symbol"]
#     amount = float(data["amount"])
#     trade_type = data["type"]

#     # Load existing data
#     portfolio = load_file(PORTFOLIO_FILE)
#     trades = load_file(TRADES_FILE)

#     # --- Fetch current price ---
#     price = 0.0
#     try:
#         async with httpx.AsyncClient() as client:
#             r = await client.get(STOCKS_URL)
#             stocks = r.json().get("stocks", [])
#             for s in stocks:
#                 if s["symbol"] == symbol:
#                     price = s["price"]
#                     break
#     except Exception as e:
#         print(f"Price fetch failed: {e}")

#     # --- Update portfolio ---
#     found = False
#     for item in portfolio:
#         if item["symbol"] == symbol:
#             if trade_type == "buy":
#                 item["amount"] += amount
#             elif trade_type == "sell":
#                 item["amount"] = max(0, item["amount"] - amount)
#             found = True
#             break
#     if not found and trade_type == "buy":
#         portfolio.append({"symbol": symbol, "amount": amount})

#     # --- Calculate profit/loss for sell trades ---
#     profit = 0.0
#     if trade_type == "sell":
#         # find last buy price for that stock (if any)
#         previous_trades = [t for t in trades if t["symbol"] == symbol and t["type"] == "buy"]
#         if previous_trades:
#             last_buy_price = previous_trades[-1]["price"]
#             profit = (price - last_buy_price) * amount

#     # --- Log trade ---
#     trade = {
#         "symbol": symbol,
#         "amount": amount,
#         "type": trade_type,
#         "timestamp": datetime.now().isoformat(timespec="seconds"),
#         "price": price,
#         "profit": profit,
#     }
#     trades.append(trade)

#     # Save data
#     save_file(PORTFOLIO_FILE, portfolio)
#     save_file(TRADES_FILE, trades)

#     print(f"Trade saved: {trade}")

#     return {"message": "Trade successful", "portfolio": portfolio, "trade": trade}


from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app import db
from app.services import dhan_service
from typing import Any
import logging

router = APIRouter()
logger = logging.getLogger("trading")

class TradeRequest(BaseModel):
    symbol: str
    amount: float
    type: str  # 'buy' or 'sell'

@router.post("/trade")
def trade(req: TradeRequest):
    # validate
    symbol = req.symbol.upper()
    amount = req.amount
    typ = req.type.lower()
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be > 0")
    if typ not in ("buy", "sell"):
        raise HTTPException(status_code=400, detail="type must be 'buy' or 'sell'")

    # fetch live price
    price_resp = dhan_service.get_live_price(symbol)
    price = float(price_resp.get("price", 0.0))
    if price <= 0:
        # allow trade but warn — or block; here we return error
        raise HTTPException(status_code=400, detail=f"No live price for {symbol}")

    # place order (real or simulated)
    order_resp = dhan_service.place_order_dhan(symbol, amount, typ)

    # If simulated OR successful, update local DB
    status = order_resp.get("status", "simulated")
    if status in ("success", "simulated"):
        # For buys: update holdings and history
        if typ == "buy":
            db.upsert_holding(symbol, amount, price)
            db.add_history(symbol, typ, amount, price, None)
        else:  # sell
            # compute simple P/L = (price - avg_buy) * amount
            # fetch current avg buy
            holdings = {h["symbol"]: h for h in db.get_portfolio()}
            avg_buy = holdings.get(symbol, {}).get("avg_buy_price", 0.0)
            pnl = (price - avg_buy) * amount
            # update holdings (negative amount reduces)
            db.upsert_holding(symbol, -amount, price)  # avg_buy_price param isn't used for sells inside upsert logic
            db.add_history(symbol, typ, amount, price, pnl)
        return {"status": "ok", "order": order_resp}
    else:
        raise HTTPException(status_code=500, detail={"order_error": order_resp})

@router.get("/portfolio")
def portfolio():
    holdings = db.get_portfolio()
    # augment with current prices (best-effort)
    out = []
    for h in holdings:
        price_resp = dhan_service.get_live_price(h["symbol"])
        current = float(price_resp.get("price", 0.0))
        unrealized = (current - h["avg_buy_price"]) * h["amount"]
        out.append({
            "symbol": h["symbol"],
            "amount": h["amount"],
            "avg_buy_price": h["avg_buy_price"],
            "current_price": current,
            "unrealized_profit": unrealized
        })
    return {"portfolio": out}

@router.get("/history")
def history():
    h = db.get_history(limit=1000)
    # format timestamp -> ISO if you want
    return {"history": h}
