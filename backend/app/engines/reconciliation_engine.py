import logging
from sqlalchemy.orm import Session
from sqlalchemy import func
from .. import models
from .strategy_engine import Signal
from decimal import Decimal
from datetime import datetime

logger = logging.getLogger("ReconciliationEngine")

class ReconciliationService:
    """
    The Startup Crash-Healer and Position Synchronizer.
    Runs strictly when the server boots, or periodically, to force PostgreSQL to match reality.
    """
    def __init__(self, db: Session, broker_client):
        self.db = db
        self.broker = broker_client
        
    def run_startup_reconciliation(self):
        logger.info("CRASH HEALER: Beginning Broker Order Reconciliation Sequence")
        # 1. Fetch live truths from the broker
        live_orders = self.broker.get_orders()
        
        # 2. Reconcile Orders
        transit_orders = self.db.query(models.Order).filter(
            models.Order.status.in_([
                models.OrderStatus.NEW, 
                models.OrderStatus.SENDING,
                models.OrderStatus.SUBMITTED, 
                models.OrderStatus.BROKER_ACK,
                models.OrderStatus.PARTIALLY_FILLED
            ])
        ).all()
        
        if not transit_orders:
            logger.info("CRASH HEALER: No transit orders requiring reconciliation.")
            return

        logger.info(f"CRASH HEALER: Found {len(transit_orders)} transit orders in DB. Syncing with Broker...")
        
        broker_order_map = {str(o.get('orderId')): o for o in live_orders} if live_orders else {}
        
        for order in transit_orders:
            broker_state = broker_order_map.get(str(order.id)) 
            
            if broker_state:
                broker_status = broker_state.get('orderStatus')
                broker_filled_qty = int(broker_state.get('filledQty', 0))
                broker_avg_price = Decimal(str(broker_state.get('tradedPrice', 0.0)))
                
                # Force Heal the DB
                if broker_status == "TRADED" or broker_status == "FILLED":
                    old_status = order.status
                    order.status = models.OrderStatus.FILLED
                    order.filled_quantity = broker_filled_qty
                    order.average_price = broker_avg_price
                    logger.warning(f"CRASH HEALER: Force healed Order {order.id} from {old_status} to FILLED. Qty: {broker_filled_qty}")
                    
                elif broker_status == "REJECTED":
                    order.status = models.OrderStatus.REJECTED
                    # Do not map signal_hash to None unconditionally now due to 3-try loop logic, but for crash it's safer
                    order.signal_hash = None 
                    logger.warning(f"CRASH HEALER: Force healed Order {order.id} to REJECTED.")
                    
                elif broker_status == "CANCELLED":
                    order.status = models.OrderStatus.CANCELLED
                    logger.warning(f"CRASH HEALER: Force healed Order {order.id} to CANCELLED.")
                    
            else:
                if order.status == models.OrderStatus.SUBMITTED:
                    # Fix: OrderStatus.FAILED does not exist. Use FAILED_RETRYABLE —
                    # a vanished-in-transit order is a recoverable network/crash event,
                    # not a permanent broker rejection (which would be FAILED_FATAL).
                    order.status = models.OrderStatus.FAILED_RETRYABLE
                    order.signal_hash = None
                    logger.error(f"CRASH HEALER: Order {order.id} vanished in transit. Marked FAILED_RETRYABLE.")

        self.db.commit()
        logger.info("CRASH HEALER: Order Reconciliation Complete.")

    def sync_broker_positions(self, user_id: int):
        """
        Calculates net DB positions based on Filled quantities and diffs them against
        live Broker Net Position. Forces synthetic gap-fills if WebSocket dropped messages.
        """
        logger.info(f"POSITION SYNC: Fetching Live Broker Positions for user {user_id}")
        
        live_positions = self.broker.get_positions()
        
        broker_net = {}
        for pos in live_positions:
            sym = pos.get('tradingSymbol')
            net_qty = int(pos.get('netQty', 0))
            if sym:
                broker_net[sym] = broker_net.get(sym, 0) + net_qty
                
        symbols_in_db = self.db.query(models.Order.symbol).filter(models.Order.user_id == user_id).distinct().all()
        symbols_in_db = [s[0] for s in symbols_in_db]
        
        all_symbols = set(list(broker_net.keys()) + symbols_in_db)
        drift_count = 0
        
        for sym in all_symbols:
            longs = self.db.query(func.sum(models.Order.filled_quantity)).filter(
                models.Order.user_id == user_id,
                models.Order.symbol == sym,
                models.Order.direction == models.Direction.LONG,
                models.Order.status.in_([models.OrderStatus.FILLED, models.OrderStatus.PARTIALLY_FILLED])
            ).scalar() or 0
            
            shorts = self.db.query(func.sum(models.Order.filled_quantity)).filter(
                models.Order.user_id == user_id,
                models.Order.symbol == sym,
                models.Order.direction == models.Direction.SHORT,
                models.Order.status.in_([models.OrderStatus.FILLED, models.OrderStatus.PARTIALLY_FILLED])
            ).scalar() or 0
            
            db_net = int(longs) - int(shorts)
            br_net = broker_net.get(sym, 0)
            
            if db_net != br_net:
                logger.error(f"POSITION DRIFT DETECTED for {sym}. DB: {db_net}, Broker: {br_net}. Initiating Hard Heal.")
                qty_diff = br_net - db_net
                
                direction = models.Direction.LONG if qty_diff > 0 else models.Direction.SHORT
                abs_qty = abs(qty_diff)
                
                synthetic_order = models.Order(
                    user_id=user_id,
                    signal_hash=f"HEAL_{sym}_{int(datetime.now().timestamp())}",
                    symbol=sym,
                    direction=direction,
                    quantity=abs_qty,
                    entry_price=Decimal('0.0'),
                    filled_quantity=abs_qty,
                    average_price=Decimal('0.0'),
                    status=models.OrderStatus.FILLED,
                    rejection_count=0
                )
                self.db.add(synthetic_order)
                logger.warning(f"POSITION SYNC: Injected synthetic {direction.value} for {abs_qty} {sym} to sync with broker.")
                drift_count += 1
                
        if drift_count > 0:
            self.db.commit()
            logger.warning(f"POSITION SYNC: Successfully healed {drift_count} discrepant symbols.")
        else:
            logger.info("POSITION SYNC: Zero drift. DB matches Broker perfectly.")
