from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
import pandas as pd
from datetime import datetime
import hashlib
from decimal import Decimal

def snap_to_tick(price: Decimal, tick_size: str = "0.05") -> Decimal:
    tick = Decimal(tick_size)
    return (Decimal(str(price)) / tick).quantize(Decimal('1')) * tick

class Signal:
    def __init__(self, strategy_id: int, symbol: str, direction: str, entry_price: Decimal, stop_loss: Decimal, timestamp: datetime):
        self.strategy_id = strategy_id
        self.symbol = symbol
        self.direction = direction
        self.entry_price = snap_to_tick(entry_price)
        self.stop_loss = snap_to_tick(stop_loss) if stop_loss is not None else None
        self.timestamp = timestamp
        
        # Idempotency Key: Combines strategy, symbol, direction, and the exact minute
        raw_key = f"{strategy_id}_{symbol}_{direction}_{timestamp.strftime('%Y%m%d%H%M')}"
        self.signal_hash = hashlib.md5(raw_key.encode('utf-8')).hexdigest()

    def __repr__(self):
        return f"<Signal {self.direction} {self.symbol} @ {self.entry_price} [{self.signal_hash}]>"


class StrategyBase(ABC):
    def __init__(self, strategy_id: int, symbol: str, parameters: Optional[Dict[str, Any]] = None):
        self.strategy_id = strategy_id
        self.symbol = symbol
        self.parameters = parameters or {}
        self.bars: List[Dict[str, Any]] = []

    def _validate_bar(self, bar_data: Dict[str, Any]) -> bool:
        """
        Guards against bad ticks: duplicate timestamps, out-of-order, 0-volume, or negative spreads.
        """
        if bar_data.get('Volume', 0) <= 0:
            return False
            
        high = bar_data.get('High', 0)
        low = bar_data.get('Low', 0)
        if high < low:
            return False
            
        if self.bars:
            last_time = self.bars[-1].get('timestamp')
            curr_time = bar_data.get('timestamp')
            if last_time and curr_time and curr_time <= last_time:
                return False
                
        return True

    @abstractmethod
    def on_bar(self, bar_data: Dict[str, Any]) -> Optional[Signal]:
        """
        Receives a single new OHLCV bar (dict).
        Updates state and returns a Signal if a trigger occurs.
        """
        pass

    @abstractmethod
    def generate_signal(self) -> Optional[Signal]:
        """
        Evaluates the current internal state (self.bars) to generate a Signal.
        """
        pass


class NiftyBreakoutStrategy(StrategyBase):
    """
    Simulated Intraday Breakout Strategy.
    Maintains state incrementally via on_bar.
    """
    
    def on_bar(self, bar_data: Dict[str, Any]) -> Optional[Signal]:
        self.bars.append(bar_data)
        
        # Keep only the last 20 bars to prevent memory bloat
        if len(self.bars) > 20:
            self.bars.pop(0)
            
        return self.generate_signal()

    def generate_signal(self) -> Optional[Signal]:
        if len(self.bars) < 20:
            return None
            
        df = pd.DataFrame(self.bars)
        
        if df.empty or len(df) < 20:
            return None
            
        latest_close_val = float(df['Close'].iloc[-1])
        sma20_val = float(df['Close'].rolling(window=20).mean().iloc[-1])
        timestamp = df['timestamp'].iloc[-1] if 'timestamp' in df.columns else datetime.now()
        
        # Simple ATR calculation
        df['prev_close'] = df['Close'].shift(1)
        df['tr1'] = df['High'] - df['Low']
        df['tr2'] = (df['High'] - df['prev_close']).abs()
        df['tr3'] = (df['Low'] - df['prev_close']).abs()
        df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
        
        atr_val = float(df['tr'].rolling(14).mean().iloc[-1])
        
        latest_close = Decimal(f"{latest_close_val:.2f}")
        sma20 = Decimal(f"{sma20_val:.2f}")
        atr = Decimal(f"{atr_val:.2f}")
        
        multiplier1002 = Decimal("1.002")
        multiplier0998 = Decimal("0.998")
        multiplier15 = Decimal("1.5")
        
        if latest_close > sma20 * multiplier1002: # 0.2% above SMA20
            sl = latest_close - (atr * multiplier15)
            if sl < latest_close:
                return Signal(self.strategy_id, self.symbol, "LONG", latest_close, sl, timestamp)
                
        elif latest_close < sma20 * multiplier0998: # 0.2% below SMA20
            sl = latest_close + (atr * multiplier15)
            if sl > latest_close:
                return Signal(self.strategy_id, self.symbol, "SHORT", latest_close, sl, timestamp)
            
        return None
