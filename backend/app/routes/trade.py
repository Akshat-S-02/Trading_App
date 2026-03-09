from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import SessionLocal
from .. import crud, models
from ..schemas import TradeIn
from ..auth import get_current_user

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/api/trade/place")
def place_trade(trade: TradeIn, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    user = crud.get_user(db, 'admin')
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
        
    side = models.Direction.LONG if trade.side.upper() == 'BUY' else models.Direction.SHORT
    
    new_order = models.Order(
        user_id=user.id,
        symbol=trade.symbol,
        quantity=int(trade.qty),
        entry_price=100.0,  # Sandbox placeholder — not wired to ExecutionEngine yet
        direction=side,
        status=models.OrderStatus.NEW,  # Fix: CLOSED does not exist in OrderStatus enum
        signal_hash=None  # Manual/sandbox order — no strategy signal
    )
    db.add(new_order)
    db.commit()
    return {"status":"ok", "message": "Trade registered in new Order schema"}

@router.get("/api/portfolio")
def get_portfolio(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    # Returns empty for now, to be replaced by PortfolioMetrics logic
    return []

@router.get("/api/trades")
def get_trades(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    user = crud.get_user(db, 'admin')
    if not user:
        return []
        
    orders = db.query(models.Order).filter(models.Order.user_id == user.id).order_by(models.Order.created_at.desc()).limit(50).all()
    # Format to match frontend expectations temporarily
    return [{
        "symbol": ord.symbol,
        "qty": ord.quantity,
        "side": "BUY" if ord.direction == models.Direction.LONG else "SELL",
        "price": ord.entry_price,
        "pnl": ord.pnl,
        "created_at": ord.created_at
    } for ord in orders]
