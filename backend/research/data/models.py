"""
research/data/models.py

SQLAlchemy models for the research database (research.db).
These are completely separate from app/models.py (live trading).

Tables:
  - historical_candles   : OHLCV candle store
  - research_instruments : NIFTY 50 instrument registry
  - ingestion_jobs       : tracks every data fetch attempt
  - backtest_runs        : one row per backtest run with aggregate metrics
  - backtest_trades      : individual simulated trades per run
"""

import enum
from sqlalchemy import (
    Column, Integer, String, Numeric, DateTime, Boolean,
    UniqueConstraint, JSON, Text, ForeignKey
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from research.db import Base


# ---------------------------------------------------------------------------
# HistoricalCandle
# ---------------------------------------------------------------------------

class HistoricalCandle(Base):
    """
    One row = one OHLCV candle for a specific instrument + timeframe + timestamp.

    UNIQUE on (security_id, timeframe, timestamp) — prevents duplicate ingestion.
    symbol is stored as a human-readable display field only.
    exchange_segment and instrument are stored for future extensibility.
    """
    __tablename__ = "historical_candles"
    __table_args__ = (
        UniqueConstraint("security_id", "timeframe", "timestamp", name="uq_candle"),
    )

    id               = Column(Integer, primary_key=True, index=True)

    # Instrument identity
    security_id      = Column(String, nullable=False, index=True)   # Dhan's canonical ID
    symbol           = Column(String, nullable=False, index=True)   # Display only, e.g. "RELIANCE"
    exchange_segment = Column(String, nullable=False, default="NSE_EQ")  # e.g. "NSE_EQ"
    instrument       = Column(String, nullable=False, default="EQUITY")  # e.g. "EQUITY"

    # Candle identity
    timeframe        = Column(String, nullable=False, index=True)   # "1m","5m","15m","25m","60m","1d"
    timestamp        = Column(DateTime(timezone=True), nullable=False, index=True)  # stored as UTC

    # OHLCV
    open             = Column(Numeric(15, 4), nullable=False)
    high             = Column(Numeric(15, 4), nullable=False)
    low              = Column(Numeric(15, 4), nullable=False)
    close            = Column(Numeric(15, 4), nullable=False)
    volume           = Column(Integer,        nullable=False)
    open_interest    = Column(Integer,        nullable=True, default=0)

    created_at       = Column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# ResearchInstrument
# ---------------------------------------------------------------------------

class ResearchInstrument(Base):
    """
    Registry of instruments available for research (initially NIFTY 50).
    security_id is the canonical Dhan identifier used in all API calls and candle lookups.
    """
    __tablename__ = "research_instruments"

    id               = Column(Integer, primary_key=True, index=True)
    security_id      = Column(String, unique=True, nullable=False, index=True)
    symbol           = Column(String, unique=True, nullable=False, index=True)
    name             = Column(String, nullable=True)
    exchange_segment = Column(String, nullable=False, default="NSE_EQ")
    instrument       = Column(String, nullable=False, default="EQUITY")
    is_active        = Column(Boolean, default=True)
    index_membership = Column(String, nullable=True)  # e.g. "NIFTY50", "BANKNIFTY"

    created_at       = Column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# IngestionJob
# ---------------------------------------------------------------------------

class IngestionJobStatus(str, enum.Enum):
    RUNNING  = "RUNNING"
    DONE     = "DONE"
    FAILED   = "FAILED"
    SKIPPED  = "SKIPPED"  # already up to date


class IngestionJob(Base):
    """
    One row per data fetch attempt (one symbol + one 85-day chunk + one timeframe).
    Used to make the backfill job resumable: skips chunks already marked DONE.
    """
    __tablename__ = "ingestion_jobs"

    id            = Column(Integer, primary_key=True, index=True)
    security_id   = Column(String, nullable=False, index=True)
    symbol        = Column(String, nullable=False)
    timeframe     = Column(String, nullable=False)
    from_date     = Column(String, nullable=False)   # ISO date string "YYYY-MM-DD"
    to_date       = Column(String, nullable=False)
    status        = Column(String, default=IngestionJobStatus.RUNNING, index=True)
    rows_inserted = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    started_at    = Column(DateTime(timezone=True), server_default=func.now())
    finished_at   = Column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# BacktestRun
# ---------------------------------------------------------------------------

class BacktestRun(Base):
    """
    One row per backtest run. Stores aggregate metrics + a full JSON config snapshot
    so every result is reproducible.
    """
    __tablename__ = "backtest_runs"

    id               = Column(Integer, primary_key=True, index=True)

    # Strategy identification
    strategy_name    = Column(String, nullable=False, index=True)   # e.g. "nifty_breakout"
    strategy_version = Column(String, nullable=False, default="v1") # e.g. "v1"

    # Run scope
    timeframe        = Column(String, nullable=False)
    from_date        = Column(String, nullable=False)   # ISO "YYYY-MM-DD"
    to_date          = Column(String, nullable=False)
    universe         = Column(JSON,   nullable=False)   # list of symbols

    # Full reproducibility snapshot — includes strategy params, fee/slippage/risk config
    config_snapshot  = Column(JSON, nullable=False, default={})

    # Aggregate metrics
    total_trades        = Column(Integer,        default=0)
    winning_trades      = Column(Integer,        default=0)
    losing_trades       = Column(Integer,        default=0)
    win_rate            = Column(Numeric(8, 4),  nullable=True)
    gross_profit        = Column(Numeric(15, 4), default=0)
    gross_loss          = Column(Numeric(15, 4), default=0)
    net_pnl             = Column(Numeric(15, 4), default=0)
    total_charges       = Column(Numeric(15, 4), default=0)
    profit_factor       = Column(Numeric(8, 4),  nullable=True)
    max_drawdown        = Column(Numeric(8, 4),  nullable=True)  # as % of peak equity
    max_drawdown_abs    = Column(Numeric(15, 4), nullable=True)  # in Rs
    cagr                = Column(Numeric(8, 4),  nullable=True)
    expectancy          = Column(Numeric(15, 4), nullable=True)  # avg Rs per trade
    sharpe              = Column(Numeric(8, 4),  nullable=True)
    max_consecutive_losses = Column(Integer,     nullable=True)

    created_at       = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    trades = relationship("BacktestTrade", back_populates="run")


# ---------------------------------------------------------------------------
# BacktestTrade
# ---------------------------------------------------------------------------

class BacktestTrade(Base):
    """
    One row per simulated trade from a backtest run.
    entry_reason and exit_reason make it easy to debug clusters of losses.
    """
    __tablename__ = "backtest_trades"

    id            = Column(Integer, primary_key=True, index=True)
    run_id        = Column(Integer, ForeignKey("backtest_runs.id"), nullable=False, index=True)

    symbol        = Column(String,              nullable=False, index=True)
    security_id   = Column(String,              nullable=False)
    direction     = Column(String,              nullable=False, default="LONG")  # "LONG" / "SHORT"

    entry_time    = Column(DateTime(timezone=True), nullable=False)
    exit_time     = Column(DateTime(timezone=True), nullable=True)
    entry_price   = Column(Numeric(15, 4),      nullable=False)
    exit_price    = Column(Numeric(15, 4),      nullable=True)
    quantity      = Column(Integer,             nullable=False)

    # P&L
    gross_pnl     = Column(Numeric(15, 4),      default=0)
    charges       = Column(Numeric(15, 4),      default=0)   # total brokerage + taxes
    net_pnl       = Column(Numeric(15, 4),      default=0)

    # Slippage tracking
    slippage_entry = Column(Numeric(15, 4),     default=0)
    slippage_exit  = Column(Numeric(15, 4),     default=0)

    # Audit trail — crucial for debugging strategy logic
    entry_reason  = Column(String, nullable=True)  # e.g. "breakout_entry"
    exit_reason   = Column(String, nullable=True)  # "stop_loss" | "target_hit" | "trailing_stop" | "eod_squareoff"

    # Risk metadata at time of trade
    stop_loss      = Column(Numeric(15, 4), nullable=True)
    target         = Column(Numeric(15, 4), nullable=True)
    opening_range_high = Column(Numeric(15, 4), nullable=True)
    opening_range_low  = Column(Numeric(15, 4), nullable=True)

    created_at    = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    run = relationship("BacktestRun", back_populates="trades")
