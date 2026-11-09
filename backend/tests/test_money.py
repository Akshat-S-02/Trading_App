"""
Money-path tests: charges, position sizing, exit rules, realised P&L, backtest fills.
Pure logic plus an in-memory SQLite DB; never touches Postgres or Redis.

    cd backend && .venv/bin/python -m pytest tests/test_money.py -q
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace as NS
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")  # app.db needs a URL; we never use its engine

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.db import Base
from app.engines.execution_engine import ExecutionEngine
from app.engines.paper_strategy_runner import PaperStrategyRunner
from app.engines.risk_engine import RiskGate
from app.engines.strategy_engine import Signal
from research.backtest.engine import BacktestEngine
from research.utils.fee_calculator import FeeConfig, calculate_charges

IST = ZoneInfo("Asia/Kolkata")
LONG, SHORT = models.Direction.LONG, models.Direction.SHORT


# ── Charges ──────────────────────────────────────────────────────────────────

def test_brokerage_is_capped_by_percentage_on_small_orders():
    small = calculate_charges(FeeConfig(), "buy", qty=1, price=2500.0)
    assert small["brokerage"] == pytest.approx(0.75)          # 0.03% of 2,500, not Rs 20


def test_brokerage_is_flat_20_on_large_orders():
    big = calculate_charges(FeeConfig(), "sell", qty=100, price=2500.0)
    assert big["brokerage"] == 20.0
    assert big["stt"] == pytest.approx(250000 * 0.025 / 100)  # STT on the sell side only
    assert big["stamp"] == 0.0


# ── Position sizing ──────────────────────────────────────────────────────────

def _user(capital=50000):
    return NS(capital_current=Decimal(capital), risk_category=models.RiskCategory.LOW)


def _signal(direction, entry, sl):
    return Signal(strategy_id=1, symbol="TCS", direction=direction, entry_price=Decimal(entry),
                  stop_loss=Decimal(sl), timestamp=datetime.now(timezone.utc), strategy_name="orb_v4")


def test_long_size_risks_category_pct_of_capital():
    # LOW = 0.75% of 50,000 = 375 risk; stop distance 5 -> 75 shares
    assert RiskGate.calculate_position_size(_user(), _signal("LONG", "100", "95"), lot_size=1) == 75


def test_short_size_uses_stop_above_entry():
    assert RiskGate.calculate_position_size(_user(), _signal("SHORT", "100", "105"), lot_size=1) == 75


def test_stop_on_wrong_side_sizes_zero():
    assert RiskGate.calculate_position_size(_user(), _signal("LONG", "100", "101"), lot_size=1) == 0


# ── Exit rules ───────────────────────────────────────────────────────────────

def _order(direction, sl=None, target=None, opened=None):
    return NS(direction=direction, signal=NS(stop_loss=sl, target_price=target),
              created_at=opened or datetime.now(timezone.utc))


NOON = datetime.now(IST).replace(hour=12, minute=0, second=0, microsecond=0)
evaluate = PaperStrategyRunner._evaluate_exit


@pytest.mark.parametrize("direction,ltp,expected", [
    (LONG, 94.9, "SL"), (LONG, 110, "TARGET"), (LONG, 100, None),
    (SHORT, 105.1, "SL"), (SHORT, 90, "TARGET"), (SHORT, 100, None),
])
def test_sl_and_target(direction, ltp, expected):
    sl, tgt = (95, 110) if direction == LONG else (105, 90)
    order = _order(direction, sl, tgt, opened=NOON.astimezone(timezone.utc))
    assert evaluate(PaperStrategyRunner, order, ltp, NOON) == expected


def test_eod_closes_at_cutoff():
    order = _order(LONG, opened=NOON.astimezone(timezone.utc))
    assert evaluate(PaperStrategyRunner, order, 100, NOON.replace(hour=15, minute=20)) == "EOD"


def test_position_from_previous_day_is_squared_off():
    order = _order(LONG, opened=(NOON - timedelta(days=1)).astimezone(timezone.utc))
    assert evaluate(PaperStrategyRunner, order, 100, NOON) == "EOD"


# ── Realised P&L on close ────────────────────────────────────────────────────

@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.mark.parametrize("direction,entry,exit_ltp,sign", [(LONG, 100, 110, 1), (SHORT, 100, 90, 1), (LONG, 100, 90, -1)])
def test_close_books_net_pnl_into_capital(db, direction, entry, exit_ltp, sign, monkeypatch):
    monkeypatch.setattr("app.engines.execution_engine.sync_dispatch_alert", lambda *a, **k: None)
    user = models.User(username="t", capital_initial=50000, capital_current=50000)
    db.add(user); db.flush()
    db.add(models.PortfolioMetrics(user_id=user.id, peak_equity=50000))
    order = models.Order(user_id=user.id, symbol="TCS", direction=direction, quantity=10,
                         filled_quantity=10, entry_price=entry, average_price=entry,
                         status=models.OrderStatus.FILLED)
    db.add(order); db.commit()

    ExecutionEngine(db).close_paper_position(order.id, exit_ltp, "TEST")
    db.refresh(order); db.refresh(user)

    slip = Decimal("0.10")  # 2 ticks against us on exit
    exit_px = Decimal(exit_ltp) - slip if direction == LONG else Decimal(exit_ltp) + slip
    gross = (exit_px - entry) * 10 if direction == LONG else (entry - exit_px) * 10
    assert order.status == models.OrderStatus.CLOSED
    assert Decimal(order.exit_price) == exit_px
    assert 0 < gross - Decimal(order.pnl) < 10            # net = gross minus a few rupees of charges
    assert (Decimal(order.pnl) > 0) == (sign > 0)
    assert Decimal(user.capital_current) == Decimal(50000) + Decimal(order.pnl)

    # Closing twice must not double-count
    ExecutionEngine(db).close_paper_position(order.id, exit_ltp, "TEST")
    db.refresh(user)
    assert Decimal(user.capital_current) == Decimal(50000) + Decimal(order.pnl)


# ── Backtest fills ───────────────────────────────────────────────────────────

_fake_bt = NS(_close_position=lambda pos, bar, reason, px: (reason, px))


@pytest.mark.parametrize("direction,stop,target,bar,expected", [
    # long gaps down through its stop -> fills at the open, not the stop
    ("LONG", 95.0, 110.0, (92.0, 93.0, 91.0), ("stop_loss", 92.0)),
    ("LONG", 95.0, 110.0, (100.0, 111.0, 99.0), ("target_hit", 110.0)),
    # short: stop is above, target below; a gap up through the stop fills at the open
    ("SHORT", 105.0, 90.0, (108.0, 109.0, 107.0), ("stop_loss", 108.0)),
    ("SHORT", 105.0, 90.0, (100.0, 101.0, 89.0), ("target_hit", 90.0)),
])
def test_backtest_exit_fills(direction, stop, target, bar, expected):
    pos = {"direction": direction, "stop_loss": stop, "target": target}
    o, h, l = bar
    b = {"open": o, "high": h, "low": l, "close": o, "timestamp": NOON}
    assert BacktestEngine._check_exit(_fake_bt, pos, b, []) == (True, expected)


def test_backtest_short_is_sized_and_profits_when_price_falls():
    eng = BacktestEngine.__new__(BacktestEngine)
    eng.risk_config = NS(capital=50000, risk_pct=1.0)
    eng.slippage_config = __import__("research.utils.fee_calculator", fromlist=["x"]).SlippageConfig(ticks=0)
    eng.fee_config = FeeConfig()
    sig = NS(direction="SHORT", entry_price=100.0, stop_loss=105.0, target=90.0, entry_reason="t", meta={})
    pos = eng._open_position(sig, {"timestamp": NOON, "high": 100, "low": 100}, "TCS", "1")
    assert pos is not None and pos["quantity"] == 100          # 500 risk / 5 per share
    trade = eng._close_position(pos, {"timestamp": NOON, "close": 90.0}, "target_hit", 90.0)
    assert trade["gross_pnl"] == pytest.approx(1000.0)         # (100 - 90) * 100
    assert trade["net_pnl"] < trade["gross_pnl"]


# ── Daily loss limit also guards manual orders ───────────────────────────────

@pytest.mark.parametrize("realized,blocked", [(0, False), (-999, False), (-1000, True), (500, False)])
def test_daily_loss_limit_hit(db, realized, blocked):
    user = models.User(username="t", capital_initial=50000, capital_current=50000, max_daily_dd=2,
                       last_reset_date=datetime.now(timezone.utc).date())
    db.add(user); db.flush()
    db.add(models.PortfolioMetrics(user_id=user.id, peak_equity=50000, realized_pnl=realized)); db.commit()
    db.refresh(user)
    assert RiskGate.daily_loss_limit_hit(db, user) is blocked   # 2% of 50k = 1000


# ── A rejected order is never re-sent by a repeated signal ───────────────────

def test_repeated_signal_after_rejection_creates_nothing(db):
    user = models.User(username="t", capital_initial=50000, capital_current=50000)
    db.add(user); db.flush()
    db.add(models.UserStrategyAllocation(user_id=user.id, strategy_id=1, allocation_percentage=100))
    db.add(models.Order(user_id=user.id, symbol="TCS", direction=LONG, quantity=1, entry_price=100,
                        signal_hash="h1", status=models.OrderStatus.REJECTED, rejection_count=1))
    db.commit()
    sig = Signal(strategy_id=1, symbol="TCS", direction="LONG", entry_price=Decimal("100"),
                 stop_loss=Decimal("95"), timestamp=datetime.now(timezone.utc), strategy_name="orb_v4")
    sig.signal_hash = "h1"
    assert ExecutionEngine(db).process_signal(sig) == []
    assert db.query(models.OutboxEvent).count() == 0
    assert db.query(models.Order).one().status == models.OrderStatus.REJECTED
