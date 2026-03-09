from pydantic import BaseModel
from typing import Optional

class LimitUpdate(BaseModel):
    max_daily_dd: float
    max_monthly_dd: float

class TradeIn(BaseModel):
    symbol: str
    qty: float
    side: str  # BUY or SELL
    stop_loss: Optional[float] = None
