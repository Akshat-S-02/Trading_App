import sys
import os
import uuid
import time
import logging
from datetime import datetime, timezone
import sqlalchemy
from sqlalchemy.orm import Session
from sqlalchemy import func

# Add the parent directory so we can import 'app'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from app.db import SessionLocal
from app.models import OutboxEvent, OutboxEventStatus, Order, OrderStatus, User
from app.services.dhan_service import place_order as dhan_place_order
from app.broker.paper_broker import place_order as paper_place_order
from app.engines.execution_engine import ExecutionEngine
from app.config import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("OutboxWorker")

class OutboxWorker:
    def __init__(self, db: Session):
        self.db = db
        self.worker_id = f"outbox_worker_{uuid.uuid4().hex[:8]}"
        self.engine = ExecutionEngine(self.db)
        
    def process_pending_events(self):
        """
        Polls the OutboxEvent table for PENDING messages.
        Uses FOR UPDATE SKIP LOCKED to prevent concurrent workers from claiming the same event.
        """
        now = datetime.now(timezone.utc)
        
        # 1. Fetch exactly 1 pending event that is eligible for retry
        event = self.db.query(OutboxEvent).filter(
            OutboxEvent.status == OutboxEventStatus.PENDING,
            OutboxEvent.next_attempt_at <= now
        ).order_by(
            OutboxEvent.created_at.asc()
        ).with_for_update(skip_locked=True).first()
        
        if not event:
            return False # No work to do
            
        logger.info(f"[{self.worker_id}] Claimed OutboxEvent {event.id} for Order {event.order_id}")
        
        # 2. Mark as processing to track crashes intrinsically
        event.status = OutboxEventStatus.PROCESSING
        event.locked_at = now
        self.db.commit()
        
        # Extract payload
        payload = event.payload
        symbol = payload.get("symbol")
        qty = payload.get("qty")
        direction = payload.get("direction")
        price = payload.get("price")
        order_type = payload.get("order_type")
        correlation_id = payload.get("correlation_id")
        
        order = self.db.query(Order).filter(Order.id == event.order_id).first()
        
        try:
            # 3. Route based on EXECUTION_MODE
            mode = config.EXECUTION_MODE.lower()
            
            if mode == "sandbox":
                # Sandbox = UI only, skip execution entirely
                logger.info(f"[{self.worker_id}] SANDBOX mode: skipping execution for {qty}x {symbol}")
                event.status = OutboxEventStatus.COMPLETED
                if order:
                    order.status = OrderStatus.SUBMITTED
                    order.broker_order_id = f"SANDBOX_{correlation_id or 'NOOP'}"
                self.db.commit()
                return True
            
            elif mode == "paper":
                logger.info(f"[{self.worker_id}] PAPER mode: simulating fill for {qty}x {symbol} | CorrId: {correlation_id}")
                resp = paper_place_order(
                    symbol=symbol,
                    qty=qty,
                    direction=direction,
                    price=price,
                    order_type=order_type,
                    correlation_id=correlation_id,
                )
            
            else:
                # Live mode — real Dhan REST API
                logger.info(f"[{self.worker_id}] LIVE mode: dispatching to Dhan for {qty}x {symbol} | CorrId: {correlation_id}")
                resp = dhan_place_order(
                    symbol=symbol,
                    qty=qty,
                    direction=direction,
                    price=price,
                    order_type=order_type,
                    correlation_id=correlation_id,
                )
            
            if resp.get("status") == "success":
                # 4a. Success Path
                broker_id = resp.get("order_id")
                event.status = OutboxEventStatus.COMPLETED
                
                if order:
                    order.status = OrderStatus.SUBMITTED
                    order.broker_order_id = broker_id
                
                # 4a.1 PAPER MODE: Immediately process fill
                # In live mode, fills arrive via Dhan WebSocket.
                # In paper mode, there is no WS — so we complete the
                # full lifecycle (SUBMITTED → FILLED) right here.
                if mode == "paper" and order:
                    paper_meta = resp.get("paper_meta", {})
                    fill_price_val = paper_meta.get("fill_price", price)

                    # Enrich paper_meta with signal-level context
                    paper_meta["signal_price"] = price
                    paper_meta["execution_mode"] = "paper"

                    from decimal import Decimal
                    self.engine.handle_partial_fill(
                        order_id=order.id,
                        filled_qty=qty,
                        fill_price=Decimal(str(fill_price_val)),
                        fill_id=broker_id,
                        paper_meta=paper_meta,
                    )
                    logger.info(
                        f"[{self.worker_id}] PAPER FILL complete: "
                        f"{qty}x {symbol} @ {fill_price_val} "
                        f"| slippage={paper_meta.get('slippage_ticks')} ticks "
                        f"| latency={paper_meta.get('latency_ms', 0):.0f}ms"
                    )
                else:
                    logger.info(f"[{self.worker_id}] SUCCESS. Broker ID: {broker_id}")
            else:
                # 4b. Broker Rejection Path (e.g. Insufficient margin from exchange)
                error_msg = resp.get("error", "Unknown API error")
                logger.warning(f"[{self.worker_id}] Broker Refusal: {error_msg}")
                
                if order:
                    self.engine.handle_broker_rejection(order.id, error_msg)
                    
                # Re-fetch order status since engine modified it
                order = self.db.query(Order).filter(Order.id == event.order_id).first()
                if order and order.status == OrderStatus.REJECTED:
                    # Automation was potentially killed inside the engine loop, hard-kill event
                    event.status = OutboxEventStatus.FAILED
                else:
                    self._schedule_retry(event)
                    
        except Exception as e:
            # 4c. Structural Crash Path (e.g. network timeout, 500 error, DB constraint)
            logger.error(f"[{self.worker_id}] Outbox Execution CRASH: {e}")
            try:
                self.db.rollback()
                self._schedule_retry(event)
            except Exception as retry_err:
                logger.error(f"[{self.worker_id}] FATAL: Failed to schedule retry for Event {event.id}: {retry_err}")
            
        finally:
            self.db.commit()
            
        return True
        
    def _schedule_retry(self, event: OutboxEvent):
        """ Exponential Backoff Logic """
        event.retry_count += 1
        
        if event.retry_count > 3:
            logger.error(f"[{self.worker_id}] OutboxEvent {event.id} permanently failed after 3 retries.")
            event.status = OutboxEventStatus.FAILED
            # Update order as definitively failed if bound
            order = self.db.query(Order).filter(Order.id == event.order_id).first()
            if order:
                order.status = OrderStatus.FAILED_FATAL
        else:
            # Wait 2^retries seconds: backoff 2s, 4s, 8s...
            delay = 2 ** event.retry_count 
            event.next_attempt_at = datetime.now(timezone.utc) + sqlalchemy.text(f"interval '{delay} seconds'")
            event.status = OutboxEventStatus.PENDING
            logger.info(f"[{self.worker_id}] Scheduled Retry #{event.retry_count} for Event {event.id} in {delay}s")

def run_worker():
    db = SessionLocal()
    worker = OutboxWorker(db)
    
    logger.info(f"[{worker.worker_id}] Starting Outbox Daemon Polling...")
    try:
        while True:
            acted = worker.process_pending_events()
            if not acted:
                time.sleep(1.0) # Poll every 1 second if queue is empty
    except KeyboardInterrupt:
        logger.info(f"[{worker.worker_id}] Shutting down Outbox Worker gracefully.")
    except Exception as e:
        logger.error(f"[{worker.worker_id}] Global Crash: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_worker()
