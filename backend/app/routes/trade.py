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

    # Risk Management: Reset counters if needed
    import datetime
    now = datetime.datetime.now()
    if user.last_reset_date:
        last_reset = user.last_reset_date.replace(tzinfo=None) # naive comparison
        if last_reset.date() < now.date():
            user.daily_spent = 0.0
        if last_reset.month != now.month or last_reset.year != now.year:
            user.monthly_spent = 0.0
        # Update reset date only if we actually reset? Or always update on activity to "today"?
        # For simplicity, if we reset, we update. If not, we keep the date.
        # Better: just Check if today is different from last_reset_date.
        if last_reset.date() < now.date():
             user.last_reset_date = now # Update reset date to today

    # fetch current price (simple: call yfinance)
    import yfinance as yf
    try:
        t = yf.Ticker(trade.symbol)
        data = t.history(period='1d', interval='1m')
        if data.empty:
            raise HTTPException(status_code=400, detail="Price unavailable")
        price = float(data['Close'].iloc[-1])
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Price fetch error: {str(e)}")

    value = price * trade.qty

    if trade.side.upper() == 'BUY':
        # check limits
        if user.tokens < value:
            raise HTTPException(status_code=400, detail="Insufficient sandbox tokens")
        if user.daily_spent + value > user.daily_limit:
            raise HTTPException(status_code=400, detail=f"Daily limit exceeded ({user.daily_limit})")
        if user.monthly_spent + value > user.monthly_limit:
            raise HTTPException(status_code=400, detail=f"Monthly limit exceeded ({user.monthly_limit})")

        # execute logic
        user.tokens -= value
        user.daily_spent += value
        user.monthly_spent += value
        
        db.add(user)
        new_trade = models.Trade(
            user_id=user.id, 
            symbol=trade.symbol, 
            qty=trade.qty, 
            price=price, 
            side='BUY',
            stop_loss=trade.stop_loss,
            is_active=1
        )
        db.add(new_trade)
        
        # In a real app, update Holdings table here too
        # checking if holding exists
        holding = db.query(models.Holding).filter(models.Holding.user_id == user.id, models.Holding.symbol == trade.symbol).first()
        if holding:
            total_qty = holding.qty + trade.qty
            # weighted average price
            new_avg = ((holding.qty * holding.avg_price) + (trade.qty * price)) / total_qty
            holding.qty = total_qty
            holding.avg_price = new_avg
        else:
            holding = models.Holding(user_id=user.id, symbol=trade.symbol, qty=trade.qty, avg_price=price)
        db.add(holding)

        db.commit()
        return {"status":"ok","price":price,"value":value, "message": "Buy executed in sandbox"}

    else:
        # SELL Logic
        # fetch holding
        holding = db.query(models.Holding).filter(models.Holding.user_id == user.id, models.Holding.symbol == trade.symbol).first()
        if not holding or holding.qty < trade.qty:
             raise HTTPException(status_code=400, detail="Insufficient holdings")

        holding.qty -= trade.qty
        if holding.qty == 0:
            db.delete(holding)
        else:
            db.add(holding)
            
        user.tokens += value
        # We don't reduce 'spent' on sell, usually limits are on "exposure/buy"
        
        db.add(user)
        new_trade = models.Trade(
            user_id=user.id, 
            symbol=trade.symbol, 
            qty=trade.qty, 
            price=price, 
            side='SELL',
            is_active=0 # Sell closes? Not necessarily, but for simplicity assuming linear fifo or just closing
        )
        # If selling, we might want to mark associated buy trades as closed?
        # For this simple sandbox, we just log the Sell trade.
        db.add(new_trade)
        db.commit()
        return {"status":"ok","price":price,"value":value, "message": "Sell executed in sandbox"}

@router.get("/api/portfolio")
def get_portfolio(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    user = crud.get_user(db, 'admin')
    if not user:
        return []
    holdings = db.query(models.Holding).filter(models.Holding.user_id == user.id).all()
    # Fetch current prices for calculating unrealized PnL (optional, but good for UI)
    import yfinance as yf
    res = []
    for h in holdings:
        # For speed, maybe don't fetch live price here, or let frontend do it via WebSocket/Timer
        # We will just return holding data
        res.append({
            "symbol": h.symbol,
            "qty": h.qty,
            "avg_price": h.avg_price,
            "value": 0.0 # frontend can calculate
        })
    return res

@router.get("/api/trades")
def get_trades(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    user = crud.get_user(db, 'admin')
    if not user:
        return []
    # Return last 50 trades
    trades = db.query(models.Trade).filter(models.Trade.user_id == user.id).order_by(models.Trade.created_at.desc()).limit(50).all()
    return trades
