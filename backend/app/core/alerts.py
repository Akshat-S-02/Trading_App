import os
import json
import logging
import asyncio
import httpx
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("Alerts")

WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL") # Telegram, Discord, Slack, etc.

async def async_dispatch_alert(level: str, title: str, message: str, metadata: dict = None):
    """
    Fire-and-forget async webhook dispatcher for critical production events.
    """
    if not WEBHOOK_URL:
        # Silently drop if alerts aren't configured
        logger.warning(f"Alert Not Sent (No Webhook): [{level}] {title} - {message}")
        return

    payload = {
        "text": f"[{level} ALERT: {title}]\n{message}\nTime: {datetime.utcnow().isoformat()}Z"
    }

    if metadata:
        payload["text"] += f"\n```json\n{json.dumps(metadata, indent=2)}\n```"

    try:
        async with httpx.AsyncClient() as client:
            await client.post(WEBHOOK_URL, json=payload, timeout=5.0)
    except Exception as e:
        logger.error(f"Failed to dispatch alert: {e}")

def sync_dispatch_alert(level: str, title: str, message: str, metadata: dict = None):
    """
    Synchronous wrapper for contexts (like SQLAlchemy transactions) where async isn't available.
    Submits the task to the asyncio background event loop if running, or runs it explicitly.
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(async_dispatch_alert(level, title, message, metadata))
    except RuntimeError:
        # No running event loop
        asyncio.run(async_dispatch_alert(level, title, message, metadata))
