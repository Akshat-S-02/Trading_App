import asyncio
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..auth import get_current_user
from ..core.alerts import async_dispatch_alert
from ..db import get_db
from ..engines.risk_engine import RiskGate, month_realized_pnl
from ..services import token_renewal
from ..websocket import market_ws

_IST = ZoneInfo("Asia/Kolkata")
router = APIRouter()


def _admin_user(db: Session) -> models.User:
    user = crud.get_user(db, "admin")
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/api/admin/limits")
def get_limits(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    """Loss limits and today's / this month's realised loss, all as % of capital."""
    user = _admin_user(db)
    RiskGate.check_intraday_reset(db, user)  # realized_pnl is today's only after a reset
    capital = float(user.capital_current or 0)
    day_pnl = float(user.portfolio_metrics.realized_pnl or 0) if user.portfolio_metrics else 0.0
    month_pnl = float(month_realized_pnl(db, user))
    loss_pct = lambda pnl: round(max(0.0, -pnl) / capital * 100, 2) if capital > 0 else 0.0
    return {
        "daily_limit": user.max_daily_dd,
        "monthly_limit": user.max_monthly_dd,
        "daily_spent": loss_pct(day_pnl),
        "monthly_spent": loss_pct(month_pnl),
        "tokens": user.capital_current
    }

@router.post("/api/admin/limits")
def set_limits(limits: schemas.LimitUpdate, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    user = _admin_user(db)
    user.max_daily_dd = limits.max_daily_dd
    user.max_monthly_dd = limits.max_monthly_dd
    db.commit()
    return {"status": "ok", "message": "Risk Limits updated", "daily_limit": user.max_daily_dd, "monthly_limit": user.max_monthly_dd}

# ── Canonical Portfolio/Trade Endpoints ─────────────────────────────────────

class PortfolioResponse(BaseModel):
    realized_pnl: float
    peak_equity: float
    win_rate: float
    consecutive_loss_days: int
    consecutive_dd_hits: int
    total_trades_today: int
    winning_trades_today: int
    losing_trades_today: int
    gross_pnl_today: float

@router.get("/api/portfolio", response_model=PortfolioResponse)
def get_portfolio(db: Session = Depends(get_db), current_username: str = Depends(get_current_user)):
    """
    Canonical portfolio endpoint returning metrics and today's summary.
    """
    user = db.query(models.User).filter(models.User.username == current_username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    metrics = db.query(models.PortfolioMetrics).filter(models.PortfolioMetrics.user_id == user.id).first()

    # "Today" is the IST trading day (UTC midnight is 05:30 IST).
    start_of_day = datetime.now(_IST).replace(hour=0, minute=0, second=0, microsecond=0)

    # Trades = positions opened today; wins / losses / win rate / P&L = those closed today.
    opened_today = db.query(models.Order).filter(
        models.Order.user_id == user.id,
        models.Order.status.in_([models.OrderStatus.FILLED, models.OrderStatus.CLOSED]),
        models.Order.created_at >= start_of_day,
    ).count()
    closed_today = db.query(models.Order).filter(
        models.Order.user_id == user.id,
        models.Order.status == models.OrderStatus.CLOSED,
        models.Order.close_requested_at >= start_of_day,
    ).all()
    wins = sum(1 for o in closed_today if (o.pnl or 0) > 0)
    losses = sum(1 for o in closed_today if (o.pnl or 0) < 0)

    return PortfolioResponse(
        # All-time realised net P&L: capital only changes when a position closes.
        realized_pnl=float(user.capital_current or 0) - float(user.capital_initial or 0),
        peak_equity=float(metrics.peak_equity) if metrics else 0.0,
        win_rate=round(100.0 * wins / len(closed_today), 1) if closed_today else 0.0,
        consecutive_loss_days=metrics.consecutive_loss_days if metrics else 0,
        consecutive_dd_hits=metrics.consecutive_dd_hits if metrics else 0,
        total_trades_today=opened_today,
        winning_trades_today=wins,
        losing_trades_today=losses,
        gross_pnl_today=float(sum((o.pnl or 0) for o in closed_today)),
    )

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
        "id": ord.id,
        "order_id": ord.broker_order_id or f"INT-{ord.id}",
        "symbol": ord.symbol,
        "qty": ord.quantity,
        "side": "BUY" if ord.direction == models.Direction.LONG else "SELL",
        "price": float(ord.average_price or ord.entry_price),
        "exit_price": float(ord.exit_price) if ord.exit_price is not None else None,
        "exit_reason": ord.exit_reason,
        "pnl": float(ord.pnl or 0.0),
        "status": ord.status.value,
        "strategy_name": ord.strategy_name,
        "source": "manual" if ord.strategy_name == "manual" else "auto",
        "created_at": ord.created_at
    } for ord in orders]

# ── Health & Diagnostics ─────────────────────────────────────────────────────

@router.get("/api/admin/health")
def get_system_health(_: str = Depends(get_current_user)):
    """Dhan token and market feed status for the app's Health screen."""
    next_renewal = time.time() + token_renewal._seconds_until_next_renewal()
    last_msg = market_ws.last_ws_msg_time
    return {
        "status": "ok",
        "token": {
            "valid": token_renewal.is_token_valid(),
            "auto_renewal": {"next_renewal_at": datetime.fromtimestamp(next_renewal, tz=timezone.utc).isoformat()},
        },
        "feed": {
            "connected": market_ws._ws is not None,
            "reconnecting": market_ws._running and market_ws._ws is None,
            "stale": market_ws.stale_feed_active,
            "last_tick_time": datetime.fromtimestamp(last_msg, tz=timezone.utc).isoformat() if last_msg else None,
            "reconnect_count": market_ws._reconnect_count,
            "sub_count": len(market_ws._subscribe_symbols),
        },
    }


# ── Emergency Stop (Global Circuit Breaker) ────────────────────────────────────

@router.post("/api/admin/emergency-stop")
async def trip_emergency_stop(db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    """
    Global kill-switch. Sets SystemSettings.emergency_stop: RiskGate refuses
    new signals and the manual order route refuses new orders while it's set.
    The market feed keeps running on purpose: the exit monitor needs live
    prices to keep enforcing stop-loss / target / EOD on open positions.
    """
    settings = db.query(models.SystemSettings).first()
    if not settings:
        settings = models.SystemSettings()
        db.add(settings)
    settings.emergency_stop = True
    db.commit()

    asyncio.create_task(async_dispatch_alert(
        level="CRITICAL",
        title="EMERGENCY STOP TRIPPED",
        message=f"Global circuit breaker triggered by '{user}'. New orders blocked. Open positions stay under stop-loss / target / EOD monitoring."
    ))

    return {"status": "ok", "emergency_stop": True}


@router.post("/api/admin/automation/enable")
def enable_automation(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    """
    Turn automated trading back on after a risk guard halted it. Also clears the
    losing-streak counters, otherwise the streak guards halt it again on the next
    signal. The daily / monthly loss limits still apply as usual.
    """
    user = _admin_user(db)
    user.automation_enabled = True
    if user.portfolio_metrics:
        user.portfolio_metrics.consecutive_dd_hits = 0
        user.portfolio_metrics.consecutive_loss_days = 0
    db.commit()
    return {"status": "ok", "automation_enabled": True}


@router.post("/api/admin/emergency-stop/clear")
def clear_emergency_stop(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    """
    Clears the emergency_stop flag so RiskGate resumes accepting new signals.
    """
    settings = db.query(models.SystemSettings).first()
    if settings:
        settings.emergency_stop = False
        db.commit()
    return {"status": "ok", "emergency_stop": False}
