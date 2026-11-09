"""
Manual trading endpoints (paper mode only).

Manual orders go through the same canonical path as strategy orders:
Signal row (carries SL/target) -> Order (NEW) -> OutboxEvent -> OutboxWorker
-> PaperBroker fill. Once FILLED, the PaperStrategyRunner position monitor
manages SL / target / EOD exits for them exactly like automated positions.

Live mode is refused: live exits are not yet sent to Dhan, so a manual live
position could not be closed from here.
"""
import uuid
from datetime import datetime, time as dt_time, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from .. import crud, models
from ..auth import get_current_user
from ..config import config
from ..db import SessionLocal
from ..core.tick_store import MAX_TICK_AGE_S, get_cached_ltp, get_live_ltp, get_tick
from ..engines.paper_strategy_runner import EOD_CUTOFF

router = APIRouter(prefix="/api/trade", tags=["manual-trade"])

MANUAL_STRATEGY_NAME = "manual"
_IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN = dt_time(9, 15)

# Orders accepted but not yet filled
PENDING_STATUSES = [
    models.OrderStatus.NEW,
    models.OrderStatus.ENQUEUED,
    models.OrderStatus.SENDING,
    models.OrderStatus.SUBMITTED,
    models.OrderStatus.BROKER_ACK,
    models.OrderStatus.CONFIRMED,
    models.OrderStatus.PARTIALLY_FILLED,
    models.OrderStatus.FAILED_RETRYABLE,
]


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class ManualOrderIn(BaseModel):
    symbol: str
    qty: int = Field(gt=0)
    side: Literal["BUY", "SELL"]
    stop_loss: Optional[float] = Field(default=None, gt=0)
    target: Optional[float] = Field(default=None, gt=0)


