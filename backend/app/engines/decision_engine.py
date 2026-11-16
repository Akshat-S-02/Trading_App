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
        self._adapters = {
            "orb_v4": MomentumORBv4Adapter(strategy_id),
            "ema_momentum": EMAMomentumAdapter(strategy_id),
            "vwap_reversion": VWAPReversionAdapter(strategy_id),
            "supertrend": SupertrendAdapter(strategy_id),
        }
        self._regime_classifier = RegimeClassifier   # classmethods only
        self._strategy_weights: Dict[str, float] = dict.fromkeys(self._adapters, 1.0)
        self._weights_file = os.path.join(os.path.dirname(__file__), '../../strategy_weights.json')
        self._load_state()
        self._bar_history: Dict[str, list[dict]] = {}
        self._last_regime: Dict[str, str] = {}

    @property
    def _orb_adapter(self):
        return self._adapters["orb_v4"]

    def feed_state_only(self, symbol: str, candle: dict) -> None:
        """Advance every strategy's state on this candle without letting any signal."""
        for adapter in self._adapters.values():
            adapter.on_candle(symbol, candle, allow_signal=False)

    def evaluate(self, symbol: str, candle: dict) -> Optional[AppSignal]:
        """
        Evaluate a completed candle against active strategies, filter by regime and EV.
        """
        history = self._bar_history.setdefault(symbol, [])
        history.append({
            "timestamp": candle["timestamp"],
            "open": float(candle["open"]),
            "high": float(candle["high"]),
            "low": float(candle["low"]),
            "close": float(candle["close"]),
            "volume": int(candle.get("volume", 0)),
        })
        if len(history) > 100:
            history.pop(0)

        # 1. Classify Regime (needs 20 bars)
        regime_data = self._regime_classifier.classify(history)
        if not regime_data:
            self._last_regime[symbol] = "INSUFFICIENT_DATA"
            self.feed_state_only(symbol, candle)
            return None
        regime = regime_data["regime"]
        trend = regime_data["trend"]
        allowed_strategies = self._regime_classifier.STRATEGY_MATRIX.get((regime, trend), [])
        self._last_regime[symbol] = f"{regime.value} + {trend}"

        # 2. Every strategy sees every candle so its state (opening range, VWAP,
        # EMAs) has no gaps; the regime only decides which may signal.
        signals: List[AppSignal] = []
        for strategy_name, adapter in self._adapters.items():
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

        # 3. EV filter, then 4. highest weight wins (first one on a tie)
        with SessionLocal() as db:
            valid_signals = [sig for sig in signals if self._passes_ev_filter(symbol, sig.strategy_name, db)]
        if not valid_signals:
            return None
        winner = max(valid_signals, key=lambda sig: self._strategy_weights.get(sig.strategy_name, 1.0))
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
            
        # Expected value per trade; breakeven counts as a loss
        pnls = [float(o.pnl) for o in orders]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        win_rate = len(wins) / len(pnls)
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
        ev = win_rate * avg_win - (1 - win_rate) * avg_loss
        total_trades = len(pnls)

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
