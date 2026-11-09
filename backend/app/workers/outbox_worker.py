import sys
import os
import uuid
import time
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session

# Add the parent directory so we can import 'app'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from app.db import SessionLocal
from app.models import OutboxEvent, OutboxEventStatus, Order, OrderStatus
from app.services import dhan_service
from app.broker.paper_broker import place_order as paper_place_order
from app.engines.execution_engine import ExecutionEngine
from app.core.alerts import sync_dispatch_alert
from app.config import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("OutboxWorker")

# Order states in which nothing has reached the broker yet, so sending is allowed.
SENDABLE = {OrderStatus.NEW, OrderStatus.ENQUEUED, OrderStatus.SENDING}
MAX_RETRIES = 3
STUCK_AFTER_S = 60


class OutboxWorker:
    def __init__(self, db: Session):
        self.db = db
        self.worker_id = f"outbox_worker_{uuid.uuid4().hex[:8]}"
        self.engine = ExecutionEngine(self.db)

    def requeue_interrupted(self) -> int:
        """
        A worker killed mid-send (deploy restart, crash) leaves its event in
        PROCESSING forever, and the order stays NEW, blocking the symbol and
        the open-position slot. Run at startup: requeue events whose order was
        never sent; close out those whose order already moved on (e.g. the
        paper fill committed just before the crash), so nothing is sent twice.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=STUCK_AFTER_S)
        stuck = self.db.query(OutboxEvent).filter(
            OutboxEvent.status == OutboxEventStatus.PROCESSING,
            (OutboxEvent.locked_at == None) | (OutboxEvent.locked_at < cutoff),  # noqa: E711
        ).with_for_update(skip_locked=True).all()
        for event in stuck:
            order = self.db.query(Order).filter(Order.id == event.order_id).first()
            if order and order.status in SENDABLE:
                event.status = OutboxEventStatus.PENDING
                # Counts as an attempt: in live mode a retry looks the order up
                # at Dhan before sending (it may have gone out before the crash).
                event.retry_count += 1
                event.next_attempt_at = datetime.now(timezone.utc)
                logger.warning(f"[{self.worker_id}] Requeued interrupted event {event.id} (order {event.order_id})")
            else:
                event.status = OutboxEventStatus.COMPLETED
                logger.warning(f"[{self.worker_id}] Closed interrupted event {event.id}: order already "
                               f"{order.status.value if order else 'missing'}")
        self.db.commit()
        return len(stuck)

    def process_pending_events(self):
        """
        Claims one PENDING event (FOR UPDATE SKIP LOCKED, so concurrent workers
        never take the same one) and sends it to the paper or live broker.
        """
        now = datetime.now(timezone.utc)
        event = self.db.query(OutboxEvent).filter(
            OutboxEvent.status == OutboxEventStatus.PENDING,
            OutboxEvent.next_attempt_at <= now
        ).order_by(OutboxEvent.created_at.asc()).with_for_update(skip_locked=True).first()

        if not event:
            return False

        logger.info(f"[{self.worker_id}] Claimed OutboxEvent {event.id} for Order {event.order_id}")
        event.status = OutboxEventStatus.PROCESSING
        event.locked_at = now
        self.db.commit()

        payload = event.payload
        symbol = payload.get("symbol")
        qty = payload.get("qty")
        direction = payload.get("direction")
        price = payload.get("price")
        order_type = payload.get("order_type")
        correlation_id = payload.get("correlation_id")

        order = self.db.query(Order).filter(Order.id == event.order_id).first()
        mode = config.EXECUTION_MODE.lower()

        try:
            if order is not None and order.status not in SENDABLE:
                logger.warning(f"[{self.worker_id}] Order {order.id} is {order.status.value}; not sending again.")
                event.status = OutboxEventStatus.COMPLETED
                return True

            if mode == "sandbox":
                logger.info(f"[{self.worker_id}] SANDBOX mode: skipping execution for {qty}x {symbol}")
                event.status = OutboxEventStatus.COMPLETED
                if order:
                    order.status = OrderStatus.SUBMITTED
                    order.broker_order_id = f"SANDBOX_{correlation_id or 'NOOP'}"
                return True

            if mode == "paper":
                logger.info(f"[{self.worker_id}] PAPER mode: simulating fill for {qty}x {symbol} | CorrId: {correlation_id}")
                resp = paper_place_order(symbol=symbol, qty=qty, direction=direction, price=price,
                                         order_type=order_type, correlation_id=correlation_id)
            else:
                resp = self._send_live(event, symbol, qty, direction, price, order_type, correlation_id)
                if resp is None:  # could not confirm whether it went out: retry later, don't resend blind
                    self._schedule_retry(event)
                    return True

            if resp.get("status") == "success":
                broker_id = resp.get("order_id")
                event.status = OutboxEventStatus.COMPLETED
                if order:
                    order.status = OrderStatus.SUBMITTED
                    order.broker_order_id = broker_id

                # Paper has no order-update stream: complete SUBMITTED -> FILLED here.
                # Live fills arrive via Dhan's order updates.
                if mode == "paper" and order:
                    paper_meta = resp.get("paper_meta", {})
                    fill_price_val = paper_meta.get("fill_price", price)
                    paper_meta["signal_price"] = price
                    paper_meta["execution_mode"] = "paper"
                    self.engine.handle_partial_fill(
                        order_id=order.id,
                        filled_qty=qty,
                        fill_price=Decimal(str(fill_price_val)),
                        fill_id=broker_id,
                        paper_meta=paper_meta,
                    )
                    logger.info(
                        f"[{self.worker_id}] PAPER FILL complete: {qty}x {symbol} @ {fill_price_val} "
                        f"| slippage={paper_meta.get('slippage_ticks')} ticks "
                        f"| latency={paper_meta.get('latency_ms', 0):.0f}ms"
                    )
                    side = "BUY" if direction == "LONG" else "SELL"
                    sync_dispatch_alert("INFO", f"Paper Entry: {symbol}",
                                        f"{side} {qty} @ {float(fill_price_val):.2f} "
                                        f"({order.strategy_name or 'auto'})")
                else:
                    logger.info(f"[{self.worker_id}] SUCCESS. Broker ID: {broker_id}")
            else:
                error_msg = resp.get("error", "Unknown API error")
                logger.warning(f"[{self.worker_id}] Broker Refusal: {error_msg}")
                if order:
                    self.engine.handle_broker_rejection(order.id, error_msg)
                order = self.db.query(Order).filter(Order.id == event.order_id).first()
                if order and order.status == OrderStatus.REJECTED:
                    event.status = OutboxEventStatus.FAILED
                else:
                    self._schedule_retry(event)

        except Exception as e:
            logger.error(f"[{self.worker_id}] Outbox Execution CRASH: {e}")
            try:
                self.db.rollback()
                self._schedule_retry(event)
            except Exception as retry_err:
                logger.error(f"[{self.worker_id}] FATAL: Failed to schedule retry for Event {event.id}: {retry_err}")

        finally:
            self.db.commit()

        return True

    def _send_live(self, event, symbol, qty, direction, price, order_type, correlation_id) -> dict | None:
        """
        Live send that never duplicates: on any retry, first ask Dhan whether an
        order with this correlation id already exists (a timed-out request may
        still have been accepted). Returns None when that can't be determined.
        """
        if event.retry_count > 0 and correlation_id:
            try:
                existing = dhan_service.find_order_by_correlation(correlation_id)
            except Exception as e:
                logger.error(f"[{self.worker_id}] Order lookup for {correlation_id} failed: {e}; will retry.")
                return None
            if existing:
                logger.warning(f"[{self.worker_id}] {correlation_id} already at Dhan as {existing.get('orderId')}; not resending.")
                return {"status": "success", "order_id": existing.get("orderId")}

        logger.info(f"[{self.worker_id}] LIVE mode: dispatching to Dhan for {qty}x {symbol} | CorrId: {correlation_id}")
        resp = dhan_service.place_order(symbol=symbol, qty=qty, direction=direction, price=price,
                                        order_type=order_type, correlation_id=correlation_id)
        if resp.get("status") == "unknown":
            logger.error(f"[{self.worker_id}] {resp.get('error')}; will look up {correlation_id} before any resend.")
            return None
        return resp

    def _schedule_retry(self, event: OutboxEvent):
        """Exponential backoff: 2s, 4s, 8s, then give up."""
        event.retry_count += 1
        if event.retry_count > MAX_RETRIES:
            logger.error(f"[{self.worker_id}] OutboxEvent {event.id} permanently failed after {MAX_RETRIES} retries.")
            event.status = OutboxEventStatus.FAILED
            order = self.db.query(Order).filter(Order.id == event.order_id).first()
            if order:
                order.status = OrderStatus.FAILED_FATAL
            if config.EXECUTION_MODE.lower() == "live":
                sync_dispatch_alert("CRITICAL", "Order state unknown",
                                    f"Order {event.order_id} gave up after {MAX_RETRIES} retries. "
                                    f"Check Dhan for correlation id {event.payload.get('correlation_id')}.")
        else:
            delay = 2 ** event.retry_count
            event.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
            event.status = OutboxEventStatus.PENDING
            logger.info(f"[{self.worker_id}] Scheduled Retry #{event.retry_count} for Event {event.id} in {delay}s")


def run_worker():
    db = SessionLocal()
    worker = OutboxWorker(db)
    logger.info(f"[{worker.worker_id}] Starting Outbox Daemon Polling...")
    try:
        worker.requeue_interrupted()
    except Exception:
        logger.exception("Startup requeue of interrupted events failed")
        db.rollback()

    try:
        while True:
            try:
                acted = worker.process_pending_events()
            except Exception:
                # A DB blip must not kill the daemon; reset the session and keep polling.
                logger.exception(f"[{worker.worker_id}] Poll cycle failed")
                db.rollback()
                acted = False
            if not acted:
                time.sleep(1.0)
    except KeyboardInterrupt:
        logger.info(f"[{worker.worker_id}] Shutting down Outbox Worker gracefully.")
    finally:
        db.close()


if __name__ == "__main__":
    run_worker()
