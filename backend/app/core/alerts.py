"""
app/core/alerts.py

Every alert is saved to the `notifications` table, which the app's bell and
notification list show (and pop up as a banner while the app is open).
"""
import asyncio
import json
import logging

logger = logging.getLogger("Alerts")


def _store(level: str, title: str, message: str) -> None:
    """Persist the alert for the in-app list. Never raises: alerts must not break trading."""
    from app.db import SessionLocal
    from app.models import Notification
    try:
        with SessionLocal() as db:
            db.add(Notification(level=level, title=title, message=message))
            db.commit()
    except Exception as e:
        logger.error(f"Failed to store notification '{title}': {e}")


async def async_dispatch_alert(level: str, title: str, message: str, metadata: dict = None):
    if metadata:
        message += "\n" + json.dumps(metadata, indent=2, default=str)
    logger.info(f"Alert [{level}] {title} - {message}")
    await asyncio.to_thread(_store, level, title, message)


def sync_dispatch_alert(level: str, title: str, message: str, metadata: dict = None):
    """
    For sync code. Inside a running event loop: fire and forget. In a worker
    thread or the OutboxWorker process (no loop): runs to completion.
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(async_dispatch_alert(level, title, message, metadata))
    except RuntimeError:
        asyncio.run(async_dispatch_alert(level, title, message, metadata))
