import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.alerts import sync_dispatch_alert
from research.utils.market_calendar import is_trading_day

from .. import models
from .strategy_engine import Signal

logger = logging.getLogger("RiskGate")
_IST = ZoneInfo("Asia/Kolkata")

# Dhan intraday equity margin is ~20% of the order value, i.e. up to 5x capital.
# One rule for manual and automated orders, so paper results match what live allows.
INTRADAY_LEVERAGE = Decimal("5")

# Orders accepted but not yet filled
PENDING_STATUSES = [
    models.OrderStatus.NEW,
    models.OrderStatus.ENQUEUED,
    models.OrderStatus.SENDING,
    models.OrderStatus.SUBMITTED,
    models.OrderStatus.BROKER_ACK,
    models.OrderStatus.PARTIALLY_FILLED,
]


def buying_power_left(db: Session, user: models.User) -> Decimal:
    """capital_current x INTRADAY_LEVERAGE minus the value of open and in-flight orders."""
    open_orders = db.query(models.Order).filter(
        models.Order.user_id == user.id,
        models.Order.status.in_(PENDING_STATUSES + [models.OrderStatus.FILLED]),
    ).all()
    committed = sum(
        (Decimal(str(o.average_price or o.entry_price or 0)) * (o.quantity or 0) for o in open_orders),
        Decimal("0"),
    )
    return Decimal(str(user.capital_current or 0)) * INTRADAY_LEVERAGE - committed


def pct_of_capital(user: models.User, pct) -> Decimal:
    return Decimal(str(user.capital_current or 0)) * Decimal(str(pct)) / 100


def month_realized_pnl(db: Session, user: models.User, now: datetime | None = None) -> Decimal:
    """Net P&L of positions closed since the start of this IST month."""
    month_start = (now or datetime.now(timezone.utc)).astimezone(_IST).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0)
    return Decimal(str(db.query(func.sum(models.Order.pnl)).filter(
        models.Order.user_id == user.id,
        models.Order.status == models.OrderStatus.CLOSED,
        models.Order.close_requested_at >= month_start,
    ).scalar() or 0))


def _halt(db: Session, user: models.User, title: str, message: str, **alert_kw) -> bool:
    """Switch automation off (a risk guard tripped), alert, and refuse the trade."""
    logger.error(f"Catastrophic Guard Tripped for {user.username}: {title}. Auto-killing.")
    user.automation_enabled = False
    sync_dispatch_alert("FATAL", title, message, **alert_kw)
    db.commit()
    return False


