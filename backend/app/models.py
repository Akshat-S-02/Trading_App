from sqlalchemy import Column, Integer, String, Float, DateTime, JSON
from sqlalchemy.sql import func
from .db import Base

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    tokens = Column(Float, default=50000.0)  # ₹50,000 initial sandbox
    daily_limit = Column(Float, default=5000.0)
    monthly_limit = Column(Float, default=50000.0)
    daily_spent = Column(Float, default=0.0)
    monthly_spent = Column(Float, default=0.0)
    max_daily_loss = Column(Float, default=1000.0) # Safety: Max daily loss allowed
    last_reset_date = Column(DateTime(timezone=True), server_default=func.now())

class Holding(Base):
    __tablename__ = 'holdings'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    symbol = Column(String, index=True)
    qty = Column(Float, default=0.0)
    avg_price = Column(Float, default=0.0)

class Trade(Base):
    __tablename__ = 'trades'
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String, unique=True, index=True) # Safety: Idempotency Key
    user_id = Column(Integer, index=True)
    symbol = Column(String)
    qty = Column(Float)
    price = Column(Float)
    side = Column(String)  # BUY/SELL
    stop_loss = Column(Float, nullable=True)
    is_active = Column(Integer, default=1) # 1=Active, 0=Closed
    pnl = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AIAction(Base):
    __tablename__ = 'ai_actions'
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String, nullable=True) # Safety: Traceability
    symbol = Column(String)
    decision = Column(String)  # BUY/SELL/HOLD
    confidence = Column(Float, default=0.0)
    meta = Column(JSON)
    latency_ms = Column(Float, nullable=True) # Safety: Performance tracking
    created_at = Column(DateTime(timezone=True), server_default=func.now())
