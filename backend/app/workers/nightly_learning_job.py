"""
app/workers/nightly_learning_job.py

Nightly loop that tunes strategy weights and disables strategies on anomalies (weight 0).
Runs daily at 16:00 IST via APScheduler.
"""

import logging
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Order, OrderStatus
from app.engines.paper_strategy_runner import get_runner

logger = logging.getLogger("NightlyLearningJob")
_IST = ZoneInfo("Asia/Kolkata")

def _clamp(val: float, min_val: float, max_val: float) -> float:
    return max(min_val, min(val, max_val))

def run_nightly_job():
    """
    1. Strategy weight tuner
    2. Anomaly detector
    """
    logger.info("Starting Nightly Learning Job...")
    
    runner = get_runner()
    decision_engine = getattr(runner, "_decision_engine", None)
    if not decision_engine:
        logger.error("DecisionEngine not found on PaperStrategyRunner. Cannot run learning job.")
        return

    today_str = datetime.now(_IST).strftime("%Y%m%d")
    log_file = os.path.join(os.path.dirname(__file__), f"../../learning_log_{today_str}.json")
    
    log_data = {
        "timestamp": datetime.now(_IST).isoformat(),
        "strategies": {},
        "alerts": [],
    }

    with SessionLocal() as db:
        for strategy_name in ["orb_v4", "ema_momentum", "vwap_reversion", "supertrend"]:
            stmt = (
                select(Order)
                .where(Order.strategy_name == strategy_name)
                .where(Order.status == OrderStatus.CLOSED)
                .order_by(Order.created_at.desc())
                .limit(30)
            )
            orders = db.execute(stmt).scalars().all()
            
            # 1 & 2. Weight Tuner and Anomaly Detector
            if len(orders) < 10:
                log_data["strategies"][strategy_name] = {"status": "skipped_insufficient_data"}
                continue
                
            wins = []
            losses = []
            recent_losses = 0
            
            # Check last 5 trades for loss cluster
            for i, o in enumerate(orders[:5]):
                if float(o.pnl) <= 0:
                    recent_losses += 1
            
            for o in orders:
                pnl = float(o.pnl)
                if pnl > 0:
                    wins.append(pnl)
                else:
                    losses.append(pnl)
                    
            total_trades = len(orders)
            win_rate = len(wins) / total_trades
            gross_profit = sum(wins)
            gross_loss = abs(sum(losses))
            
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 99.0
            avg_win = gross_profit / len(wins) if wins else 0
            avg_loss = gross_loss / len(losses) if losses else 0
            avg_r = avg_win / avg_loss if avg_loss > 0 else 0
            
            old_weight = decision_engine._strategy_weights.get(strategy_name, 1.0)
            
            # Anomaly: Win rate too low
            if win_rate < 0.35 and total_trades >= 15:
                new_weight = 0.0
                msg = f"CRITICAL ALERT: {strategy_name} win rate dropped to {win_rate:.1%}. Disabling strategy."
                logger.critical(msg)
                log_data["alerts"].append(msg)
                
            # Anomaly: Loss cluster
            elif recent_losses >= 5:
                # Normal formula but halved
                base_weight = _clamp(profit_factor * 0.5 + win_rate * 0.5, 0.2, 2.0)
                new_weight = _clamp(base_weight * 0.5, 0.2, 2.0)
                msg = f"WARNING: Loss cluster detected for {strategy_name} (5 consecutive losses). Halving weight."
                logger.warning(msg)
                log_data["alerts"].append(msg)
                
            else:
                # Normal Tuning
                new_weight = _clamp(profit_factor * 0.5 + win_rate * 0.5, 0.2, 2.0)
                
            logger.info(f"Weight update: {strategy_name} -> {old_weight:.2f} -> {new_weight:.2f} (pf={profit_factor:.2f} wr={win_rate:.1%})")
            decision_engine.update_weights(strategy_name, new_weight)
            
            log_data["strategies"][strategy_name] = {
                "trades_analyzed": total_trades,
                "win_rate": win_rate,
                "profit_factor": profit_factor,
                "avg_r": avg_r,
                "old_weight": old_weight,
                "new_weight": new_weight
            }
            
    # Write log file
    try:
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to write learning log: {e}")

    logger.info("Nightly Learning Job Complete.")
