"""
Alerts -> notifications table -> /api/notifications, and the SHORT-signal block.
In-memory SQLite; Telegram is not called (no token in tests).

    cd backend && .venv/bin/python -m pytest tests/test_notifications.py -q
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.db as app_db
from app import models
from app.core import alerts
from app.db import Base, get_db
from app.routes.notifications import router


@pytest.fixture
def Session(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine)
    monkeypatch.setattr(app_db, "SessionLocal", S)          # alerts._store imports it lazily
    monkeypatch.setattr(alerts, "TELEGRAM_BOT_TOKEN", None)
    return S


def test_alert_is_stored_and_listed_then_marked_read(Session):
    alerts.sync_dispatch_alert("INFO", "Paper Exit: TCS", "closed via SL")
    alerts.sync_dispatch_alert("CRITICAL", "STALE_FEED", "no data", metadata={"secs": 60})

    api = FastAPI(); api.include_router(router)
    def db():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    api.dependency_overrides[get_db] = db
    c = TestClient(api)

    body = c.get("/api/notifications").json()
    assert body["unread"] == 2
    assert [n["title"] for n in body["items"]] == ["STALE_FEED", "Paper Exit: TCS"]   # newest first
    assert '"secs": 60' in body["items"][0]["message"]

    assert c.post("/api/notifications/read-all").status_code == 200
    assert c.get("/api/notifications").json()["unread"] == 0


def test_store_failure_never_raises(monkeypatch):
    def broken():
        raise RuntimeError("db down")
    monkeypatch.setattr(app_db, "SessionLocal", broken)
    monkeypatch.setattr(alerts, "TELEGRAM_BOT_TOKEN", None)
    asyncio.run(alerts.async_dispatch_alert("INFO", "x", "y"))   # must not raise


def test_short_signals_are_dropped_longs_kept():
    from app.engines.decision_engine import DecisionEngine
    from app.engines.strategy_engine import Signal
    ts = datetime.now(timezone.utc)
    sig = lambda d, name: Signal(strategy_id=1, symbol="TCS", direction=d, entry_price=Decimal("100"),
                                 stop_loss=Decimal("105" if d == "SHORT" else "95"), timestamp=ts, strategy_name=name)
    adapters = {"orb_v4": None, "ema_momentum": None, "vwap_reversion": sig("SHORT", "vwap_reversion"),
                "supertrend": sig("LONG", "supertrend")}
    de = DecisionEngine.__new__(DecisionEngine)
    for attr, name in [("_orb_adapter", "orb_v4"), ("_ema_adapter", "ema_momentum"),
                       ("_vwap_adapter", "vwap_reversion"), ("_supertrend_adapter", "supertrend")]:
        setattr(de, attr, NS(on_candle=lambda s, c, allow_signal=True, _r=adapters[name]: _r))
    de._bar_history, de._last_regime, de._strategy_weights = {}, {}, {}
    de._passes_ev_filter = lambda *a: True
    import enum
    class R(enum.Enum):
        T = "T"
    de._regime_classifier = NS(classify=lambda h: {"regime": R.T, "trend": "UP"},
                               STRATEGY_MATRIX={(R.T, "UP"): ["vwap_reversion", "supertrend"]})
    winner = de.evaluate("TCS", {"timestamp": ts, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1})
    assert winner is not None and winner.direction == "LONG" and winner.strategy_name == "supertrend"
