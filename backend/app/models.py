import enum
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Time, Date, Boolean, ForeignKey, Enum, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime, time, timezone
from .db import Base

class RiskCategory(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

    @property
    def max_risk_pct(self) -> float:
        if self == RiskCategory.LOW:
            return 0.75
        elif self == RiskCategory.MEDIUM:
            return 1.25
        elif self == RiskCategory.HIGH:
            return 2.0
        return 0.75 # Default fallback

class UserStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    BANNED = "BANNED"

class StrategyType(str, enum.Enum):
    INTRADAY = "INTRADAY"
    SWING = "SWING"
    OPTIONS = "OPTIONS"

class Direction(str, enum.Enum):
    LONG = "LONG"
    SHORT = "SHORT"

class OrderStatus(str, enum.Enum):
    NEW = "NEW"                           # Created in DB
    ENQUEUED = "ENQUEUED"                 # Outbox event created
    SENDING = "SENDING"                   # OutboxWorker picked it up
    SUBMITTED = "SUBMITTED"               # Fallback legacy match
    BROKER_ACK = "BROKER_ACK"             # API returned success
    CONFIRMED = "CONFIRMED"               # Exchange accepted
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CLOSED = "CLOSED"                     # Round-trip complete (Exit processed)
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"                 # Broker/Exchange rejected
    FAILED_RETRYABLE = "FAILED_RETRYABLE" # Outbox transient network failure
    FAILED_FATAL = "FAILED_FATAL"         # Outbox catastrophic failure (e.g. 401 token dead)

class OutboxEventStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, unique=True, index=True) # 1:1 mapping with order creation
    event_type = Column(String, default="SEND_TO_BROKER")
    payload = Column(JSON, default={})
    
    # State control
    status = Column(Enum(OutboxEventStatus), default=OutboxEventStatus.PENDING, index=True)
    retry_count = Column(Integer, default=0)
    
    # Scheduling & Locking
    next_attempt_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class SystemSettings(Base):
    __tablename__ = "system_settings"
    id = Column(Integer, primary_key=True, index=True)
    emergency_stop = Column(Boolean, default=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    
    # Capital
    capital_initial = Column(Numeric(15, 4), default=50000.0)
    capital_current = Column(Numeric(15, 4), default=50000.0)
    
    # Risk Profile
    risk_category = Column(Enum(RiskCategory), default=RiskCategory.LOW)
    automation_enabled = Column(Boolean, default=True)
    max_daily_dd = Column(Numeric(15, 4), default=2.0)    # 2%
    max_monthly_dd = Column(Numeric(15, 4), default=6.0)  # 6%
    
    # Intraday Auto-Reset & Circuit Breakers
    session_start_time = Column(Time, default=time(9, 15))  # Default NSE Open
    session_end_time = Column(Time, default=time(15, 30))   # Default NSE Close
    last_reset_date = Column(Date, nullable=True)
    max_orders_per_minute = Column(Integer, default=5)
    max_open_positions = Column(Integer, default=1)
    
    # Trackers
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(Enum(UserStatus), default=UserStatus.ACTIVE)
    
    # Relationships
    allocations = relationship("UserStrategyAllocation", back_populates="user")
    orders = relationship("Order", back_populates="user")
    portfolio_metrics = relationship("PortfolioMetrics", back_populates="user", uselist=False)


class Strategy(Base):
    __tablename__ = 'strategies'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    strategy_type = Column(Enum(StrategyType), default=StrategyType.INTRADAY)
    risk_profile = Column(Enum(RiskCategory), default=RiskCategory.LOW)
    active = Column(Boolean, default=True)

    # Relationships
    allocations = relationship("UserStrategyAllocation", back_populates="strategy")
    signals = relationship("Signal", back_populates="strategy")


class UserStrategyAllocation(Base):
    __tablename__ = 'user_strategy_allocations'

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id"), primary_key=True)
    
    # Engine logic
    allocation_percentage = Column(Numeric(15, 4), default=100.0) # E.g. allocating 50% of capital to this strategy
    risk_per_trade = Column(Numeric(15, 4), default=1.0)          # E.g. 1% risk per trade
    
    # Relationships
    user = relationship("User", back_populates="allocations")
    strategy = relationship("Strategy", back_populates="allocations")


class Signal(Base):
    __tablename__ = 'signals'

    id = Column(Integer, primary_key=True, index=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id"))
    
    symbol = Column(String, index=True)
    direction = Column(Enum(Direction))
    entry_price = Column(Numeric(15, 4))
    stop_loss = Column(Numeric(15, 4), nullable=True)
    signal_hash = Column(String, unique=True, index=True) # NEW: Idempotency Key
    
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    strategy = relationship("Strategy", back_populates="signals")
    orders = relationship("Order", back_populates="signal")


class Order(Base):
    __tablename__ = 'orders'
    __table_args__ = (UniqueConstraint('user_id', 'signal_hash', name='uq_user_signal_hash'),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    signal_id = Column(Integer, ForeignKey("signals.id"), nullable=True, index=True) # Nullable if manual
    signal_hash = Column(String, index=True, nullable=True) # NEW: DB Level Idempotency
    
    # Order metadata
    symbol = Column(String, index=True)
    direction = Column(Enum(Direction))
    quantity = Column(Integer)
    
    # Pre-API Fields
    entry_price = Column(Numeric(15, 4))
    
    # Partial Fill & Live API Math
    filled_quantity = Column(Integer, default=0)
    average_price = Column(Numeric(15, 4), nullable=True)
    exit_price = Column(Numeric(15, 4), nullable=True)
    
    pnl = Column(Numeric(15, 4), default=0.0)
    status = Column(Enum(OrderStatus), default=OrderStatus.NEW)
    rejection_count = Column(Integer, default=0)
    broker_order_id = Column(String, index=True, nullable=True) # DYNAMIC LIVE FILL TRACKING
    
    signal_timestamp = Column(DateTime(timezone=True), nullable=True) # True market time of the generated signal, disjoint from processing latency
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Exit Engine tracking
    exit_reason = Column(String, nullable=True) # e.g. "SL", "TARGET", "EOD"
    close_requested_at = Column(DateTime(timezone=True), nullable=True)
    
    # Latency Telemetry (Phase 3)
    signal_creation_time = Column(DateTime(timezone=True), nullable=True)
    order_submission_time = Column(DateTime(timezone=True), nullable=True)
    broker_ack_time = Column(DateTime(timezone=True), nullable=True)
    final_fill_time = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="orders")
    signal = relationship("Signal", back_populates="orders")
    fills = relationship("TradeFill", back_populates="order")


class TradeFill(Base):
    __tablename__ = 'trade_fills'
    
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), index=True)
    fill_id = Column(String, unique=True, index=True) # Dhan's unique fill ID to prevent double-counting
    
    quantity = Column(Integer)
    price = Column(Numeric(15, 4))
    
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    # Paper trading validation metrics (Phase 4)
    # Stores: signal_price, fill_price, slippage_ticks, latency_ms,
    #         realized_r, mae_r, mfe_r, signal_to_bar_close_delay_ms,
    #         paper_fill_vs_next_bar_open, execution_mode
    paper_meta = Column(JSON, nullable=True)
    
    # Relationships
    order = relationship("Order", back_populates="fills")


class PortfolioMetrics(Base):
    __tablename__ = 'portfolio_metrics'

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    
    realized_pnl = Column(Numeric(15, 4), default=0.0)
    unrealized_pnl = Column(Numeric(15, 4), default=0.0)
    current_drawdown = Column(Numeric(15, 4), default=0.0)
    peak_equity = Column(Numeric(15, 4), default=50000.0)
    
    # Margin Cache Guardrail
    available_margin = Column(Numeric(15, 4), default=0.0)
    last_margin_sync = Column(DateTime(timezone=True), nullable=True)
    
    # Anomaly Clustering (Phase 3.995)
    consecutive_loss_days = Column(Integer, default=0)
    consecutive_dd_hits = Column(Integer, default=0)
    
    win_rate = Column(Numeric(15, 4), default=0.0)
    sharpe_estimate = Column(Numeric(15, 4), default=0.0)

    user = relationship("User", back_populates="portfolio_metrics")
