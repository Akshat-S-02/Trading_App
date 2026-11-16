from datetime import datetime
import hashlib
from decimal import Decimal

def snap_to_tick(price: Decimal, tick_size: str = "0.05") -> Decimal:
    tick = Decimal(tick_size)
    return (Decimal(str(price)) / tick).quantize(Decimal('1')) * tick

class Signal:
    def __init__(self, strategy_id: int, symbol: str, direction: str, entry_price: Decimal, stop_loss: Decimal, timestamp: datetime, strategy_name: str = None, target_price: Decimal = None):
        self.strategy_id = strategy_id
        self.strategy_name = strategy_name
        self.symbol = symbol
        self.direction = direction
        self.entry_price = snap_to_tick(entry_price)
        self.stop_loss = snap_to_tick(stop_loss) if stop_loss is not None else None
        self.target_price = snap_to_tick(target_price) if target_price is not None else None
        self.timestamp = timestamp
        
        # Idempotency Key: Combines strategy_name, symbol, direction, and the exact minute
        raw_key = f"{strategy_name}_{symbol}_{direction}_{timestamp.strftime('%Y%m%d%H%M')}"
        self.signal_hash = hashlib.md5(raw_key.encode('utf-8')).hexdigest()

    def __repr__(self):
        return f"<Signal {self.direction} {self.symbol} @ {self.entry_price} [{self.signal_hash}]>"
