import sys
if sys.platform == "win32":
    # Force utf-8 encoding on Windows console to prevent emoji crashes
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import asyncio
from fastapi import FastAPI

from app.routes.market_live import router as market_router
from app.routes.ticks import router as ticks_router
from app.websocket.market_ws import start_ws_background_task, subscribe_symbols
from app.core.instruments import load_instruments
from app.routes.admin import router as admin_router
from app.db import engine, Base
from app.config import config
from app.workers.nightly_learning_job import run_nightly_job
from apscheduler.schedulers.asyncio import AsyncIOScheduler
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

    # ── SEBI static-IP compliance guard ──────────────────────────────────────
    # From April 2026, Dhan requires order-placing API calls to originate from
    # an IP whitelisted on the account. Refuse to boot in live mode until that's
    # confirmed — this is a regulatory/account-safety gate, not a warning.
    if config.EXECUTION_MODE.lower() == "live" and not config.DHAN_STATIC_IP_CONFIRMED:
        raise RuntimeError(
            "EXECUTION_MODE=live but DHAN_STATIC_IP_CONFIRMED is not set. "
            "Whitelist this host's outbound IP with Dhan (required from April 2026), "
            "then set DHAN_STATIC_IP_CONFIRMED=true in .env to confirm."
        )

    # Create default user (Sandbox)
    from app.crud import create_default_user
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        create_default_user(db)
    finally:
        db.close()

    # 1. Validate / Refresh Token synchronously
    import time
    from app.services.token_renewal import _token_exp, _do_renewal
    exp = _token_exp(config.ACCESS_TOKEN)
    if not exp or exp < time.time():
        print("⚠️ Token is missing or expired at startup. Force-renewing now...", flush=True)
        success = await _do_renewal()
        if not success:
            print("🚨 FATAL: Could not acquire valid Dhan token at startup. Exec engine will fail.", flush=True)
    else:
        import app.services.token_renewal as _tr
        _tr.last_renewal_ok = True  # a valid token at boot is a healthy token
        print("✅ Token validated at startup.", flush=True)

    # 2. Load instrument CSV → builds sid_to_symbol map
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
    
    # Start Paper Strategy Runner (Position Monitor)
    from app.engines.paper_strategy_runner import get_runner
    runner = get_runner()
    runner.start()

    asyncio.create_task(start_ws_background_task())


    # Start Dhan token auto-renewal (daily at 08:15 IST, 1h before market open)
    from app.services.token_renewal import token_renewal_loop
    asyncio.create_task(token_renewal_loop())

    # Start APScheduler for Nightly Learning Job
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_nightly_job, 
        'cron', 
        day_of_week='mon-fri', 
        hour=16, 
        minute=0, 
        timezone='Asia/Kolkata'
    )
    scheduler.start()
    print("✅ APScheduler started. Nightly Learning Job scheduled at 16:00 IST (Mon-Fri).")



@app.get("/")
def root():
    return {"status": "running", "message": "Backend online"}


from fastapi import Depends
from app.auth import get_current_user

# Every router except login and the WebSocket proxy (which checks ?token=) needs a valid JWT.
_auth = [Depends(get_current_user)]

app.include_router(market_router, prefix="/api/market", dependencies=_auth)
app.include_router(ticks_router, dependencies=_auth)
app.include_router(admin_router)

# Auth
from app.routes.auth_routes import router as auth_router
app.include_router(auth_router)

# Include the Live WebSocket Proxy Router
from app.websocket import market_ws
app.include_router(market_ws.router)

from app.routes import trade
app.include_router(trade.router)

# Paper Trading Engine
from app.routes.paper import router as paper_router
app.include_router(paper_router, dependencies=_auth)
