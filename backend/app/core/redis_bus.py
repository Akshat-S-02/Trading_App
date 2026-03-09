import json
import logging
import redis
from datetime import datetime
from decimal import Decimal
from ..models import Direction
from ..engines.strategy_engine import Signal

logger = logging.getLogger("RedisBus")

class RedisSignalBus:
    """
    Durable Signal Transport using Redis Streams.
    Replaces ephemeral Pub/Sub with at-least-once message delivery.
    """
    STREAM_KEY = "strategy:signals"
    GROUP_NAME = "execution_workers"
    
    def __init__(self, host='127.0.0.1', port=6379, db=0):
        self.redis = redis.Redis(host=host, port=port, db=db, decode_responses=True)
        self._init_group()
        
    def _init_group(self):
        try:
            # Create the stream and consumer group if they don't exist
            self.redis.xgroup_create(self.STREAM_KEY, self.GROUP_NAME, id='0', mkstream=True)
            logger.info(f"Initialized Redis Stream '{self.STREAM_KEY}' and Consumer Group '{self.GROUP_NAME}'")
        except redis.exceptions.ResponseError as e:
            if "BUSYGROUP Consumer Group name already exists" not in str(e):
                logger.error(f"Failed to create Redis stream group: {e}")
                
    def publish_signal(self, signal: Signal) -> str:
        """
        Pushes a generated Signal into the durable Redis Stream.
        """
        payload = {
            "strategy_id": str(signal.strategy_id),
            "symbol": signal.symbol,
            "direction": signal.direction,
            "entry_price": str(signal.entry_price),
            "stop_loss": str(signal.stop_loss) if signal.stop_loss else "",
            "timestamp": signal.timestamp.isoformat(),
            "signal_hash": signal.signal_hash
        }
        
        message_id = self.redis.xadd(self.STREAM_KEY, payload)
        logger.info(f"Published Signal to Stream: {signal.signal_hash} -> MsgID: {message_id}")
        return message_id
        
    def consume_signals(self, consumer_name: str, count: int = 10, block_ms: int = 5000):
        """
        Reads pending messages from the Stream for this consumer group.
        """
        # '>' means read messages never delivered to any consumer in the group before
        streams = {self.STREAM_KEY: '>'}
        try:
            results = self.redis.xreadgroup(
                self.GROUP_NAME, 
                consumer_name, 
                streams, 
                count=count, 
                block=block_ms
            )
            
            parsed_signals = []
            if results:
                stream_name, messages = results[0]
                for message_id, payload in messages:
                    # Reconstruct Signal
                    sig = Signal(
                        strategy_id=int(payload["strategy_id"]),
                        symbol=payload["symbol"],
                        direction=payload["direction"],
                        entry_price=Decimal(payload["entry_price"]),
                        stop_loss=Decimal(payload["stop_loss"]) if payload["stop_loss"] else None,
                        timestamp=datetime.fromisoformat(payload["timestamp"])
                    )
                    # Force override hash to match original DB block
                    sig.signal_hash = payload["signal_hash"]
                    
                    parsed_signals.append((message_id, sig))
                    
            return parsed_signals
            
        except Exception as e:
            logger.error(f"Failed to consume from Redis stream: {e}")
            return []
            
    def ack_signal(self, message_id: str):
        """
        Acknowledges that the worker has flawlessly saved the execution to Postgres.
        Releases the message from the Pending Entries List (PEL).
        """
        self.redis.xack(self.STREAM_KEY, self.GROUP_NAME, message_id)
        logger.debug(f"ACKed Message {message_id}")
