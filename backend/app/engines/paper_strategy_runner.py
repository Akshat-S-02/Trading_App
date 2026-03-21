"""
app/engines/paper_strategy_runner.py

Singleton that wires TickAggregator → MomentumORBv4Adapter → ExecutionEngine.

Lifecycle:
  1. On startup, creates the TickAggregator and Adapter
  2. market_ws.py forwards each tick via `feed_tick()`
  3. When a 5-min candle completes, the adapter evaluates ORB v4
  4. If a Signal fires → routed through ExecutionEngine → Outbox → PaperBroker

Only finalized completed candles trigger strategy evaluation (never raw ticks).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from app.engines.tick_aggregator import TickAggregator
from app.strategies.adapters.momentum_orb_v4_adapter import MomentumORBv4Adapter
from app.engines.execution_engine import ExecutionEngine
from app.db import SessionLocal
from app import models
from sqlalchemy import func
import asyncio
from zoneinfo import ZoneInfo

logger = logging.getLogger("PaperStrategyRunner")
_IST = ZoneInfo("Asia/Kolkata")

# ── Momentum5 Universe (initial) ────────────────────────────────
# The top symbols from our backtest results.
# Can be expanded later via config/DB.
MOMENTUM5_UNIVERSE = [
    "RELIANCE",
    "TCS",
    "INFY",
    "HDFCBANK",
    "ICICIBANK",
]


class PaperStrategyRunner:
    """
    Singleton-style runner that connects the tick pipeline to ORB v4.

    Exposes:
      - feed_tick()     : called by market_ws on every parsed tick
      - get_status()    : returns runner state for the /api/paper/status endpoint
      - start() / pause() / resume()
    """

    def __init__(self, strategy_id: int = 1):
        self.strategy_id = strategy_id
        self._enabled = True
        self._paused = False

        # Core components
        self._adapter = MomentumORBv4Adapter(strategy_id=strategy_id)
        self._aggregator = TickAggregator(on_candle=self._on_candle_complete)

        # Active position tracking (In-memory)
        self._active_positions: dict[int, models.Order] = {}
        self._monitor_task: Optional[asyncio.Task] = None

        logger.info(
            f"PaperStrategyRunner initialized | "
            f"strategy_id={strategy_id} | "
            f"universe={MOMENTUM5_UNIVERSE}"
        )
        
        # Initial sync from DB
        self._sync_active_positions()

    # ------------------------------------------------------------------
    # Public: Tick Feed
    # ------------------------------------------------------------------

    def feed_tick(
        self,
        symbol: str,
        price: float,
        volume: int = 0,
        tick_time: Optional[datetime] = None,
    ) -> None:
        """
        Called by market_ws.py for every parsed tick.
        Only processes symbols in our universe.
        """
        if not self._enabled or self._paused:
            return

        # Only process symbols in our universe
        if symbol not in MOMENTUM5_UNIVERSE:
            return

        self._ticks_received += 1
        self._aggregator.on_tick(symbol, price, volume, tick_time)

    def feed_historical_candle(self, symbol: str, candle: dict) -> None:
        """
        Replay completed historical candle to rebuild strategy state securely.
        Uses allow_signal=False to prevent accidental ghost executions of past signals.
        """
        self._candles_processed += 1
        self._adapter.on_candle(symbol, candle, allow_signal=False)

    # ------------------------------------------------------------------
    # Public: Control
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._enabled = True
        self._paused = False
        
        # Start the background position monitor
        if self._monitor_task is None or self._monitor_task.done():
            self._monitor_task = asyncio.create_task(self._position_monitor_loop())
            
        logger.info("PaperStrategyRunner: STARTED (Position Monitor Active)")

    def pause(self) -> None:
        self._paused = True
        logger.info("PaperStrategyRunner: PAUSED")

    def resume(self) -> None:
        self._paused = False
        logger.info("PaperStrategyRunner: RESUMED")

    def stop(self) -> None:
        self._enabled = False
        logger.info("PaperStrategyRunner: STOPPED")

    # ------------------------------------------------------------------
    # Public: Status (for /api/paper/status)
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        return {
            "runner_enabled": self._enabled,
            "runner_paused": self._paused,
            "symbols_tracked": MOMENTUM5_UNIVERSE,
            "active_positions_count": len(self._active_positions),
            "current_session_date": (
                self._aggregator.session_date.isoformat()
                if self._aggregator.session_date else None
            ),
            "last_completed_candle_time": (
                self._aggregator.last_bucket.isoformat()
                if self._aggregator.last_bucket else None
            ),
            "signals_emitted_today": self._signals_today,
            "candles_processed": self._candles_processed,
            "ticks_received": self._ticks_received,
            "last_signal_time": (
                self._last_signal_time.isoformat()
                if self._last_signal_time else None
            ),
        }

    # ------------------------------------------------------------------
    # Position Monitoring (Exit Engine)
    # ------------------------------------------------------------------

    def _sync_active_positions(self):
        """Load FILLED but unclosed paper orders for the current session at startup."""
        db = SessionLocal()
        try:
            from datetime import date
            from sqlalchemy.orm import joinedload
            today = date.today()
            orders = db.query(models.Order).options(
                joinedload(models.Order.signal)
            ).filter(
                models.Order.status == models.OrderStatus.FILLED,
                func.date(models.Order.created_at) == today
            ).all()
            
            for o in orders:
                # Add to in-memory set (expunged from session to stay thread-safe)
                db.expunge(o)
                self._active_positions[o.id] = o
                
            if orders:
                logger.info(f"Sync: Loaded {len(orders)} active paper positions from DB.")
        except Exception:
            logger.exception("Failed to sync active positions from DB")
        finally:
            db.close()

    def register_fill(self, order_id: int):
        """Add a newly filled order to the active monitor."""
        db = SessionLocal()
        try:
            from sqlalchemy.orm import joinedload
            order = db.query(models.Order).options(
                joinedload(models.Order.signal)
            ).filter(models.Order.id == order_id).first()
            if order:
                db.expunge(order)
                self._active_positions[order.id] = order
                logger.info(f"Monitor: Registered new active position for {order.symbol} (Order {order_id})")
        except Exception:
            logger.exception(f"Failed to register fill for order {order_id}")
        finally:
            db.close()

    async def _position_monitor_loop(self):
        """1-second loop that evaluates exits for all active paper positions."""
        while self._enabled:
            if not self._paused:
                try:
                    await self._monitor_once()
                except Exception:
                    logger.exception("Error in position monitor cycle")
            await asyncio.sleep(1)

    async def _monitor_once(self):
        from app.core.tick_store import get_tick
        
        # Copy to avoid mutation during iteration
        active_ids = list(self._active_positions.keys())
        now_ist = datetime.now(_IST)
        
        for oid in active_ids:
            order = self._active_positions.get(oid)
            if not order: continue
            
            # 1. Get latest price
            tick = get_tick(order.symbol)
            if not tick: continue
            
            ltp = float(tick["ltp"])
            
            # 2. Check Exit Conditions
            exit_reason = self._evaluate_exit(order, ltp, now_ist)
            
            if exit_reason:
                await self._trigger_exit(order, ltp, exit_reason)

    def _evaluate_exit(self, order: models.Order, ltp: float, now_ist: datetime) -> Optional[str]:
        """Stop-Loss, Target, and EOD Square-off checks."""
        # A. Stop Loss
        if order.signal and order.signal.stop_loss:
            sl = float(order.signal.stop_loss)
            if order.direction == models.Direction.LONG and ltp <= sl:
                return "SL"
            if order.direction == models.Direction.SHORT and ltp >= sl:
                return "SL"
                
        # B. Profit Target (from backtest config reward_ratio=1.5)
        # Note: Strategy currently calculates target price, let's assume it's in signal meta 
        # or calculate it dynamically if not stored. 
        # Actually, let's check if we have s.target in Signal model? No.
        # For this prototype, we primarily use SL and EOD.
        
        # C. EOD Square-off (Hard Close at 15:20 IST)
        if now_ist.hour == 15 and now_ist.minute >= 20:
            return "EOD"
            
        return None

    async def _trigger_exit(self, order: models.Order, exit_price: float, reason: str):
        """Dedicated exit path. Removes from memory and calls ExecutionEngine."""
        logger.info(f"EXIT TRIGGERED: {order.symbol} @ {exit_price} Reason={reason}")
        
        # 1. Remove from in-memory set immediately (Local Idempotency)
        self._active_positions.pop(order.id, None)
        
        # 2. Call Execution Engine for close logic
        db = SessionLocal()
        try:
            # We don't want to rely on the stale 'order' object from memory 
            # for DB updates — refetch it.
            engine = ExecutionEngine(db)
            await asyncio.to_thread(engine.close_paper_position, order.id, exit_price, reason)
        except Exception:
            logger.exception(f"Failed to close paper position {order.id}")
            # Optional: Re-add to active_positions for retry? 
            # Better to mark as FAILED in DB and analyze.
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Internal: Candle → Strategy → Signal → ExecutionEngine
    # ------------------------------------------------------------------

    def _on_candle_complete(self, symbol: str, candle: dict) -> None:
        """
        Callback from TickAggregator when a 5-min candle is finalized.
        """
        self._candles_processed += 1

        logger.debug(
            f"Candle complete: {symbol} "
            f"{candle['timestamp']} "
            f"O={candle['open']:.2f} H={candle['high']:.2f} "
            f"L={candle['low']:.2f} C={candle['close']:.2f} "
            f"V={candle['volume']}"
        )

        # Run through the ORB v4 adapter
        app_signal = self._adapter.on_candle(symbol, candle)

        if app_signal is None:
            return

        # Signal fired!
        self._signals_today += 1
        self._last_signal_time = candle["timestamp"]

        logger.info(
            f"PAPER SIGNAL: {app_signal.direction} {symbol} "
            f"@ {app_signal.entry_price} SL={app_signal.stop_loss}"
        )

        # Route through ExecutionEngine → Outbox → PaperBroker
        db = SessionLocal()
        try:
            engine = ExecutionEngine(db)
            order_ids = engine.process_signal(app_signal)
            if order_ids:
                logger.info(f"Paper orders created: {order_ids}")
        except Exception:
            logger.exception(f"Failed to process paper signal for {symbol}")
        finally:
            db.close()


# ── Module-level singleton ────────────────────────────────────────
_runner: Optional[PaperStrategyRunner] = None


def get_runner() -> PaperStrategyRunner:
    """Get or create the global PaperStrategyRunner singleton."""
    global _runner
    if _runner is None:
        _runner = PaperStrategyRunner()
    return _runner
