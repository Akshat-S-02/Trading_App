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
from datetime import datetime, timedelta, timezone, time as dt_time
from typing import Optional

from app.engines.tick_aggregator import TickAggregator
from app.engines.decision_engine import DecisionEngine
from app.engines.execution_engine import ExecutionEngine
from app.db import SessionLocal
from app import models
from sqlalchemy import func
import asyncio
import time
from zoneinfo import ZoneInfo

logger = logging.getLogger("PaperStrategyRunner")
_IST = ZoneInfo("Asia/Kolkata")

# How often the position monitor re-reads FILLED orders from the DB. Fills from
# the standalone OutboxWorker process only reach this runner via that resync.
POSITION_RESYNC_INTERVAL_S = 5.0

# Hard square-off time; no new entries from candles completing at/after it
EOD_CUTOFF = dt_time(15, 20)

# A candle that completes more than this long ago may not produce a signal
STALE_CANDLE_AFTER = timedelta(minutes=10)

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
        self._decision_engine = DecisionEngine(strategy_id=strategy_id)
        self._aggregator = TickAggregator(on_candle=self._on_candle_complete)

        # Active position tracking (In-memory)
        self._active_positions: dict[int, models.Order] = {}
        self._exiting: set[int] = set()
        self._stale_warned: set[str] = set()  # symbols already logged as stale
        self._monitor_task: Optional[asyncio.Task] = None

        # Metrics for get_status()
        self._ticks_received = 0
        self._candles_processed = 0
        self._signals_today = 0
        self._last_signal_time: Optional[datetime] = None

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
        # Paused still builds candles: pause only blocks new signals (see
        # _on_candle_complete), so strategy state stays correct for resume.
        if not self._enabled:
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
        history = self._decision_engine._bar_history.setdefault(symbol, [])
        history.append(candle)
        if len(history) > 100:  # same cap as DecisionEngine.evaluate
            history.pop(0)
        self._decision_engine._orb_adapter.on_candle(symbol, candle, allow_signal=False)
        self._decision_engine._ema_adapter.on_candle(symbol, candle, allow_signal=False)
        self._decision_engine._vwap_adapter.on_candle(symbol, candle, allow_signal=False)
        self._decision_engine._supertrend_adapter.on_candle(symbol, candle, allow_signal=False)

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
            "current_regime": self._decision_engine._last_regime,
            "strategy_weights": self._decision_engine._strategy_weights,
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

    def _load_filled_orders(self) -> Optional[list[models.Order]]:
        """
        Query all FILLED but unclosed orders. Returns None on DB error.
        Not limited to today: a position left over from an earlier session
        must still be monitored so _evaluate_exit can square it off.
        """
        db = SessionLocal()
        try:
            from sqlalchemy.orm import joinedload
            orders = db.query(models.Order).options(
                joinedload(models.Order.signal)
            ).filter(
                models.Order.status == models.OrderStatus.FILLED,
            ).all()
            for o in orders:
                # Expunge so the objects can live in memory without a session
                db.expunge(o)
            return orders
        except Exception:
            logger.exception("Failed to load active positions from DB")
            return None
        finally:
            db.close()

    def _apply_position_sync(self, orders: Optional[list[models.Order]]) -> None:
        """
        Make the in-memory set mirror the DB: picks up fills written by the
        standalone OutboxWorker process and drops positions closed elsewhere.
        Orders mid-exit are skipped so a resync can't re-trigger them.
        """
        if orders is None:
            return
        before = set(self._active_positions)
        self._active_positions = {o.id: o for o in orders if o.id not in self._exiting}
        added = set(self._active_positions) - before
        if added:
            logger.info(f"Sync: Now monitoring {len(added)} new position(s) from DB: {sorted(added)}")

    def _sync_active_positions(self):
        """Load FILLED but unclosed paper orders for the current session from the DB."""
        self._apply_position_sync(self._load_filled_orders())

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
        """
        1-second loop that evaluates exits for all active paper positions.
        Runs while paused too: pause only stops new entries (feed_tick), so
        SL / target / EOD exits keep protecting open manual and auto positions.
        """
        last_sync = 0.0
        while self._enabled:
            try:
                now = time.monotonic()
                if now - last_sync >= POSITION_RESYNC_INTERVAL_S:
                    last_sync = now
                    orders = await asyncio.to_thread(self._load_filled_orders)
                    self._apply_position_sync(orders)
                self._aggregator.flush_session_end()
                await self._monitor_once()
            except Exception:
                logger.exception("Error in position monitor cycle")
            await asyncio.sleep(1)

    async def _monitor_once(self):
        from app.core.tick_store import get_tick, tick_is_live, MAX_TICK_AGE_S

        # Copy to avoid mutation during iteration
        active_ids = list(self._active_positions.keys())
        now_ist = datetime.now(_IST)

        for oid in active_ids:
            order = self._active_positions.get(oid)
            if not order: continue

            # 1. Get latest price
            tick = get_tick(order.symbol)
            if not tick or not tick.get("ltp"): continue

            ltp = float(tick["ltp"])

            # A frozen price (feed down / reconnecting) must not trigger or
            # miss SL / target. Only the EOD square-off still runs, at the last
            # known price, so an intraday position can never carry over.
            if not tick_is_live(tick):
                if order.symbol not in self._stale_warned:
                    self._stale_warned.add(order.symbol)
                    logger.warning(
                        f"[{order.symbol}] No tick in {MAX_TICK_AGE_S}s: SL/target checks "
                        f"paused until prices resume (EOD square-off still active)."
                    )
                reason = self._eod_reason(order, now_ist)
                if reason:
                    await self._trigger_exit(order, ltp, reason)
                continue
            self._stale_warned.discard(order.symbol)
            # 1.5 Calculate Trailing Stop
            trailing_sl = None
            # Only ORB positions trail with ORB's rule; EMA / VWAP / Supertrend /
            # manual trades keep their fixed SL, matching how they were backtested.
            if (order.strategy_name == "orb_v4" and order.signal
                    and order.signal.stop_loss and order.average_price):
                strategy = self._decision_engine._orb_adapter._strategy_for(order.symbol)
                if strategy:
                    order_dt = order.created_at
                    if order_dt and order_dt.tzinfo is None:
                        from datetime import timezone
                        order_dt = order_dt.replace(tzinfo=timezone.utc)
                    
                    history = self._aggregator.get_history(order.symbol)
                    bars_since_entry = [b for b in history if b["timestamp"] >= order_dt]
                    
                    current_bar = {"close": ltp}
                    entry_price = float(order.average_price)
                    original_sl = float(order.signal.stop_loss)
                    # Support LONG only for now per NiftyBreakout v4 limitations
                    initial_risk = entry_price - original_sl
                    
                    try:
                        trailing_sl = strategy.get_trailing_stop(
                            current_bar, bars_since_entry, entry_price, original_sl, initial_risk
                        )
                    except Exception as e:
                        logger.error(f"Error computing trailing stop for {order.symbol}: {e}")
                        trailing_sl = None

            # 2. Check Exit Conditions
            exit_reason = self._evaluate_exit(order, ltp, now_ist, trailing_sl)
            
            if exit_reason:
                await self._trigger_exit(order, ltp, exit_reason)

    def _evaluate_exit(self, order: models.Order, ltp: float, now_ist: datetime, trailing_sl: Optional[float] = None) -> Optional[str]:
        """Stop-Loss, Target, and EOD Square-off checks."""
        # A. Stop Loss
        if order.signal and order.signal.stop_loss:
            sl = float(order.signal.stop_loss)
            
            if trailing_sl is not None:
                if order.direction == models.Direction.LONG and trailing_sl > sl:
                    if sl != trailing_sl:
                        logger.debug(f"[{order.symbol}] Trailing SL active: original={sl} trailing={trailing_sl}")
                    sl = trailing_sl
                elif order.direction == models.Direction.SHORT and trailing_sl < sl:
                    if sl != trailing_sl:
                        logger.debug(f"[{order.symbol}] Trailing SL active: original={sl} trailing={trailing_sl}")
                    sl = trailing_sl

            if order.direction == models.Direction.LONG and ltp <= sl:
                return "SL"
            if order.direction == models.Direction.SHORT and ltp >= sl:
                return "SL"

        # B. Profit Target
        if order.signal and order.signal.target_price:
            tp = float(order.signal.target_price)
            if order.direction == models.Direction.LONG and ltp >= tp:
                return "TARGET"
            if order.direction == models.Direction.SHORT and ltp <= tp:
                return "TARGET"

        return self._eod_reason(order, now_ist)

    @staticmethod
    def _eod_reason(order: models.Order, now_ist: datetime) -> Optional[str]:
        """EOD Square-off: hard close at 15:20 IST, and anything opened on an
        earlier session date — intraday positions must never carry over."""
        if now_ist.time() >= EOD_CUTOFF:
            return "EOD"
        opened_at = order.created_at
        if opened_at is not None:
            if opened_at.tzinfo is None:
                opened_at = opened_at.replace(tzinfo=timezone.utc)
            if opened_at.astimezone(_IST).date() < now_ist.date():
                return "EOD"
        return None

    async def _trigger_exit(self, order: models.Order, exit_price: float, reason: str):
        """Dedicated exit path. Removes from memory and calls ExecutionEngine."""
        logger.info(f"EXIT TRIGGERED: {order.symbol} @ {exit_price} Reason={reason}")
        
        # 1. Remove from in-memory set immediately (Local Idempotency)
        self._exiting.add(order.id)
        self._active_positions.pop(order.id, None)

        # 2. Call Execution Engine for close logic
        db = SessionLocal()
        try:
            # We don't want to rely on the stale 'order' object from memory
            # for DB updates — refetch it.
            engine = ExecutionEngine(db)
            await asyncio.to_thread(engine.close_paper_position, order.id, exit_price, reason)
        except Exception:
            # Order is still FILLED in the DB, so the next resync re-adds it
            # and the exit is retried.
            logger.exception(f"Failed to close paper position {order.id}")
        finally:
            self._exiting.discard(order.id)
            db.close()

    # ------------------------------------------------------------------
    # Internal: Candle → Strategy → Signal → ExecutionEngine
    # ------------------------------------------------------------------

    def _on_candle_complete(self, symbol: str, candle: dict) -> None:
        """
        Callback from TickAggregator when a 5-min candle is finalized.
        """
        # Stale or post-cutoff candles only update strategy state. This covers
        # the previous session's last candle flushed on the next day's first
        # tick, any candle that completes late, and the 15:25 candle (an entry
        # after the EOD cutoff would be squared off immediately).
        now_ist = datetime.now(_IST)
        candle_end = candle["timestamp"] + timedelta(minutes=5)
        if candle_end.tzinfo is None:
            candle_end = candle_end.replace(tzinfo=timezone.utc)
        is_stale = (now_ist - candle_end) > STALE_CANDLE_AFTER
        if is_stale or now_ist.time() >= EOD_CUTOFF or self._paused:
            why = "stale" if is_stale else "paused" if self._paused else "after EOD cutoff"
            logger.info(f"Candle {symbol} {candle['timestamp']} fed as state only ({why}); no signal.")
            self.feed_historical_candle(symbol, candle)
            return

        self._candles_processed += 1

        logger.debug(
            f"Candle complete: {symbol} "
            f"{candle['timestamp']} "
            f"O={candle['open']:.2f} H={candle['high']:.2f} "
            f"L={candle['low']:.2f} C={candle['close']:.2f} "
            f"V={candle['volume']}"
        )

        # Run through the Decision Engine
        app_signal = self._decision_engine.evaluate(symbol, candle)

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


def peek_runner() -> Optional[PaperStrategyRunner]:
    """Return the runner if this process created one, without creating it."""
    return _runner
