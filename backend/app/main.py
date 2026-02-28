# from fastapi import FastAPI
# from .db import Base, engine
# from .routes import market, trade, admin
# from app.routes import admin, trading, market_live
# import uvicorn
# import asyncio
# from .ai_engine import simple_momentum_loop
# from fastapi.middleware.cors import CORSMiddleware
# from app.routes import market_ws
# from dotenv import load_dotenv
# load_dotenv()


# app = FastAPI(title="AI Stock Trader Alpha")
# # create tables
# Base.metadata.create_all(bind=engine)


# app.include_router(market_ws.router)
# app.include_router(market_live.router)
# app.include_router(market.router)
# app.include_router(trade.router)
# app.include_router(admin.router)
# app.include_router(trading.router)
# @app.on_event("startup")
# async def startup_event():
#     # create default user
#     from .crud import create_default_user
#     db = engine.connect()
#     create_default_user.__self__ if False else None
#     create_default_user(__import__('sqlalchemy').orm.session.Session(engine))  # placeholder

#     # Start background AI loop
#     asyncio.create_task(simple_momentum_loop(60))

# if __name__ == "__main__":
#     uvicorn.run("app.main:app", host="10.0.2.2", port=8000, reload=True)

# import sys, os
# sys.path.append(os.path.dirname(__file__))
# from fastapi import FastAPI, WebSocket
# import asyncio
# from app.websocket.market_ws import feed, dhan_ws_task
# from app.services.dhan_service import find_instrument

# app = FastAPI()

# @app.on_event("startup")
# async def startup_event():
#     asyncio.create_task(dhan_ws_task())

# @app.websocket("/ws/market")
# async def market_socket(websocket: WebSocket):
#     await websocket.accept()
#     feed.connected_clients.add(websocket)
#     print("📲 Flutter client connected.")

#     try:
#         while True:
#             data = await websocket.receive_text()
#             if data.startswith("SUB:"):
#                 symbol = data.split(":")[1].strip().upper()
#                 inst = find_instrument(symbol)
#                 if inst:
#                     await feed.subscribe([f"{inst['exchange']}:{inst['symbol']}"])
#     except Exception as e:
#         print(f"⚠️ WebSocket closed: {e}")
#     finally:
#         feed.connected_clients.remove(websocket)
#     print("❌ Flutter client disconnected.")

    # Cleanup subscriptions if needed

# import asyncio
# from fastapi import FastAPI
# from app.routes.market_live import router as market_router
# from app.websocket.market_ws import start_ws_background_task
# from app.routes.ticks import router as ticks_router
# from app.core.instruments import load_instruments
# from app.websocket.market_ws import subscribe_symbols


# app = FastAPI(title="Dhan API Backend")



# @app.on_event("startup")
# async def startup_event():
#     load_instruments()
#     subscribe_symbols(["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"])
#     asyncio.create_task(start_ws_background_task())


# @app.get("/")
# def root():
#     return {"status": "running", "message": "Backend online"}


# app.include_router(market_router)
# app.include_router(ticks_router)


import asyncio
from fastapi import FastAPI

from app.routes.market_live import router as market_router
from app.routes.ticks import router as ticks_router
# from app.core.tick_store import get_cached_ltp
from app.websocket.market_ws import start_ws_background_task, subscribe_symbols
from app.core.instruments import load_instruments
from app.routes.admin import router as admin_router
from app.routes import ws, ws_routes
from app.db import engine, Base
from app.config import config  # needed for JWT_SECRET startup check
# Create tables
Base.metadata.create_all(bind=engine)


app = FastAPI(title="Dhan API Backend")

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# @app.on_event("startup")
# async def startup_event():
#     # Load instrument CSV → builds sid_to_symbol map
#     load_instruments()

#     # Subscribe to desired symbols before websocket starts
#     subscribe_symbols(["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"])

#     # Start websocket loop
#     asyncio.create_task(start_ws_background_task())

@app.on_event("startup")
async def startup_event():
    # ── Security guard ─────────────────────────────────────────────────────────
    if len(config.JWT_SECRET) < 32:
        import sys
        print(
            "\n" + "=" * 70 + "\n"
            "⚠️  SECURITY WARNING: JWT_SECRET is too short (< 32 chars).\n"
            "   Set a long random string in your .env file before deploying.\n"
            "   Generate one with:  python -c \"import secrets; print(secrets.token_hex(32))\"\n"
            + "=" * 70 + "\n",
            file=sys.stderr,
        )

    # Create default user (Sandbox)
    from app.crud import create_default_user
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        create_default_user(db)
    finally:
        db.close()

    # Load instrument CSV → builds sid_to_symbol map
    try:
        load_instruments()
    except Exception as e:
        print(f"⚠️ Instrument load failed: {e}")

    # Start Live Dhan WebSocket
    from app.websocket.market_ws import start_ws_background_task, subscribe_symbols
    
    # Subscribe to main watchlist
    # Ensure these match SEM_TRADING_SYMBOL in CSV
    subscribe_symbols([
        "RELIANCE", "TCS", "INFY", "HDFCBANK", 
        "SBIN", "ICICIBANK", "AXISBANK", "KOTAKBANK",
        "ITC", "LT", "BHARTIARTL", "ASIANPAINT",
        "MARUTI", "HCLTECH", "SUNPHARMA", "TITAN",
        "BAJFINANCE", "ULTRACEMCO", "M&M", "TATASTEEL"
    ])
    
    asyncio.create_task(start_ws_background_task())

    # Start AI Engine (Sandbox)
    from app.ai_engine import simple_momentum_loop
    asyncio.create_task(simple_momentum_loop())

    # Start Dhan token auto-renewal (daily at 08:15 IST, 1h before market open)
    from app.services.token_renewal import token_renewal_loop
    asyncio.create_task(token_renewal_loop())



@app.get("/")
def root():
    return {"status": "running", "message": "Backend online"}


app.include_router(market_router, prefix="/api/market")
app.include_router(ticks_router)
app.include_router(admin_router)

# Auth
from app.routes.auth_routes import router as auth_router
app.include_router(auth_router)

# Include the Live WebSocket Proxy Router
from app.websocket import market_ws
app.include_router(market_ws.router)

from app.routes import trade
app.include_router(trade.router)
