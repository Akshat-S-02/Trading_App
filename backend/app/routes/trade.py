from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import SessionLocal
from .. import crud, models
from ..schemas import TradeIn
from ..auth import get_current_user

router = APIRouter(prefix="/sandbox")

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
    return {"status":"ok", "message": "Manual trade registered in sandbox Order schema"}

# DEPRECATED: portfolio/trades moved to canonical /api/ in admin.py
