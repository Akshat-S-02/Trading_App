import asyncio
import sys
import time

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.services.token_renewal as token_renewal
from app.auth import get_current_user
from app.config import config
from app.core.instruments import load_instruments
from app.crud import create_default_user
from app.db import Base, SessionLocal, engine
from app.engines.paper_strategy_runner import get_runner
from app.routes import trade
from app.routes.admin import router as admin_router
from app.routes.auth_routes import router as auth_router
from app.routes.market_live import router as market_router
from app.routes.notifications import router as notifications_router
from app.routes.paper import router as paper_router
from app.websocket import market_ws
from app.workers.nightly_learning_job import run_nightly_job

if sys.platform == "win32":
    # emoji in print() crash the default Windows console encoding
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Dhan API Backend")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

WATCHLIST = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "SBIN", "ICICIBANK", "AXISBANK", "KOTAKBANK",
    "ITC", "LT", "BHARTIARTL", "ASIANPAINT", "MARUTI", "HCLTECH", "SUNPHARMA", "TITAN",
    "BAJFINANCE", "ULTRACEMCO", "M&M", "TATASTEEL",
]


@app.on_event("startup")
async def startup_event():
    if len(config.JWT_SECRET) < 32:
        print("⚠️  SECURITY WARNING: JWT_SECRET is shorter than 32 chars. Set a long random "
              "string in .env:  python -c \"import secrets; print(secrets.token_hex(32))\"",
              file=sys.stderr)
    # The SEBI static-IP gate for live mode is enforced when config loads (app/config.py).

    db = SessionLocal()
    try:
        create_default_user(db)
    finally:
        db.close()

    exp = token_renewal._token_exp(config.ACCESS_TOKEN)
    if not exp or exp < time.time():
        print("⚠️ Token is missing or expired at startup. Force-renewing now...", flush=True)
        if not await token_renewal._do_renewal():
            print("🚨 FATAL: Could not acquire valid Dhan token at startup. Exec engine will fail.", flush=True)
    else:
        print("✅ Token validated at startup.", flush=True)

    try:
        load_instruments()
    except Exception as e:
        print(f"⚠️ Instrument load failed: {e}")

    market_ws.subscribe_symbols(WATCHLIST)
    get_runner().start()  # position monitor: SL / target / EOD exits
    asyncio.create_task(market_ws.start_ws_background_task())
    asyncio.create_task(token_renewal.token_renewal_loop())  # daily 08:15 IST

    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_nightly_job, "cron", day_of_week="mon-fri", hour=16, minute=0,
                      timezone="Asia/Kolkata")
    scheduler.start()
    print("✅ APScheduler started. Nightly Learning Job scheduled at 16:00 IST (Mon-Fri).")


@app.get("/")
def root():
    return {"status": "running", "message": "Backend online"}


# Every router except login and the WebSocket proxy (which checks ?token=) needs a valid JWT.
# admin and trade check it per route.
_auth = [Depends(get_current_user)]
app.include_router(market_router, prefix="/api/market", dependencies=_auth)
app.include_router(paper_router, dependencies=_auth)
app.include_router(notifications_router, dependencies=_auth)
app.include_router(admin_router)
app.include_router(trade.router)
app.include_router(auth_router)
app.include_router(market_ws.router)
