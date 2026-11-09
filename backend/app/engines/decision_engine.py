"""
app/engines/decision_engine.py

Decision Engine: Acts as the brain of the routing system.
Aggregates signals, classifies regimes, applies EV filtering, and scores confidence.
"""

from __future__ import annotations

import logging
from typing import Optional, Dict, List
import json
import os

# SQLAlchemy imports for EV filter
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Order, OrderStatus
from app.engines.strategy_engine import Signal as AppSignal

from app.strategies.adapters.research_adapters import (
    EMAMomentumAdapter, MomentumORBv4Adapter, SupertrendAdapter, VWAPReversionAdapter,
)
from research.strategies.volatility_regime import RegimeClassifier

logger = logging.getLogger("DecisionEngine")

ALLOW_SHORT_SIGNALS = False  # automated shorts off until backtested; manual shorts unaffected


class DecisionEngine:
    def __init__(self, strategy_id: int):
        self.strategy_id = strategy_id
        
        self._orb_adapter = MomentumORBv4Adapter(strategy_id)
        self._ema_adapter = EMAMomentumAdapter(strategy_id)
        self._vwap_adapter = VWAPReversionAdapter(strategy_id)
        self._supertrend_adapter = SupertrendAdapter(strategy_id)
        
        # We don't instantiate the classifier since its methods are classmethods
        self._regime_classifier = RegimeClassifier
        
        self._strategy_weights: Dict[str, float] = {
            "orb_v4": 1.0, 
            "ema_momentum": 1.0,
            "vwap_reversion": 1.0,
            "supertrend": 1.0
        }
        
        self._weights_file = os.path.join(os.path.dirname(__file__), '../../strategy_weights.json')
        
        self._load_state()

        self._bar_history: Dict[str, list[dict]] = {}
        self._last_regime: Dict[str, str] = {}

    def evaluate(self, symbol: str, candle: dict) -> Optional[AppSignal]:
        """
        Evaluate a completed candle against active strategies, filter by regime and EV.
        """
        if symbol not in self._bar_history:
            self._bar_history[symbol] = []
            
        history = self._bar_history[symbol]
        
        # Ensure timestamp, close, high, low, volume are present
        bar = {
            "timestamp": candle["timestamp"],
            "open": float(candle["open"]),
            "high": float(candle["high"]),
            "low": float(candle["low"]),
            "close": float(candle["close"]),
            "volume": int(candle.get("volume", 0)),
        }
        
        history.append(bar)
        if len(history) > 100:
            history.pop(0)
            
        # 1. Classify Regime
        regime_data = self._regime_classifier.classify(history)
        if not regime_data:
            self._last_regime[symbol] = "INSUFFICIENT_DATA"
            # Not enough data (needs 20 bars)
            self._orb_adapter.on_candle(symbol, candle, allow_signal=False)
            self._ema_adapter.on_candle(symbol, candle, allow_signal=False)
            self._vwap_adapter.on_candle(symbol, candle, allow_signal=False)
            self._supertrend_adapter.on_candle(symbol, candle, allow_signal=False)
            return None
            
        regime = regime_data["regime"]
        trend = regime_data["trend"]
        allowed_strategies = self._regime_classifier.STRATEGY_MATRIX.get((regime, trend), [])
        
        self._last_regime[symbol] = f"{regime.value} + {trend}"
        
        # 2. Collect Signals
        adapter_map = {
            "orb_v4": self._orb_adapter,
            "ema_momentum": self._ema_adapter,
            "vwap_reversion": self._vwap_adapter,
            "supertrend": self._supertrend_adapter
        }
        
        # Every strategy sees every candle so its state (opening range, VWAP,
        # EMAs) has no gaps; the regime only decides which may signal.
        signals: List[AppSignal] = []
        for strategy_name, adapter in adapter_map.items():
            sig = adapter.on_candle(symbol, candle, allow_signal=strategy_name in allowed_strategies)
            if sig:
                signals.append(sig)
            
        # Shorts (Supertrend, VWAP) were never backtested: the engine dropped them
        # until 2026-11-09. Flip ALLOW_SHORT_SIGNALS once their backtest holds up.
        if not ALLOW_SHORT_SIGNALS:
            for s in [s for s in signals if s.direction == "SHORT"]:
                logger.info(f"DecisionEngine: dropped SHORT {s.strategy_name} signal on {symbol}: shorts disabled")
            signals = [s for s in signals if s.direction != "SHORT"]

        # Weight 0 = disabled by the nightly job. Without this a lone signal from a
        # "disabled" strategy still won, because weight only broke ties.
        disabled = [s for s in signals if self._strategy_weights.get(s.strategy_name, 1.0) <= 0]
        for s in disabled:
            logger.warning(f"DecisionEngine: dropped {s.strategy_name} signal on {symbol}: strategy disabled (weight 0)")
        signals = [s for s in signals if s not in disabled]
        if not signals:
            return None
            
        # 3. Apply EV Filter
        valid_signals = []
        with SessionLocal() as db:
            for sig in signals:
                if self._passes_ev_filter(symbol, sig.strategy_name, db):
                    valid_signals.append(sig)
                    
        if not valid_signals:
            return None
            
        # 4. Score and Pick Best Signal
        winner: Optional[AppSignal] = None
        
        if len(valid_signals) == 1:
            winner = valid_signals[0]
        else:
            # Simple scoring: confidence * weight (assuming base confidence=1.0 for now)
            # If signals had a 'confidence' attribute, we'd use it here.
            best_score = -1.0
            for sig in valid_signals:
                weight = self._strategy_weights.get(sig.strategy_name, 1.0)
                score = 1.0 * weight  # 1.0 is default confidence
                if score > best_score:
                    best_score = score
                    winner = sig
                    
        if winner:
            logger.info(
                f"DecisionEngine: regime={regime.value} trend={trend} "
                f"allowed={allowed_strategies} signals={len(signals)} "
                f"winner={winner.strategy_name}"
            )
            
        return winner

    def _passes_ev_filter(self, symbol: str, strategy_name: str, db: Session) -> bool:
        """
        Calculates EV for the strategy on this symbol using the last 30 closed trades.
        Blocks signal if EV < 0.
        """
        # Query last 30 CLOSED orders for this strategy+symbol
        stmt = (
            select(Order)
            .where(Order.symbol == symbol)
            .where(Order.strategy_name == strategy_name)
            .where(Order.status == OrderStatus.CLOSED)
            .order_by(Order.created_at.desc())
            .limit(30)
        )
        orders = db.execute(stmt).scalars().all()
        
        # Need at least 10 trades for statistical significance
        if len(orders) < 10:
            return True
            
        wins = []
        losses = []
        
        for o in orders:
            pnl = float(o.pnl)
            if pnl > 0:
                wins.append(pnl)
            else:
                # Include breakeven as a loss (or 0)
                losses.append(pnl)
                
        total_trades = len(orders)
        win_rate = len(wins) / total_trades
        
        avg_win = (sum(wins) / len(wins)) if wins else 0.0
        avg_loss = (sum(losses) / len(losses)) if losses else 0.0
        
        # Expected Value = (Win Rate x Avg Win) - (Loss Rate x Avg Loss Abs)
        ev = (win_rate * avg_win) - ((1 - win_rate) * abs(avg_loss))
        
        if ev < 0:
            logger.warning(
                f"EV Filter BLOCKED {strategy_name} on {symbol}: "
                f"EV={ev:.2f} (WR={win_rate*100:.1f}%, trades={total_trades})"
            )
            return False
            
        return True

    def update_weights(self, strategy_name: str, new_weight: float) -> None:
        if strategy_name in self._strategy_weights:
            self._strategy_weights[strategy_name] = new_weight
            logger.info(f"Updated weight for {strategy_name} to {new_weight}")
            self._save_weights()

    def _load_state(self) -> None:
        if os.path.exists(self._weights_file):
            try:
                with open(self._weights_file, 'r') as f:
                    data = json.load(f)
                    for k, v in data.items():
                        if k in self._strategy_weights:
                            self._strategy_weights[k] = float(v)
                logger.info(f"Loaded strategy weights: {self._strategy_weights}")
            except Exception as e:
                logger.error(f"Failed to load weights: {e}")
        # strategy_params.json is intentionally NOT applied: it was written by a
        # placeholder "refit" that only ever tightened params on profit factor,
        # without the per-trade data the rule needs. Strategies run on their
        # backtested defaults until a real refit exists.

    def _save_weights(self) -> None:
        try:
            with open(self._weights_file, 'w') as f:
                json.dump(self._strategy_weights, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save weights: {e}")
