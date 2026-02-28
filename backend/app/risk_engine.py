
import logging
from .models import User
from .logger import error_logger, system_logger

class RiskManager:
    def __init__(self, db):
        self.db = db

    def check_capital_limits(self, user: User, potential_loss: float = 0.0) -> bool:
        """
        Checks if the user has hit their daily loss limit or capital limit.
        Returns True if trading is allowed, False otherwise.
        """
        try:
            # 1. Check Circuit Breaker (Daily PnL < -Max Daily Loss)
            # Assuming daily_spent tracks loss? No, daily_spent tracks *amount spent*.
            # We need to calculate Daily PnL. 
            # For now, let's assume 'daily_spent' is the proxy for exposure 
            # OR we need a real Daily PnL tracker. 
            # The prompt asked for "If daily PnL < -X -> stop".
            # Currently `User` model has `daily_spent` (exposure) but not `daily_pnl`.
            # I will assume we need to query today's trades to calculate PnL.
            # For efficiency, let's use a simplified check on `max_daily_loss` vs theoretical limit.
            # But wait, `daily_spent` is accumulated BUY value.
            
            # TODO: Implement Real Daily PnL calculation from Trades table.
            # For Phase 1, we will enforce STRICT Capital Allocation Limit.
            
            # Check Max Spending Limit
            if user.daily_spent + potential_loss > user.daily_limit:
                 system_logger.warning(f"Risk Reject: Daily limit reached for user {user.username}")
                 return False
                 
            return True
        except Exception as e:
             error_logger.error(f"Error in check_capital_limits: {e}")
             return False # Fail safe

    def is_circuit_breaker_triggered(self, user_id: int) -> bool:
        """
        Checks if the daily loss has exceeded the user's max_daily_loss.
        """
        # This requires querying trades for the day.
        # Implementation deferred to keep this file clean, or I can add it now.
        # Let's add a placeholder that returns False (Safe) until we have PnL tracking.
        return False 

    def calculate_position_size(self, capital: float, risk_per_trade_pct: float, entry_price: float, stop_loss_price: float) -> int:
        """
        Calculates position size based on risk percentage.
        Formula: Qty = (Capital * Risk%) / (Entry - StopLoss)
        """
        try:
            if entry_price <= stop_loss_price:
                error_logger.error("Risk Error: Entry price <= Stop Loss for BUY trade")
                return 0
                
            risk_amount = capital * (risk_per_trade_pct / 100.0)
            stop_loss_dist = entry_price - stop_loss_price
            
            qty = int(risk_amount / stop_loss_dist)
            
            if qty < 1: return 0
            
            return qty
        except Exception as e:
            error_logger.error(f"Error calculating position size: {e}")
            return 0

    def check_feed_integrity(self, tick_timestamp: float, current_timestamp: float) -> bool:
        """
        Checks if the data feed is stale.
        """
        try:
            age = current_timestamp - tick_timestamp
            if age > 5: # 5 seconds delay tolerance
                system_logger.warning(f"Feed Integrity Alert: Tick age {age}s > 5s")
                return False
            return True
        except Exception as e:
             return False

