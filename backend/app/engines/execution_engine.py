import logging
from sqlalchemy.orm import Session
from .. import models
from .strategy_engine import Signal
from .risk_engine import RiskGate
from decimal import Decimal
from datetime import datetime, timezone
import sqlalchemy
from sqlalchemy import func
from app.core.alerts import sync_dispatch_alert

logger = logging.getLogger("ExecutionEngine")

class ExecutionEngine:
    def __init__(self, db: Session):
        self.db = db

    def process_signal(self, signal: Signal) -> list:
        """
        Takes a pure mathematical Signal and routes it to users via the RiskGate.
        Simulates Execution by generating Order records directly.
        Returns a list of created Order IDs.
        """
        logger.info(f"ExecutionEngine Processing: {signal}")
        
        # 1. Find all active allocations for this strategy
        allocations = self.db.query(models.UserStrategyAllocation)\
            .filter(models.UserStrategyAllocation.strategy_id == signal.strategy_id)\
            .all()
            
        executed_orders = []
            
        for alloc in allocations:
            user_id = alloc.user_id
            
            # 0. DB-Level Idempotency Check (Per User)
            existing = self.db.query(models.Order).filter(
                models.Order.user_id == user_id,
                models.Order.signal_hash == signal.signal_hash
            ).first()
            
            if existing:
                if existing.status == models.OrderStatus.REJECTED and existing.rejection_count < 3:
                    logger.info(f"Retrying rejected signal for user {user_id}. Attempt {existing.rejection_count + 1}")
                else:
                    logger.warning(f"Duplicate or Max-Retry Signal Rejected by DB Check for User {user_id}: {signal.signal_hash}")
                    continue

            try:
                # 0.2 PRE-FLIGHT BROKER HEALTH GUARD
                from app.config import config
                from app.services.token_renewal import is_token_valid
                
                if not config.ACCESS_TOKEN or not is_token_valid():
                    logger.error(f"Broker Health Guard Failed for {user_id}: DHAN_ACCESS_TOKEN is missing or unauthorized (401 flagged). Halting order flow.")
                    break # Break entirely, token is dead. Need to wait for token_renewal daemon.

                # 2. CONCURRENCY SHIELD: Lock the user row for this transaction
                user = self.db.query(models.User).filter(models.User.id == user_id).with_for_update().first()
                if not user:
                    continue
                    
                # 0.5 Fetch System Settings (Global Circuit Breaker) INSIDE lock to prevent mid-tx race
                system_settings = self.db.query(models.SystemSettings).first()
                    
                # 2.5 Strict Transit & Position Guards
                transit_order = self.db.query(models.Order).filter(
                    models.Order.user_id == user.id,
                    models.Order.symbol == signal.symbol,
                    models.Order.status.in_([
                        models.OrderStatus.NEW,
                        models.OrderStatus.ENQUEUED,
                        models.OrderStatus.SENDING,
                        models.OrderStatus.SUBMITTED,
                        models.OrderStatus.BROKER_ACK,
                        models.OrderStatus.PARTIALLY_FILLED
                    ])
                ).first()
                
                # Check if it's our recycled order in transit
                # It shouldn't be, since existing status is REJECTED
                if transit_order and (not existing or transit_order.id != existing.id):
                    # Just print generic warning so Windows cp1252 doesn't explode
                    logger.warning(f"User {user.username} blocked: Transit order exists for {signal.symbol}.")
                    continue
                    
                longs = self.db.query(func.sum(models.Order.filled_quantity)).filter(
                    models.Order.user_id == user.id,
                    models.Order.symbol == signal.symbol,
                    models.Order.direction == models.Direction.LONG,
                    models.Order.status.in_([models.OrderStatus.FILLED, models.OrderStatus.PARTIALLY_FILLED])
                ).scalar() or 0
                
                shorts = self.db.query(func.sum(models.Order.filled_quantity)).filter(
                    models.Order.user_id == user.id,
                    models.Order.symbol == signal.symbol,
                    models.Order.direction == models.Direction.SHORT,
                    models.Order.status.in_([models.OrderStatus.FILLED, models.OrderStatus.PARTIALLY_FILLED])
                ).scalar() or 0
                
                current_position = int(longs) - int(shorts)
                
                # Prevent Pyramiding: Block entry if we already have a position in the same direction
                if current_position != 0:
                    if (current_position > 0 and signal.direction == 'LONG') or (current_position < 0 and signal.direction == 'SHORT'):
                        logger.warning(f"User {user.username} blocked: Open position limit reached for {signal.symbol}.")
                        continue
                
                # 3. Execution Gate
                is_approved = RiskGate.validate_risk(
                    db=self.db,
                    user=user,
                    system_settings=system_settings,
                    signal=signal,
                    current_time=signal.timestamp
                )
                
                if not is_approved:
                    logger.warning(f"User {user.username} blocked by RiskGate.")
                    continue
                    
                # 4. Capital Fragmentation Calculation
                allocation_pct = Decimal(str(alloc.allocation_percentage))
                allocated_capital = Decimal(str(user.capital_current)) * (allocation_pct / Decimal('100.0'))
                
                # 5. Position Sizing
                size = RiskGate.calculate_position_size(
                    user=user,
                    signal=signal,
                    lot_size=1
                )
                
                if size <= 0:
                    logger.warning(f"User {user.username} rejected: Zero position size.")
                    continue
                    
                # 5.5 Margin Cache Guardrail
                # Assumes conservative 5x leverage for intraday NSE equity
                estimated_margin_required = (signal.entry_price * Decimal(str(size))) / Decimal('5.0')
                
                # Check for stale margin cache
                current_time = datetime.now(timezone.utc)
                if user.portfolio_metrics:
                    last_sync = user.portfolio_metrics.last_margin_sync
                    if last_sync and (current_time - last_sync).total_seconds() > 30:
                        logger.warning(f"User {user.username} rejected via Stale Margin Guard: Cache is > 30s old.")
                        sync_dispatch_alert("WARNING", "Stale Margin Cache", f"Blocked execution for {user.username}. Cache delta > 30s.")
                        continue
                        
                    if user.portfolio_metrics.available_margin < estimated_margin_required:
                        # In a real scenario, this helps pre-empt a broker HTTP 400 rejection
                        logger.warning(f"User {user.username} rejected via Local Margin Guard: Requires {estimated_margin_required:.2f}, Cache has {user.portfolio_metrics.available_margin:.2f}")
                        continue
                    
                # 6. Build and Store Order
                if existing:
                    order = existing
                    order.quantity = size
                    order.entry_price = signal.entry_price
                    order.status = models.OrderStatus.NEW
                else:
                    side = models.Direction.LONG if signal.direction == "LONG" else models.Direction.SHORT
                    order = models.Order(
                        user_id=user.id,
                        signal_id=None,
                        signal_hash=signal.signal_hash,
                        symbol=signal.symbol,
                        direction=side,
                        quantity=size,
                        entry_price=signal.entry_price,
                        status=models.OrderStatus.NEW,
                        rejection_count=0
                    )
                    self.db.add(order)
                    
                self.db.flush() # Get order ID without committing
                
                # 7. Create OutboxEvent Transactionally
                outbox_event = models.OutboxEvent(
                    order_id=order.id,
                    event_type="SEND_TO_BROKER",
                    status=models.OutboxEventStatus.PENDING,
                    payload={
                        "symbol": order.symbol,
                        "qty": order.quantity,
                        "direction": order.direction.value,
                        "price": float(order.entry_price),
                        "order_type": "LIMIT" if order.entry_price > 0 else "MARKET",
                        "correlation_id": f"USR{user.id}_SIG{signal.signal_hash[:10]}"
                    }
                )
                self.db.add(outbox_event)
                
                self.db.commit()
                self.db.refresh(order)
                
                executed_orders.append(order.id)
                logger.info(f"User {user.username} ENQUEUED: {size}x {signal.symbol} @ {signal.entry_price}")
                
            except sqlalchemy.exc.IntegrityError:
                self.db.rollback()
                logger.warning(f"IntegrityError Caught: Concurrent double signal insertion blocked for user {user_id}")
                continue
            except Exception as e:
                self.db.rollback()
                logger.error(f"Unexpected error in process_signal: {str(e)}")
                continue
            
        return executed_orders

    def handle_broker_rejection(self, order_id: int, reason: str):
        """
        Called when the Live API rejects an order.
        Marks OrderStatus to REJECTED. Maintains signal_hash so retry bounds (3 limit) apply.
        """
        order = self.db.query(models.Order).filter(models.Order.id == order_id).with_for_update().first()
        if not order:
            return
            
        logger.error(f"Broker Rejected Order {order_id} (User {order.user_id}): {reason}")
        
        # We NO LONGER clear `signal_hash` here to avoid infinite loops and maintain `UniqueConstraint` bounds
        # order.signal_hash = None
                
        # 2. Revert order state
        order.status = models.OrderStatus.REJECTED
        order.rejection_count = (order.rejection_count or 0) + 1
        
        # 2.5 Hard Kill on persistent Rejections (e.g., Margin shortfall from Dhan)
        user = self.db.query(models.User).filter(models.User.id == order.user_id).first()
        
        # Count total rejections today
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        daily_rejections = self.db.query(models.Order).filter(
            models.Order.user_id == user.id,
            models.Order.status == models.OrderStatus.REJECTED,
            models.Order.created_at >= today
        ).count()
        
        # Adding 1 for the current rejection that hasn't been committed yet
        if (daily_rejections + 1) >= 5:
            logger.error(f"Catastrophic Guard Tripped: User {user.username} exceeded daily broker rejection threshold limit (5). Auto-killing.")
            user.automation_enabled = False
            sync_dispatch_alert("FATAL", "Broker Rejection Anomaly", f"{user.username} had 5 orders rejected. Halted.")
            
        self.db.commit()

    def handle_partial_fill(self, order_id: int, filled_qty: int, fill_price: Decimal, fill_id: str):
        """
        Called when Dhan WebSockets stream a partial fill.
        """
        order = self.db.query(models.Order).filter(models.Order.id == order_id).with_for_update().first()
        if not order:
            return
            
        # 0. WebSocket Deduplication
        existing_fill = self.db.query(models.TradeFill).filter(models.TradeFill.fill_id == fill_id).first()
        if existing_fill:
            logger.warning(f"Ignoring Duplicate Fill ID: {fill_id}")
            return
            
        # 0.5 Terminal State Validation Constraint
        # A FILLED or CANCELLED order cannot process more fills.
        if order.status in [models.OrderStatus.FILLED, models.OrderStatus.CANCELLED, models.OrderStatus.REJECTED]:
            logger.error(f"Invalid State Transition: Attempted to process fill on Order {order_id} with status {order.status}")
            return
            
        # 1. Save TradeFill to prevent future duplicates
        db_fill = models.TradeFill(
            order_id=order.id,
            fill_id=fill_id,
            quantity=filled_qty,
            price=fill_price
        )
        self.db.add(db_fill)
            
        # 2. Recalculate Average Fill Price
        old_filled = order.filled_quantity
        old_avg = Decimal(str(order.average_price)) if order.average_price else Decimal('0.0')
        
        new_total_filled = old_filled + filled_qty
        
        if new_total_filled > 0:
            # Weighted average using precision math
            value1 = old_avg * Decimal(str(old_filled))
            value2 = fill_price * Decimal(str(filled_qty))
            total_value = value1 + value2
            new_avg = total_value / Decimal(str(new_total_filled))
            
            order.average_price = new_avg
            order.filled_quantity = new_total_filled
            
        # 3. Update status directionally
        if order.filled_quantity >= order.quantity:
            order.status = models.OrderStatus.FILLED
        elif order.status != models.OrderStatus.PARTIALLY_FILLED:
            order.status = models.OrderStatus.PARTIALLY_FILLED
            
        self.db.commit()
        logger.info(f"Order {order_id} filled {filled_qty} @ {fill_price}. Avg now {order.average_price:.2f}. Total {order.filled_quantity}/{order.quantity}")
