from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import os, re, base64, json, time
from datetime import datetime, timezone, timedelta
from ..db import SessionLocal
from .. import crud, models, schemas
from ..auth import get_current_user
from ..config import config

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ── Dhan token status ──────────────────────────────────────────────────────────

@router.get("/api/admin/token-status")
def get_token_status(_: str = Depends(get_current_user)):
    """
    Decode the Dhan ACCESS_TOKEN and return expiry + auto-renewal state.
    """
    from app.services import token_renewal as tr

    token = config.ACCESS_TOKEN
    result: dict = {"client_id": config.CLIENT_ID}

    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Not a valid JWT")

        padding = 4 - len(parts[1]) % 4
        padded  = parts[1] + ("=" * (padding % 4))
        payload = json.loads(base64.urlsafe_b64decode(padded))

        exp_ts = payload.get("exp")
        iat_ts = payload.get("iat")

        if exp_ts is None:
            result.update({"valid": False, "error": "No expiry claim in token"})
        else:
            now_ts             = time.time()
            expires_in_seconds = exp_ts - now_ts
            is_valid           = expires_in_seconds > 0

            result.update({
                "valid":              is_valid,
                "expires_at":         datetime.fromtimestamp(exp_ts, tz=timezone.utc).isoformat(),
                "issued_at":          datetime.fromtimestamp(iat_ts, tz=timezone.utc).isoformat() if iat_ts else None,
                "expires_in_hours":   round(expires_in_seconds / 3600, 2) if is_valid else 0.0,
                "expires_in_minutes": round(expires_in_seconds / 60,   1) if is_valid else 0.0,
            })

    except Exception as e:
        result.update({"valid": False, "error": f"Could not decode token: {e}"})

    # ── Auto-renewal metadata ─────────────────────────────────────────────────
    next_renewal_secs = tr._seconds_until_next_renewal()

    # Use the scheduler's stored _next_renewal_at if available, else compute
    next_renewal_epoch = (
        tr._next_renewal_at
        if tr._next_renewal_at is not None
        else time.time() + next_renewal_secs
    )
    next_renewal_iso = datetime.fromtimestamp(
        next_renewal_epoch, tz=timezone.utc
    ).isoformat()

    # Determine renewal reason for the UI
    stored_exp = tr._stored_exp_ts
    if stored_exp:
        ist_h = int(((stored_exp + tr.IST_OFFSET_S) % 86400) // 3600)
        ist_m = int(((stored_exp + tr.IST_OFFSET_S) % 3600) // 60)
        exp_min = ist_h * 60 + ist_m
        market_start = tr.MARKET_START_H * 60 + tr.MARKET_START_M
        market_end   = tr.MARKET_END_H   * 60 + tr.MARKET_END_M
        renewal_reason = (
            "expires during market hours → renewing at 8:15 AM IST"
            if market_start <= exp_min <= market_end
            else "1 hour before expiry"
        )
    else:
        renewal_reason = "schedule not yet initialised"

    result["auto_renewal"] = {
        "last_renewal_at":       datetime.fromtimestamp(tr.last_renewal_at, tz=timezone.utc).isoformat()
                                 if tr.last_renewal_at else None,
        "last_renewal_ok":       tr.last_renewal_ok,
        "last_renewal_error":    tr.last_renewal_error,
        "next_renewal_at":       next_renewal_iso,
        "next_renewal_in_hours": round(next_renewal_secs / 3600, 1),
        "renewal_reason":        renewal_reason,
    }

    return result


@router.get("/api/admin/limits")
def get_limits(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    user = crud.get_user(db, 'admin')
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "daily_limit": user.max_daily_dd,
        "monthly_limit": user.max_monthly_dd,
        "daily_spent": 0,
        "monthly_spent": 0,
        "tokens": user.capital_current
    }

@router.post("/api/admin/limits")
def set_limits(limits: schemas.LimitUpdate, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    user = crud.get_user(db, 'admin')
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.max_daily_dd = limits.max_daily_dd
    user.max_monthly_dd = limits.max_monthly_dd
    db.add(user)
    db.commit()
    return {"status": "ok", "message": "Risk Limits updated", "daily_limit": user.max_daily_dd, "monthly_limit": user.max_monthly_dd}

@router.post("/api/admin/reset_spent")
def reset_spent(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    return {"status": "ok", "message": "Spend counters resetting deprecated"}


# ── Dhan token rotation ────────────────────────────────────────────────────────

class TokenUpdateRequest(BaseModel):
    access_token: str
    client_id: Optional[str] = None   # only supply if your client ID also changed

def _rewrite_env_key(key: str, value: str) -> None:
    """Update a single key=value line in .env without touching anything else."""
    env_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    )
    try:
        with open(env_path, "r") as f:
            lines = f.readlines()

        pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
        replaced = False
        new_lines = []
        for line in lines:
            if pattern.match(line):
                new_lines.append(f"{key}={value}\n")
                replaced = True
            else:
                new_lines.append(line)

        if not replaced:           # key wasn't in .env yet — append it
            new_lines.append(f"{key}={value}\n")

        with open(env_path, "w") as f:
            f.writelines(new_lines)
    except Exception as e:
        print(f"⚠️  Could not persist token to .env: {e}")


@router.post("/api/admin/update-dhan-token")
def update_dhan_token(body: TokenUpdateRequest, _: str = Depends(get_current_user)):
    """
    Hot-swap the Dhan ACCESS_TOKEN without restarting the server.
    Also writes the new value to .env so it survives restarts.
    Requires a valid JWT (Bearer token) in the Authorization header.
    """
    config.ACCESS_TOKEN = body.access_token
    _rewrite_env_key("ACCESS_TOKEN", body.access_token)

    if body.client_id:
        config.CLIENT_ID = body.client_id
        _rewrite_env_key("CLIENT_ID", body.client_id)

    print("🔑 Dhan ACCESS_TOKEN rotated in-memory and persisted to .env")
    return {"status": "ok", "message": "Dhan token updated. No restart needed."}


# ── Canonical Portfolio/Trade Endpoints ─────────────────────────────────────

@router.get("/api/portfolio")
def get_portfolio(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    """
    Canonical portfolio endpoint. 
    Currently returns empty list (Sandbox). Wire to PortfolioMetrics later.
    """
    return []

@router.get("/api/trades")
def get_trades(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    """
    Canonical trades endpoint. Returns the last 50 orders for the admin user.
    """
    user = crud.get_user(db, 'admin')
    if not user:
        return []
        
    orders = db.query(models.Order).filter(models.Order.user_id == user.id).order_by(models.Order.created_at.desc()).limit(50).all()
    
    # Format to match frontend expectations
    return [{
        "order_id": ord.broker_order_id or f"INT-{ord.id}",
        "symbol": ord.symbol,
        "qty": ord.quantity,
        "side": "BUY" if ord.direction == models.Direction.LONG else "SELL",
        "price": float(ord.entry_price),
        "pnl": float(ord.pnl or 0.0),
        "status": ord.status.value,
        "created_at": ord.created_at
    } for ord in orders]

# ── Health & Diagnostics ─────────────────────────────────────────────────────

@router.get("/api/admin/health")
def get_system_health(_: str = Depends(get_current_user)):
    """
    Combined health endpoint for Broker Token and Market Feed WS statuses.
    """
    from app.websocket import market_ws
    
    token_data = get_token_status(_)
    
    last_tick = getattr(market_ws, 'last_ws_msg_time', 0)
    
    return {
        "status": "ok",
        "token": token_data,
        "feed": {
            "connected": market_ws._ws is not None,
            "reconnecting": market_ws._running and market_ws._ws is None,
            "stale": market_ws.stale_feed_active,
            "last_tick_time": datetime.fromtimestamp(last_tick, tz=timezone.utc).isoformat() if last_tick else None,
            "reconnect_count": market_ws._reconnect_count,
            "sub_count": len(market_ws._subscribe_symbols)
        }
    }
