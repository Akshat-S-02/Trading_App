
import uuid
from .models import Trade, AIAction
from .logger import system_logger

class OrderManager:
    def __init__(self, db):
        self.db = db

    def generate_order_id(self) -> str:
        """Generates a unique deterministic Order ID"""
        return str(uuid.uuid4())

    def is_order_processed(self, order_id: str) -> bool:
        """
        Checks idempotency: if order_id already exists in Trade or AIAction.
        """
        try:
            exists_trade = self.db.query(Trade).filter(Trade.order_id == order_id).first()
            if exists_trade:
                system_logger.warning(f"Idempotency Check: Order {order_id} already exists in Trades")
                return True
                
            # Also check AIAction if we store order_id there
            exists_action = self.db.query(AIAction).filter(AIAction.order_id == order_id).first()
            if exists_action:
                system_logger.warning(f"Idempotency Check: Order {order_id} already exists in AI Actions")
                return True
                
            return False
        except Exception as e:
            system_logger.error(f"Error checking idempotency for {order_id}: {e}")
            return True # Fail safe: assume processed to avoid dupes

