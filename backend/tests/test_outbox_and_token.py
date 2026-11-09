"""
Outbox worker and Dhan token tests (in-memory SQLite, Dhan calls mocked).

    cd backend && .venv/bin/python -m pytest tests/test_outbox_and_token.py -q
"""
import base64
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.db import Base
from app.workers import outbox_worker as ow
from app.services import token_renewal as tr

S, E = models.OrderStatus, models.OutboxEventStatus


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _event(db, order_status, event_status=E.PENDING, retry=0, locked_minutes_ago=None):
    user = models.User(username=f"u{time.time_ns()}", capital_initial=50000, capital_current=50000)
    db.add(user); db.flush()
    order = models.Order(user_id=user.id, symbol="TCS", direction=models.Direction.LONG, quantity=1,
                         entry_price=100, status=order_status)
    db.add(order); db.flush()
    ev = models.OutboxEvent(order_id=order.id, status=event_status, retry_count=retry,
                            next_attempt_at=datetime.now(timezone.utc) - timedelta(seconds=1),
                            locked_at=(datetime.now(timezone.utc) - timedelta(minutes=locked_minutes_ago))
                            if locked_minutes_ago else None,
                            payload={"symbol": "TCS", "qty": 1, "direction": "LONG", "price": 100.0,
                                     "order_type": "MARKET", "correlation_id": "USR1_MAN1"})
    db.add(ev); db.commit()
    return order, ev


def test_stuck_unsent_event_is_requeued(db):
    order, ev = _event(db, S.NEW, E.PROCESSING, locked_minutes_ago=5)
    ow.OutboxWorker(db).requeue_interrupted()
    db.refresh(ev)
    assert ev.status == E.PENDING and ev.retry_count == 1


def test_stuck_event_whose_order_already_filled_is_closed_not_resent(db):
    order, ev = _event(db, S.FILLED, E.PROCESSING, locked_minutes_ago=5)
    ow.OutboxWorker(db).requeue_interrupted()
    db.refresh(ev)
    assert ev.status == E.COMPLETED


def test_event_in_flight_right_now_is_left_alone(db):
    order, ev = _event(db, S.NEW, E.PROCESSING, locked_minutes_ago=None)
    ev.locked_at = datetime.now(timezone.utc); db.commit()
    ow.OutboxWorker(db).requeue_interrupted()
    db.refresh(ev)
    assert ev.status == E.PROCESSING


def test_live_timeout_is_not_a_rejection_and_retry_looks_up_first(db, monkeypatch):
    monkeypatch.setattr(ow.config, "EXECUTION_MODE", "live")
    sent, looked_up = [], []
    monkeypatch.setattr(ow.dhan_service, "place_order",
                        lambda **kw: sent.append(kw) or {"status": "unknown", "error": "timeout"})
    monkeypatch.setattr(ow.dhan_service, "find_order_by_correlation",
                        lambda cid: looked_up.append(cid) or {"orderId": "DH123", "orderStatus": "PENDING"})
    order, ev = _event(db, S.NEW)
    w = ow.OutboxWorker(db)

    w.process_pending_events()              # 1st try times out
    db.refresh(ev); db.refresh(order)
    assert len(sent) == 1 and ev.status == E.PENDING and order.status == S.NEW and order.rejection_count == 0

    ev.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1); db.commit()
    w.process_pending_events()              # retry: Dhan already has it -> adopt, don't resend
    db.refresh(ev); db.refresh(order)
    assert looked_up == ["USR1_MAN1"] and len(sent) == 1
    assert ev.status == E.COMPLETED and order.status == S.SUBMITTED and order.broker_order_id == "DH123"


def test_live_retry_with_failed_lookup_does_not_send(db, monkeypatch):
    monkeypatch.setattr(ow.config, "EXECUTION_MODE", "live")
    sent = []
    monkeypatch.setattr(ow.dhan_service, "place_order", lambda **kw: sent.append(kw) or {"status": "success"})
    def boom(cid): raise ConnectionError("dhan down")
    monkeypatch.setattr(ow.dhan_service, "find_order_by_correlation", boom)
    order, ev = _event(db, S.NEW, retry=1)
    ow.OutboxWorker(db).process_pending_events()
    db.refresh(ev)
    assert sent == [] and ev.status == E.PENDING


# ── Token validity ───────────────────────────────────────────────────────────

def _jwt(exp):
    body = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"x.{body}.y"


def test_token_valid_until_expiry_or_401(monkeypatch):
    token = _jwt(time.time() + 3600)
    monkeypatch.setattr(tr, "current_access_token", lambda: token)
    monkeypatch.setattr(tr.config, "ACCESS_TOKEN", token)
    monkeypatch.setattr(tr, "_rejected_token", None)
    assert tr.is_token_valid()               # valid at boot without any renewal having run
    tr.handle_401_unauthorized()
    assert not tr.is_token_valid()           # Dhan rejected it
    new = _jwt(time.time() + 7200)
    monkeypatch.setattr(tr, "current_access_token", lambda: new)
    assert tr.is_token_valid()               # renewed token is trusted again


def test_expired_token_is_invalid(monkeypatch):
    monkeypatch.setattr(tr, "current_access_token", lambda: _jwt(time.time() - 1))
    assert not tr.is_token_valid()
