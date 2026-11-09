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

    def _build_portfolio_snapshot(self, user_id: int) -> dict:
        from app.core.tick_store import get_tick
        
        # Fetch today's executed orders to build deterministic intraday exposure
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        orders = self.db.query(models.Order).filter(
            models.Order.user_id == user_id,
            models.Order.status.in_([models.OrderStatus.FILLED, models.OrderStatus.PARTIALLY_FILLED]),
            models.Order.filled_quantity > 0,
            models.Order.created_at >= today
        ).all()
        
        positions = {}
        for o in orders:
            sym = o.symbol
            if sym not in positions:
                positions[sym] = {
                    'long_qty': Decimal('0.0'), 'long_val': Decimal('0.0'),
                    'short_qty': Decimal('0.0'), 'short_val': Decimal('0.0')
                }
            qty = Decimal(str(o.filled_quantity))
            price = Decimal(str(o.average_price or o.entry_price))
            val = qty * price
            
            if o.direction == models.Direction.LONG:
                positions[sym]['long_qty'] += qty
                positions[sym]['long_val'] += val
            else:
                positions[sym]['short_qty'] += qty
                positions[sym]['short_val'] += val
                
        unrealized_pnl = Decimal('0.0')
        missing_cmp = False
        
        for sym, data in positions.items():
            net_qty = data['long_qty'] - data['short_qty']
            if net_qty != 0:
                tick = get_tick(sym)
                if not tick or tick.get("ltp") is None:
                    missing_cmp = True
                    continue
                    
                cmp = Decimal(str(tick["ltp"]))
                if net_qty > 0:
                    avg_entry = data['long_val'] / data['long_qty'] if data['long_qty'] > 0 else Decimal('0.0')
                    unrealized_pnl += net_qty * (cmp - avg_entry)
                else:
                    avg_entry = data['short_val'] / data['short_qty'] if data['short_qty'] > 0 else Decimal('0.0')
                    unrealized_pnl += abs(net_qty) * (avg_entry - cmp)
                    
        return {
            "unrealized_pnl": unrealized_pnl,
            "missing_cmp": missing_cmp
        }

    def _persist_signal(self, signal: Signal) -> int | None:
        """
        Get-or-create the DB Signal row for this signal (keyed by signal_hash).
        Orders link to it via signal_id so the exit monitor can read SL/target.
        """
        existing = self.db.query(models.Signal).filter(models.Signal.signal_hash == signal.signal_hash).first()
        if existing:
            return existing.id

        row = models.Signal(
            strategy_id=signal.strategy_id,
            symbol=signal.symbol,
            direction=models.Direction.LONG if signal.direction == "LONG" else models.Direction.SHORT,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            target_price=signal.target_price,
            signal_hash=signal.signal_hash,
            timestamp=signal.timestamp,
        )
        try:
            self.db.add(row)
            self.db.commit()
            return row.id
        except sqlalchemy.exc.IntegrityError:
            # Concurrent insert of the same signal — reuse the winner's row
            self.db.rollback()
            existing = self.db.query(models.Signal).filter(models.Signal.signal_hash == signal.signal_hash).first()
            return existing.id if existing else None

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
        if not allocations:
            logger.warning(f"No user allocations for strategy_id={signal.strategy_id}; signal {signal.signal_hash} not routed.")
            return executed_orders

        try:
            signal_row_id = self._persist_signal(signal)
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to persist Signal row for {signal.signal_hash}: {e}")
            signal_row_id = None
        if signal_row_id is None:
            logger.error(f"Signal {signal.signal_hash} has no DB row; orders will lack SL/target exits.")

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
                
                if config.EXECUTION_MODE == "live":
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
                    # Block same-direction pyramiding
                    if (current_position > 0 and signal.direction == 'LONG') or (current_position < 0 and signal.direction == 'SHORT'):
                        logger.warning(f"User {user.username} blocked: pyramiding prevention — already {current_position} shares on {signal.symbol}.")
                        continue
                    # Block opposite-direction entry while a position is open on the same symbol
                    # Reason: having simultaneous LONG and SHORT on the same symbol creates undefined P&L
                    # and doubles margin usage. The existing position must close first.
                    if (current_position > 0 and signal.direction == 'SHORT') or (current_position < 0 and signal.direction == 'LONG'):
                        logger.warning(f"User {user.username} blocked: opposite-direction entry prevented — {signal.direction} signal on {signal.symbol} while {current_position} shares open. Wait for position to close first.")
                        continue
                
                # 2.9 Prepare Portfolio Snapshot
                snapshot = self._build_portfolio_snapshot(user.id)
                
                # 3. Execution Gate
                is_approved = RiskGate.validate_risk(
                    db=self.db,
                    user=user,
                    system_settings=system_settings,
                    signal=signal,
                    portfolio_snapshot=snapshot,
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
                    logger.warning(
                        f"RiskGate sized qty=0 for user {user.username} on {signal.symbol}"
                        f" -- skipping order"
                    )
                    continue
                    
                # 5.5 Margin Cache Guardrail
                # Assumes conservative 5x leverage for intraday NSE equity
                estimated_margin_required = (signal.entry_price * Decimal(str(size))) / Decimal('5.0')
                
                # Check for stale margin cache
                current_time = datetime.now(timezone.utc)
                if user.portfolio_metrics:
                    last_sync = user.portfolio_metrics.last_margin_sync
                    if last_sync:
                        if (current_time - last_sync).total_seconds() > 30:
                            logger.warning(f"User {user.username} rejected via Stale Margin Guard: Cache is > 30s old.")
                            sync_dispatch_alert("WARNING", "Stale Margin Cache", f"Blocked execution for {user.username}. Cache delta > 30s.")
                            continue # Added missing continue
                    else:
                        # User-requested honest logging for sandbox bypass
                        logger.info(f"stale-margin guard bypassed for {user.username}: no margin sync exists yet (sandbox mode assumption active)")
                        
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
                    order.strategy_name = signal.strategy_name
                    order.signal_id = signal_row_id
                else:
                    side = models.Direction.LONG if signal.direction == "LONG" else models.Direction.SHORT
                    order = models.Order(
                        user_id=user.id,
                        signal_id=signal_row_id,
                        signal_hash=signal.signal_hash,
                        strategy_name=signal.strategy_name,
                        symbol=signal.symbol,
                        direction=side,
                        quantity=size,
                        entry_price=signal.entry_price,
                        status=models.OrderStatus.NEW,
                        rejection_count=0,
                        signal_timestamp=signal.timestamp
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

    def handle_partial_fill(self, order_id: int, filled_qty: int, fill_price: Decimal, fill_id: str, paper_meta: dict | None = None):
        """
        Called when Dhan WebSockets stream a partial fill.
        In paper mode, also called by OutboxWorker with paper_meta dict.
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
            price=fill_price,
            paper_meta=paper_meta,  # None for live fills, dict for paper fills
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
            
        self.db.commit()

        # Notify an in-process PaperStrategyRunner (fast path). When fills come
        # from the standalone OutboxWorker process there is no runner here; the
        # API's runner picks the fill up from the DB on its periodic resync.
        if order.status == models.OrderStatus.FILLED:
            try:
                from app.engines.paper_strategy_runner import peek_runner
                runner = peek_runner()
                if runner is not None:
                    runner.register_fill(order.id)
            except Exception:
                logger.exception(f"Failed to notify PaperStrategyRunner of fill for order {order_id}")

        logger.info(f"Order {order_id} filled {filled_qty} @ {fill_price}. Avg now {order.average_price:.2f}. Total {order.filled_quantity}/{order.quantity}")

    def close_paper_position(self, order_id: int, exit_price: float, reason: str):
        """
        Dedicated paper-only exit path. 
        Finalizes an open (FILLED) position, calculates realized PnL, and marks as CLOSED.
        """
        order = self.db.query(models.Order).filter(models.Order.id == order_id).with_for_update().first()
        if not order:
            logger.error(f"close_paper_position: Order {order_id} not found.")
            return

        if order.status != models.OrderStatus.FILLED:
            logger.warning(f"close_paper_position: Order {order_id} is in status {order.status}, not FILLED. Ignoring exit.")
            return

        from app.config import config
        from app.broker.paper_broker import _apply_slippage
        from research.utils.fee_calculator import FeeConfig, calculate_charges

        is_long = order.direction == models.Direction.LONG
        ltp_at_exit = Decimal(str(exit_price))
        # Exit pays slippage too (entry already did, in PaperBroker): a LONG
        # exit is a sell and fills below LTP, a SHORT exit is a buy and fills above.
        exit_px = _apply_slippage(ltp_at_exit, "SELL" if is_long else "BUY")
        entry_px = Decimal(str(order.average_price or order.entry_price))
        qty = Decimal(str(order.filled_quantity))

        # 1. Calculate Realized PnL, net of the same charges the backtest uses
        if is_long:
            gross_pnl = (exit_px - entry_px) * qty
        else:
            gross_pnl = (entry_px - exit_px) * qty

        fee_config = FeeConfig()
        entry_charges = calculate_charges(fee_config, "buy" if is_long else "sell", int(qty), float(entry_px))
        exit_charges = calculate_charges(fee_config, "sell" if is_long else "buy", int(qty), float(exit_px))
        charges = Decimal(str(entry_charges["total"])) + Decimal(str(exit_charges["total"]))
        pnl = gross_pnl - charges

        # 2. Update Order
        order.status = models.OrderStatus.CLOSED
        order.exit_price = exit_px
        order.exit_reason = reason
        order.close_requested_at = datetime.now(timezone.utc)
        order.pnl = pnl

        # 3. Create Exit Fill Record
        import uuid
        fill_id = f"exit_{uuid.uuid4().hex[:10]}"
        opened_at = order.created_at
        if opened_at and opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=timezone.utc)
        db_fill = models.TradeFill(
            order_id=order.id,
            fill_id=fill_id,
            quantity=int(qty),
            price=exit_px,
            paper_meta={
                "exit_reason": reason,
                "entry_price": float(entry_px),
                "exit_price": float(exit_px),
                "ltp_at_exit": float(ltp_at_exit),
                "exit_slippage_ticks": config.PAPER_SLIPPAGE_TICKS,
                "gross_pnl": float(gross_pnl),
                "charges": float(charges),
                "entry_charges": entry_charges,
                "exit_charges": exit_charges,
                "net_pnl": float(pnl),
                "holding_time_sec": (order.close_requested_at - opened_at).total_seconds() if opened_at else None,
                "execution_mode": "paper"
            }
        )
        self.db.add(db_fill)

        # 4. Update capital and Portfolio Metrics so sizing and drawdown
        # limits react to realized results
        user = self.db.query(models.User).filter(models.User.id == order.user_id).with_for_update().first()
        user.capital_current = Decimal(str(user.capital_current)) + pnl
        if user.portfolio_metrics:
            metrics = user.portfolio_metrics
            metrics.realized_pnl = Decimal(str(metrics.realized_pnl or 0)) + pnl
            if user.capital_current > Decimal(str(metrics.peak_equity or 0)):
                metrics.peak_equity = user.capital_current

        self.db.commit()
        logger.info(
            f"PAPER EXIT: {order.symbol} {order.direction} closed via {reason} @ {exit_px} (LTP {ltp_at_exit}). "
            f"Gross {gross_pnl:.2f} - charges {charges:.2f} = net {pnl:.2f}. Capital now {user.capital_current:.2f}"
        )
        
        sync_dispatch_alert(
            "INFO", 
            f"Paper Exit: {order.symbol}", 
            f"Position closed via {reason} at {exit_px}. Realized PnL: {pnl:.2f}"
        )
