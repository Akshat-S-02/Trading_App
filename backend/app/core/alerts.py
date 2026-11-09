"""
app/core/alerts.py

Every alert is (1) saved to the `notifications` table, which the app's
notification list shows, and (2) pushed to Telegram when configured, so it
pops up on phone / tablet / laptop even with the app closed.

Telegram setup (backend/.env):
  TELEGRAM_BOT_TOKEN=123456:ABC...   (from @BotFather)
  TELEGRAM_CHAT_ID=987654321         (your chat with the bot)
"""
import asyncio
import json
import logging
import os
from datetime import datetime

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("Alerts")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
_ICON = {"INFO": "ℹ️", "WARNING": "⚠️", "CRITICAL": "🚨", "FATAL": "🛑"}


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
    await asyncio.to_thread(_store, level, title, message)

    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        logger.warning(f"Alert not pushed (Telegram not configured): [{level}] {title} - {message}")
        return
    text = f"{_ICON.get(level, '')} {title}\n{message}\n{datetime.now().strftime('%d %b %H:%M:%S')}"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                                  json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=5.0)
            if r.status_code != 200:
                logger.error(f"Telegram push failed HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.error(f"Failed to push alert to Telegram: {e}")


def sync_dispatch_alert(level: str, title: str, message: str, metadata: dict = None):
    """
    For sync code. Inside a running event loop: fire and forget. In a worker
    thread or the OutboxWorker process (no loop): runs to completion (<= 5 s).
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(async_dispatch_alert(level, title, message, metadata))
    except RuntimeError:
        asyncio.run(async_dispatch_alert(level, title, message, metadata))
