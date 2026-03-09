import math
from typing import Optional
import logging
from datetime import datetime, date, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from decimal import Decimal
from .strategy_engine import Signal
from .. import models
from app.core.alerts import sync_dispatch_alert

logger = logging.getLogger("RiskGate")

class RiskGate:
    """
    The deterministic gatekeeper.
    Takes a pure Signal and User constraints, returning a boolean approval 
    and the calculated position size. Enforces resets and circuit breakers.
    """
    
    @staticmethod
    def check_intraday_reset(db: Session, user: models.User, current_time: datetime = None) -> None:
        """
        Forcefully resets realized_pnl if a new session has started.
        """
        if not current_time:
            current_time = datetime.now(timezone.utc)
            
        today = current_time.date()
        
        # If last_reset_date is None or prior to today, we perform a reset
        # (A more complex version might verify session overlap, but daily reset is safe here)
        if user.last_reset_date is None or user.last_reset_date < today:
            logger.info(f"RiskGate: Performing Intraday Reset for user {user.username}")
            if user.portfolio_metrics:
                # Phase 3.995: Anomaly Tracking Updates
                if user.portfolio_metrics.realized_pnl < 0:
                    user.portfolio_metrics.consecutive_loss_days = (user.portfolio_metrics.consecutive_loss_days or 0) + 1
                    
                    max_loss_amount = Decimal(str(user.capital_current)) * (Decimal(str(user.max_daily_dd)) / Decimal('100.0'))
                    if abs(Decimal(str(user.portfolio_metrics.realized_pnl))) >= max_loss_amount:
                        user.portfolio_metrics.consecutive_dd_hits = (user.portfolio_metrics.consecutive_dd_hits or 0) + 1
                    else:
                        user.portfolio_metrics.consecutive_dd_hits = 0
                elif user.portfolio_metrics.realized_pnl > 0:
                    # Only reset streak if they had a winning day. Flat days do not reset the streak.
                    user.portfolio_metrics.consecutive_loss_days = 0
                    user.portfolio_metrics.consecutive_dd_hits = 0
                    
                user.portfolio_metrics.realized_pnl = 0.0
                user.portfolio_metrics.current_drawdown = 0.0
            
            user.last_reset_date = today
            db.add(user)
            db.commit()

    @staticmethod
    def validate_risk(db: Session, user: models.User, system_settings: models.SystemSettings, signal: Signal, current_time: datetime = None) -> bool:
        """
        Validates if the user is allowed to take a new trade.
        """
        if not current_time:
            current_time = datetime.now(timezone.utc)
            
        RiskGate.check_intraday_reset(db, user, current_time)
            
        # 1. Global Circuit Breaker
        if system_settings and system_settings.emergency_stop:
            logger.error("RiskGate Blocked: GLOBAL EMERGENCY STOP ACTIVE.")
            sync_dispatch_alert("CRITICAL", "Emergency Stop Driven", f"Signal {signal.symbol} Blocked. Global Switch is ON.")
            return False
            
        # 1.5 NSE Session Boundary & Timezone Locking
        IST = timezone(timedelta(hours=5, minutes=30))
        ist_time = current_time.astimezone(IST)
        
        if ist_time.weekday() >= 5:
            logger.warning(f"RiskGate Blocked: Ghost execution suppressed on weekend (IST: {ist_time.date()}).")
            return False
            
        current_t = ist_time.time()
        if user.session_start_time and user.session_end_time:
            if current_t < user.session_start_time or current_t > user.session_end_time:
                logger.warning(f"RiskGate Blocked: Ghost execution suppressed out of NSE hours. {current_t} IST not in {user.session_start_time}-{user.session_end_time}")
                return False
            
        # 2. User Level Flag
        if not user.automation_enabled:
            logger.warning(f"RiskGate Blocked: Automation disabled for user {user.username}.")
            return False
            
        # 2.5 Kill-Switch Escalation Logic (Anomaly Clustering)
        if user.portfolio_metrics:
            if (user.portfolio_metrics.consecutive_dd_hits or 0) >= 3:
                logger.error(f"Catastrophic Guard Tripped: User {user.username} had 3 consecutive Daily DD hits. Auto-killing.")
                user.automation_enabled = False
                sync_dispatch_alert("FATAL", "Anomaly Clustering: Repeated DD Hit", f"{user.username} hit max daily drawdown 3 days in a row.")
                db.commit()
                return False
                
            if (user.portfolio_metrics.consecutive_loss_days or 0) >= 5:
                logger.error(f"Catastrophic Guard Tripped: User {user.username} had 5 consecutive losing days. Auto-killing.")
                user.automation_enabled = False
                sync_dispatch_alert("FATAL", "Anomaly Clustering: Losing Streak", f"{user.username} lost money 5 days in a row.")
                db.commit()
                return False
            
        # 3. Throttle: Max Orders Per Minute
        one_min_ago = current_time - timedelta(minutes=1)
        recent_orders_count = db.query(models.Order).filter(
            models.Order.user_id == user.id,
            models.Order.created_at >= one_min_ago
        ).count()
        
        if recent_orders_count >= user.max_orders_per_minute:
            logger.warning(f"RiskGate Blocked: Order throttle reached for {user.username}. ({recent_orders_count}/{user.max_orders_per_minute} in 60s)")
            return False
            
        # 4. Throttle: Max Open Positions
        open_positions = db.query(models.Order).filter(
            models.Order.user_id == user.id,
            models.Order.status.in_([models.OrderStatus.NEW, models.OrderStatus.ENQUEUED, models.OrderStatus.SENDING, models.OrderStatus.SUBMITTED, models.OrderStatus.BROKER_ACK, models.OrderStatus.PARTIALLY_FILLED])
        ).count()
        
        if open_positions >= user.max_open_positions:
            logger.warning(f"RiskGate Blocked: Max open positions reached for {user.username}. ({open_positions}/{user.max_open_positions})")
            return False
            
        # 6. Forward-Looking Daily & Monthly Drawdown Limit
        metrics = user.portfolio_metrics
        current_daily_loss = abs(Decimal(str(metrics.realized_pnl))) if metrics and metrics.realized_pnl < 0 else Decimal('0.0')
        max_daily_loss_amount = Decimal(str(user.capital_current)) * (Decimal(str(user.max_daily_dd)) / Decimal('100.0'))
        
        # Monthly Drop Check
        first_day_of_month = current_time.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        monthly_losing_trades = db.query(func.sum(models.Order.pnl)).filter(
            models.Order.user_id == user.id,
            models.Order.status == models.OrderStatus.FILLED,
            models.Order.updated_at >= first_day_of_month,
            models.Order.pnl < 0
        ).scalar() or Decimal('0.0')
        
        monthly_winning_trades = db.query(func.sum(models.Order.pnl)).filter(
            models.Order.user_id == user.id,
            models.Order.status == models.OrderStatus.FILLED,
            models.Order.updated_at >= first_day_of_month,
            models.Order.pnl > 0
        ).scalar() or Decimal('0.0')
        
        current_monthly_loss = abs(Decimal(str(monthly_losing_trades)) - Decimal(str(monthly_winning_trades))) if (monthly_losing_trades + monthly_winning_trades) < 0 else Decimal('0.0')
        max_monthly_loss_amount = Decimal(str(user.capital_current)) * (Decimal(str(user.max_monthly_dd)) / Decimal('100.0'))
        
        # 6.5 STRUCTURAL HARD KILL CHECKS
        # If previous trades slipped us into oblivion beyond the theoretical bounds
        if current_daily_loss > max_daily_loss_amount:
            logger.error(f"Catastrophic Guard Tripped: User {user.username} realized Daily DD exceeded structural bound. Auto-killing.")
            user.automation_enabled = False
            sync_dispatch_alert("FATAL","Daily Risk Max Violation", f"{user.username} exceeded daily limit. Automation halted.", metadata={"current": float(current_daily_loss), "max": float(max_daily_loss_amount)})
            db.commit()
            return False
            
        if current_monthly_loss > max_monthly_loss_amount:
            logger.error(f"Catastrophic Guard Tripped: User {user.username} realized Monthly DD exceeded structural bound. Auto-killing.")
            user.automation_enabled = False
            sync_dispatch_alert("FATAL","Monthly Risk Max Violation", f"{user.username} exceeded monthly limit. Automation halted.", metadata={"current": float(current_monthly_loss), "max": float(max_monthly_loss_amount)})
            db.commit()
            return False
            
        # Theoretical trade risk is now based strictly on the User's core Category Profile
        risk_per_trade_pct = Decimal(str(user.risk_category.max_risk_pct))
        theoretical_trade_risk = Decimal(str(user.capital_current)) * (risk_per_trade_pct / Decimal('100.0'))
        
        # Strict Forward-Looking Check
        if (current_daily_loss + theoretical_trade_risk) > max_daily_loss_amount:
            logger.warning(f"RiskGate Blocked: Forward-Looking Daily DD breach for {user.username}. Current DD: {current_daily_loss}, New Trade Risk: {theoretical_trade_risk}, Max Allowed: {max_daily_loss_amount}")
            return False
            
        if (current_monthly_loss + theoretical_trade_risk) > max_monthly_loss_amount:
            logger.warning(f"RiskGate Blocked: Forward-Looking Monthly DD breach for {user.username}. Current DD: {current_monthly_loss}, New Trade Risk: {theoretical_trade_risk}, Max Allowed: {max_monthly_loss_amount}")
            return False
            
        return True

    @staticmethod
    def calculate_position_size(user: models.User, signal: Signal, lot_size: int = 25) -> int:
        """
        Calculates position size strictly using exact Decimal math.
        Rounds down to the nearest whole lot size.
        """
        if signal.direction == "LONG":
            stop_distance = signal.entry_price - signal.stop_loss
        else:
            stop_distance = signal.stop_loss - signal.entry_price
            
        if stop_distance <= Decimal('0'):
            logger.error(f"RiskGate Sizing Error: Negative or zero stop distance. Entry={signal.entry_price}, SL={signal.stop_loss}")
            return 0
            
        # Hard Structural override. Forget arbitrary strategy allocation here. Risk is based purely on the User's predefined Prop-Desk Tier.
        risk_per_trade_pct = Decimal(str(user.risk_category.max_risk_pct))
            
        risk_capital = Decimal(str(user.capital_current)) * (risk_per_trade_pct / Decimal('100.0'))
        raw_quantity = risk_capital / stop_distance
        
        # Exact integer division using Decimal to prevent float rounding bounds
        lots = int(raw_quantity // Decimal(str(lot_size)))
        qty = lots * lot_size
        
        return int(qty)