class BracketUpdate(BaseModel):
    stop_loss: Optional[float] = Field(default=None, gt=0)
    target: Optional[float] = Field(default=None, gt=0)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _bare_symbol(symbol: str) -> str:
    """'RELIANCE.NS' -> 'RELIANCE' (tick store and orders use bare symbols)."""
    s = symbol.strip().upper()
    for suffix in (".NS", ".BO"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    return s


def _ltp(symbol: str) -> Optional[float]:
    try:
        tick = get_tick(symbol)
    except Exception:
        tick = None
    if not tick or not tick.get("ltp"):
        tick = get_cached_ltp(symbol)
    if tick and tick.get("ltp"):
        return float(tick["ltp"])
    return None


def _live_ltp_or_409(symbol: str) -> float:
    """Fresh price for placing / closing at market. A stale tick (feed down,
    symbol not trading, yesterday's close) would create a fake fill."""
    ltp = get_live_ltp(symbol)
    if ltp is None:
        raise HTTPException(
            409,
            f"No live price for {symbol} in the last {MAX_TICK_AGE_S}s. "
            "The market feed may be down; try again shortly.",
        )
    return ltp


def _require_market_open():
    """Manual orders only while an intraday entry can actually live: 09:15 to
    the 15:20 EOD square-off, Monday-Friday (IST)."""
    now = datetime.now(_IST)
    if now.weekday() >= 5 or not (MARKET_OPEN <= now.time() < EOD_CUTOFF):
        raise HTTPException(
            409,
            f"Market is closed. Manual orders are accepted 09:15–"
            f"{EOD_CUTOFF.strftime('%H:%M')} IST, Monday to Friday.",
        )


def _require_paper_mode():
    if config.EXECUTION_MODE.lower() != "paper":
        raise HTTPException(
            status_code=409,
            detail="Manual trading is only available in paper mode.",
        )


def _get_user(db: Session, username: str) -> models.User:
    user = crud.get_user(db, username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _validate_bracket(is_long: bool, ref_price: float, stop_loss: Optional[float], target: Optional[float]):
    """SL must sit on the losing side of the reference price, target on the winning side."""
    if is_long:
        if stop_loss is not None and stop_loss >= ref_price:
            raise HTTPException(422, f"Stop-loss for a BUY must be below the current price ({ref_price:.2f}).")
        if target is not None and target <= ref_price:
            raise HTTPException(422, f"Target for a BUY must be above the current price ({ref_price:.2f}).")
    else:
        if stop_loss is not None and stop_loss <= ref_price:
            raise HTTPException(422, f"Stop-loss for a SELL must be above the current price ({ref_price:.2f}).")
        if target is not None and target >= ref_price:
            raise HTTPException(422, f"Target for a SELL must be below the current price ({ref_price:.2f}).")


def _order_dict(o: models.Order) -> dict:
    is_long = o.direction == models.Direction.LONG
    avg = float(o.average_price) if o.average_price is not None else None
    entry = float(o.entry_price) if o.entry_price is not None else None
    d = {
        "id": o.id,
        "symbol": o.symbol,
        "side": "BUY" if is_long else "SELL",
        "qty": o.quantity,
        "filled_qty": o.filled_quantity or 0,
        "entry_price": entry,
        "avg_price": avg,
        "status": o.status.value,
        "strategy_name": o.strategy_name,
        "source": "manual" if o.strategy_name == MANUAL_STRATEGY_NAME else "auto",
        "stop_loss": float(o.signal.stop_loss) if o.signal and o.signal.stop_loss is not None else None,
        "target": float(o.signal.target_price) if o.signal and o.signal.target_price is not None else None,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }
    if o.status == models.OrderStatus.FILLED:
        ltp = _ltp(o.symbol)
        d["ltp"] = ltp
        base = avg if avg is not None else entry
        if ltp is not None and base is not None:
            qty = o.filled_quantity or o.quantity
            d["unrealized_pnl"] = round(((ltp - base) if is_long else (base - ltp)) * qty, 2)
        else:
            d["unrealized_pnl"] = None
    return d


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/order")
def place_manual_order(
    body: ManualOrderIn,
    db: Session = Depends(get_db),
    username: str = Depends(get_current_user),
):
    """Place a manual market order with optional stop-loss and target."""
    _require_paper_mode()
    user = _get_user(db, username)

    settings = db.query(models.SystemSettings).first()
    if settings and settings.emergency_stop:
        raise HTTPException(423, "Emergency stop is active. Clear it before placing orders.")

    _require_market_open()
    symbol = _bare_symbol(body.symbol)
    ltp = _live_ltp_or_409(symbol)

    is_long = body.side == "BUY"
    _validate_bracket(is_long, ltp, body.stop_loss, body.target)

    # Capital check: this order plus everything already open or in flight
    open_orders = db.query(models.Order).filter(
        models.Order.user_id == user.id,
        models.Order.status.in_(PENDING_STATUSES + [models.OrderStatus.FILLED]),
    ).all()
    committed = sum(
        float(o.average_price or o.entry_price or 0) * (o.quantity or 0) for o in open_orders
    )
    notional = ltp * body.qty
    capital = float(user.capital_current or 0)
    if committed + notional > capital:
        raise HTTPException(
            422,
            f"Insufficient capital: order needs ₹{notional:,.2f}, "
            f"available ₹{max(capital - committed, 0):,.2f}.",
        )

    now = datetime.now(timezone.utc)
    signal_hash = f"manual_{uuid.uuid4().hex}"
    direction = models.Direction.LONG if is_long else models.Direction.SHORT

    signal = models.Signal(
        strategy_id=crud.PAPER_STRATEGY_ID,
        symbol=symbol,
        direction=direction,
        entry_price=Decimal(str(ltp)),
        stop_loss=Decimal(str(body.stop_loss)) if body.stop_loss else None,
        target_price=Decimal(str(body.target)) if body.target else None,
        signal_hash=signal_hash,
        timestamp=now,
    )
    db.add(signal)
    db.flush()

    order = models.Order(
        user_id=user.id,
        signal_id=signal.id,
        signal_hash=signal_hash,
        strategy_name=MANUAL_STRATEGY_NAME,
        symbol=symbol,
        direction=direction,
        quantity=body.qty,
        entry_price=Decimal(str(ltp)),
        status=models.OrderStatus.NEW,
        rejection_count=0,
        signal_timestamp=now,
    )
    db.add(order)
    db.flush()

    db.add(models.OutboxEvent(
        order_id=order.id,
        event_type="SEND_TO_BROKER",
        status=models.OutboxEventStatus.PENDING,
        payload={
            "symbol": symbol,
            "qty": body.qty,
            "direction": direction.value,
            "price": ltp,
            "order_type": "MARKET",
            "correlation_id": f"USR{user.id}_MAN{order.id}",
        },
    ))
    db.commit()
    db.refresh(order)

    return {"status": "ok", "order": _order_dict(order)}


@router.get("/positions")
def list_positions(db: Session = Depends(get_db), username: str = Depends(get_current_user)):
    """Open (FILLED) positions with live P&L, plus orders still waiting to fill."""
    user = _get_user(db, username)
    orders = (
        db.query(models.Order)
        .options(joinedload(models.Order.signal))
        .filter(
            models.Order.user_id == user.id,
            models.Order.status.in_(PENDING_STATUSES + [models.OrderStatus.FILLED]),
        )
        .order_by(models.Order.created_at.desc())
        .all()
    )
    settings = db.query(models.SystemSettings).first()
    return {
        "execution_mode": config.EXECUTION_MODE.lower(),
        "emergency_stop": bool(settings and settings.emergency_stop),
        "positions": [_order_dict(o) for o in orders if o.status == models.OrderStatus.FILLED],
        "pending": [_order_dict(o) for o in orders if o.status != models.OrderStatus.FILLED],
    }


@router.patch("/positions/{order_id}")
def update_bracket(
    order_id: int,
    body: BracketUpdate,
    db: Session = Depends(get_db),
    username: str = Depends(get_current_user),
):
    """Change the stop-loss / target of an open position. The exit monitor
    picks the new levels up on its next DB resync (within ~5 s)."""
    _require_paper_mode()
    user = _get_user(db, username)
    order = (
        db.query(models.Order)
        .options(joinedload(models.Order.signal))
        .filter(models.Order.id == order_id, models.Order.user_id == user.id)
        .first()
    )
    if not order:
        raise HTTPException(404, "Position not found")
    if order.status != models.OrderStatus.FILLED:
        raise HTTPException(409, f"Position is {order.status.value}, not open.")

    ref = _ltp(order.symbol) or float(order.average_price or order.entry_price)
    _validate_bracket(order.direction == models.Direction.LONG, ref, body.stop_loss, body.target)

    signal = order.signal
    if signal is None:
        signal = models.Signal(
            strategy_id=crud.PAPER_STRATEGY_ID,
            symbol=order.symbol,
            direction=order.direction,
            entry_price=order.average_price or order.entry_price,
            signal_hash=f"bracket_{uuid.uuid4().hex}",
            timestamp=datetime.now(timezone.utc),
        )
        db.add(signal)
        db.flush()
        order.signal_id = signal.id

    signal.stop_loss = Decimal(str(body.stop_loss)) if body.stop_loss else None
    signal.target_price = Decimal(str(body.target)) if body.target else None
    db.commit()
    db.refresh(order)
    return {"status": "ok", "position": _order_dict(order)}


@router.post("/positions/{order_id}/close")
def close_position(
    order_id: int,
    db: Session = Depends(get_db),
    username: str = Depends(get_current_user),
):
    """Square off an open position (manual or automated) at the current price."""
    _require_paper_mode()
    user = _get_user(db, username)
    order = db.query(models.Order).filter(
        models.Order.id == order_id, models.Order.user_id == user.id
    ).first()
    if not order:
        raise HTTPException(404, "Position not found")
    if order.status != models.OrderStatus.FILLED:
        raise HTTPException(409, f"Position is {order.status.value}, not open.")

    # No stale-price close: if the feed is down the exit monitor still squares
    # the position off at EOD.
    ltp = _live_ltp_or_409(order.symbol)

    from app.engines.execution_engine import ExecutionEngine
    from app.engines.paper_strategy_runner import peek_runner

    ExecutionEngine(db).close_paper_position(order.id, ltp, "MANUAL")

    db.expire_all()
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if order.status != models.OrderStatus.CLOSED:
        raise HTTPException(500, "Close failed; the position is still open. Check backend logs.")

    runner = peek_runner()
    if runner is not None:
        runner._active_positions.pop(order.id, None)

    return {
        "status": "ok",
        "order_id": order.id,
        "exit_price": float(order.exit_price),
        "pnl": float(order.pnl or 0),
    }
