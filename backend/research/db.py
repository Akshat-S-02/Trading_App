"""
research/db.py

Separate SQLite database for the research and backtesting pipeline.
Completely isolated from the live trading sandbox.db.

Database file: backend/research.db
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Place research.db next to sandbox.db, in the backend/ directory
_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "research.db")
_DB_URL = f"sqlite:///{os.path.abspath(_DB_PATH)}"

engine = create_engine(
    _DB_URL,
    connect_args={"check_same_thread": False},  # needed for SQLite + multi-threaded use
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI-style dependency (useful for research API routes if added later)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all research tables. Call once on startup or during job init."""
    # Import models so SQLAlchemy picks them up before create_all
    from research.data import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
