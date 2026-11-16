"""
Risk-limit units, halted-automation recovery, and the paper-only guards.

    cd backend && .venv/bin/python -m pytest tests/test_safety_fixes.py -q
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.config import Settings, config
from app.db import Base
from app.routes import admin
from app.schemas import LimitUpdate
from app.services.token_renewal import _rewrite_env_key
from app.workers import outbox_worker as ow


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _admin(db, **metrics):
    user = models.User(username="admin", capital_initial=50000, capital_current=50000,
                       max_daily_dd=2, max_monthly_dd=6,
                       last_reset_date=datetime.now(timezone.utc).date())
    db.add(user); db.flush()
    db.add(models.PortfolioMetrics(user_id=user.id, peak_equity=50000, **metrics))
    db.commit(); db.refresh(user)
    return user


# ── 1. Risk limits are percents ──────────────────────────────────────────────

@pytest.mark.parametrize("bad", [5000, 0, -1, float("inf"), float("nan")])
def test_limit_outside_0_to_100_percent_is_rejected(bad):
    with pytest.raises(ValidationError):
        LimitUpdate(max_daily_dd=bad, max_monthly_dd=6)


def test_limits_report_todays_loss_as_percent_of_capital(db):
    _admin(db, realized_pnl=-500)
    out = admin.get_limits(db=db, _="admin")
    assert out["daily_spent"] == 1.0      # 500 of 50,000
    assert out["daily_limit"] == 2


# ── 2. A halted strategy can be resumed ──────────────────────────────────────

def test_enable_automation_turns_it_back_on_and_clears_streaks(db):
    user = _admin(db, consecutive_dd_hits=3, consecutive_loss_days=5)
    user.automation_enabled = False; db.commit()

    admin.enable_automation(db=db, _="admin")
    db.refresh(user)
    assert user.automation_enabled is True
    assert user.portfolio_metrics.consecutive_dd_hits == 0
    assert user.portfolio_metrics.consecutive_loss_days == 0


# ── 3. Paper-only guards ─────────────────────────────────────────────────────

def test_token_with_newline_is_rejected_before_touching_env():
    with pytest.raises(ValueError):
        _rewrite_env_key("ACCESS_TOKEN", "abc\nEXECUTION_MODE=live")


def _settings(**kw):
    base = dict(API_KEY="k", API_SECRET="s", CLIENT_ID="1", ACCESS_TOKEN="t",
                DATABASE_URL="sqlite://", APP_PASSWORD="p", JWT_SECRET="j" * 32)
    return Settings(_env_file=None, **{**base, **kw})


def test_execution_mode_is_normalised_or_refused():
    assert _settings(EXECUTION_MODE=" Paper ").EXECUTION_MODE == "paper"
    with pytest.raises(ValidationError):
        _settings(EXECUTION_MODE="dry-run")
    with pytest.raises(ValidationError):
        _settings(EXECUTION_MODE="live")                        # no static-IP confirmation
    assert _settings(EXECUTION_MODE="live", DHAN_STATIC_IP_CONFIRMED=True).EXECUTION_MODE == "live"


@pytest.mark.parametrize("mode,static_ip", [("dry-run", True), ("live", False)])
def test_worker_never_sends_unless_confirmed_live(db, monkeypatch, mode, static_ip):
    monkeypatch.setattr(config, "EXECUTION_MODE", mode)          # changed after load
    monkeypatch.setattr(config, "DHAN_STATIC_IP_CONFIRMED", static_ip)
    sent = []
    monkeypatch.setattr(ow.dhan_service, "place_order", lambda **kw: sent.append(kw) or {"status": "success"})

    user = models.User(username="u", capital_initial=50000, capital_current=50000)
    db.add(user); db.flush()
    order = models.Order(user_id=user.id, symbol="TCS", direction=models.Direction.LONG, quantity=1,
                         entry_price=100, status=models.OrderStatus.NEW)
    db.add(order); db.flush()
    ev = models.OutboxEvent(order_id=order.id, status=models.OutboxEventStatus.PENDING,
                            next_attempt_at=datetime.now(timezone.utc) - timedelta(seconds=1),
                            payload={"symbol": "TCS", "qty": 1, "direction": "LONG", "price": 100.0,
                                     "order_type": "MARKET", "correlation_id": "USR1_MAN1"})
    db.add(ev); db.commit()

    ow.OutboxWorker(db).process_pending_events()
    db.refresh(ev); db.refresh(order)
    assert sent == []
    assert ev.status == models.OutboxEventStatus.FAILED
    assert order.status == models.OrderStatus.FAILED_FATAL


# ── Candles: the input to every strategy signal ──────────────────────────────

def test_ticks_become_one_5min_candle_on_ist_boundaries():
    from zoneinfo import ZoneInfo
    from app.engines.tick_aggregator import TickAggregator
    ist = ZoneInfo("Asia/Kolkata")
    at = lambda h, m, s: datetime(2026, 11, 16, h, m, s, tzinfo=ist)
    out = []
    agg = TickAggregator(on_candle=lambda sym, c: out.append((sym, c)))

    agg.on_tick("TCS", 90.0, 1, at(9, 14, 59))     # before the open: ignored
    agg.on_tick("TCS", 100.0, 1, at(9, 15, 0))
    agg.on_tick("TCS", 105.0, 1, at(9, 17, 0))
    agg.on_tick("TCS", 98.0, 1, at(9, 19, 59))
    assert out == []                                # bucket still open
    agg.on_tick("TCS", 101.0, 1, at(9, 20, 0))     # first tick of the next bucket closes it

    assert len(out) == 1
    sym, c = out[0]
    assert sym == "TCS"
    assert c["timestamp"] == datetime(2026, 11, 16, 3, 45, tzinfo=timezone.utc)   # 09:15 IST
    assert (c["open"], c["high"], c["low"], c["close"], c["volume"]) == (100.0, 105.0, 98.0, 98.0, 3)


# ── Risk gate: a breached daily loss halts automation ────────────────────────

def _signal(ts):
    from decimal import Decimal
    from app.engines.strategy_engine import Signal
    return Signal(strategy_id=1, symbol="TCS", direction="LONG", entry_price=Decimal("100"),
                  stop_loss=Decimal("95"), timestamp=ts, strategy_name="orb_v4")


@pytest.mark.parametrize("realized,approved,still_enabled", [
    (0, True, True),          # fresh day: trade allowed
    (-1000, False, True),     # at the 2% limit: blocked, not halted (next trade would breach)
    (-1200, False, False),    # past the limit: blocked and automation switched off
])
def test_validate_risk_daily_loss(db, realized, approved, still_enabled):
    from app.engines.risk_engine import RiskGate
    ts = datetime(2026, 11, 16, 4, 30, tzinfo=timezone.utc)      # Monday 10:00 IST
    user = _admin(db, realized_pnl=realized)
    user.last_reset_date = ts.date(); db.commit()

    ok = RiskGate.validate_risk(db, user, None, _signal(ts),
                                portfolio_snapshot={"unrealized_pnl": 0, "missing_cmp": False}, current_time=ts)
    db.refresh(user)
    assert ok is approved
    assert user.automation_enabled is still_enabled


# ── One capital rule for manual and automated orders ─────────────────────────

def test_buying_power_is_capital_times_leverage_minus_open_orders(db):
    from decimal import Decimal
    from app.engines.risk_engine import INTRADAY_LEVERAGE, buying_power_left
    user = _admin(db)
    assert buying_power_left(db, user) == Decimal("50000") * INTRADAY_LEVERAGE
    db.add(models.Order(user_id=user.id, symbol="TCS", direction=models.Direction.LONG, quantity=100,
                        entry_price=2000, average_price=2000, filled_quantity=100,
                        status=models.OrderStatus.FILLED))
    db.add(models.Order(user_id=user.id, symbol="INFY", direction=models.Direction.LONG, quantity=10,
                        entry_price=1000, status=models.OrderStatus.CLOSED))   # closed: not counted
    db.commit()
    assert buying_power_left(db, user) == Decimal("250000") - Decimal("200000")
