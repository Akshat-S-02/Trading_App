from pydantic import BaseModel
from typing import Optional

class TokenAdd(BaseModel):
    amount: float

class TradeIn(BaseModel):
    symbol: str
    qty: float
    side: str  # BUY or SELL
    stop_loss: Optional[float] = None

class LimitUpdate(BaseModel):
    daily_limit: float
    monthly_limit: float