class RiskGate:
    """Approves or refuses a new automated trade and sizes it; enforces the
    daily reset and the loss / streak circuit breakers."""

    @staticmethod
    def check_intraday_reset(db: Session, user: models.User, current_time: datetime = None) -> None:
        """On the first call of a new day, roll yesterday's result into the
        losing-streak counters and zero realized_pnl."""
        today = (current_time or datetime.now(timezone.utc)).date()
        if user.last_reset_date is not None and user.last_reset_date >= today:
            return
        logger.info(f"RiskGate: Performing Intraday Reset for user {user.username}")
        m = user.portfolio_metrics
        if m:
            if m.realized_pnl < 0:
                m.consecutive_loss_days = (m.consecutive_loss_days or 0) + 1
                hit = -Decimal(str(m.realized_pnl)) >= pct_of_capital(user, user.max_daily_dd)
                m.consecutive_dd_hits = (m.consecutive_dd_hits or 0) + 1 if hit else 0
            elif m.realized_pnl > 0:   # a flat day does not reset the streaks
                m.consecutive_loss_days = 0
                m.consecutive_dd_hits = 0
            m.realized_pnl = 0.0
        user.last_reset_date = today
        db.commit()

    @staticmethod
    def daily_loss_limit_hit(db: Session, user: models.User) -> bool:
        """Today's realized loss has reached max_daily_dd. Guards manual entries."""
        RiskGate.check_intraday_reset(db, user)
        m = user.portfolio_metrics
        pnl = Decimal(str(m.realized_pnl or 0)) if m else Decimal('0')
        return pnl < 0 and -pnl >= pct_of_capital(user, user.max_daily_dd)

    @staticmethod
    def validate_risk(db: Session, user: models.User, system_settings: models.SystemSettings, signal: Signal,
                      portfolio_snapshot: dict = None, current_time: datetime = None) -> bool:
        """True if the user may take this new automated trade."""
        current_time = current_time or datetime.now(timezone.utc)
        RiskGate.check_intraday_reset(db, user, current_time)
        snapshot = portfolio_snapshot or {}
        m = user.portfolio_metrics

        if system_settings and system_settings.emergency_stop:
            logger.error("RiskGate Blocked: GLOBAL EMERGENCY STOP ACTIVE.")
            sync_dispatch_alert("CRITICAL", "Emergency Stop Driven", f"Signal {signal.symbol} Blocked. Global Switch is ON.")
            return False

        ist_time = current_time.astimezone(_IST)
        if not is_trading_day(ist_time.date()):
            logger.warning(f"RiskGate Blocked: not an NSE trading day (IST: {ist_time.date()}).")
            return False
        t = ist_time.time()
        if user.session_start_time and user.session_end_time and not (
                user.session_start_time <= t <= user.session_end_time):
            logger.warning(f"RiskGate Blocked: {t} IST outside {user.session_start_time}-{user.session_end_time}")
            return False

        if not user.automation_enabled:
            logger.warning(f"RiskGate Blocked: Automation disabled for user {user.username}.")
            return False

        if snapshot.get("missing_cmp"):   # fail closed: can't value open positions
            logger.error(f"RiskGate Blocked: no live price for an open position of {user.username}.")
            return False

        if m and (m.consecutive_dd_hits or 0) >= 3:
            return _halt(db, user, "Anomaly Clustering: Repeated DD Hit",
                         f"{user.username} hit max daily drawdown 3 days in a row.")
        if m and (m.consecutive_loss_days or 0) >= 5:
            return _halt(db, user, "Anomaly Clustering: Losing Streak",
                         f"{user.username} lost money 5 days in a row.")

        recent = db.query(models.Order).filter(
            models.Order.user_id == user.id,
            models.Order.created_at >= current_time - timedelta(minutes=1),
        ).count()
        if recent >= user.max_orders_per_minute:
            logger.warning(f"RiskGate Blocked: Order throttle reached for {user.username}. ({recent}/{user.max_orders_per_minute} in 60s)")
            return False

        open_positions = db.query(models.Order).filter(
            models.Order.user_id == user.id,
            models.Order.status.in_(PENDING_STATUSES + [models.OrderStatus.FILLED]),
        ).count()
        if open_positions >= user.max_open_positions:
            logger.warning(f"RiskGate Blocked: Max open positions reached for {user.username}. ({open_positions}/{user.max_open_positions})")
            return False

        # Today's loss = realized loss + any unrealized loss on open positions
        realized = Decimal(str(m.realized_pnl)) if m and m.realized_pnl else Decimal(0)
        unrealized = Decimal(str(snapshot.get("unrealized_pnl", 0)))
        daily_loss = max(Decimal(0), -realized) + max(Decimal(0), -unrealized)
        monthly_loss = max(Decimal(0), -month_realized_pnl(db, user, current_time))
        max_daily = pct_of_capital(user, user.max_daily_dd)
        max_monthly = pct_of_capital(user, user.max_monthly_dd)

        if daily_loss > max_daily:
            return _halt(db, user, "Daily Risk Max Violation", f"{user.username} exceeded daily limit. Automation halted.",
                         metadata={"current": float(daily_loss), "max": float(max_daily)})
        if monthly_loss > max_monthly:
            return _halt(db, user, "Monthly Risk Max Violation", f"{user.username} exceeded monthly limit. Automation halted.",
                         metadata={"current": float(monthly_loss), "max": float(max_monthly)})

        # Forward-looking: this trade's full risk must still fit under both limits
        trade_risk = pct_of_capital(user, user.risk_category.max_risk_pct)
        if daily_loss + trade_risk > max_daily:
            logger.warning(f"RiskGate Blocked: daily loss {daily_loss} + trade risk {trade_risk} > {max_daily} for {user.username}")
            return False
        if monthly_loss + trade_risk > max_monthly:
            logger.warning(f"RiskGate Blocked: monthly loss {monthly_loss} + trade risk {trade_risk} > {max_monthly} for {user.username}")
            return False
        return True

    @staticmethod
    def calculate_position_size(user: models.User, signal: Signal) -> int:
        """Shares such that hitting the stop loses the user's per-trade risk %; 0 if the stop is on the wrong side."""
        stop_distance = (signal.entry_price - signal.stop_loss if signal.direction == "LONG"
                         else signal.stop_loss - signal.entry_price)
        if stop_distance <= 0:
            logger.error(f"RiskGate Sizing Error: Negative or zero stop distance. Entry={signal.entry_price}, SL={signal.stop_loss}")
            return 0
        return int(pct_of_capital(user, user.risk_category.max_risk_pct) // stop_distance)
