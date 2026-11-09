"""In-app notification list: every alert the system raised (see app/core/alerts.py)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Notification

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
def list_notifications(limit: int = 100, db: Session = Depends(get_db)):
    """Newest first, plus the unread count for the bell badge."""
    # shortcut: rows are never pruned; a few dozen a day is fine for years.
    items = db.query(Notification).order_by(Notification.id.desc()).limit(max(1, min(limit, 200))).all()
    unread = db.query(Notification).filter(Notification.read == False).count()  # noqa: E712
    return {
        "unread": unread,
        "items": [
            {"id": n.id, "level": n.level, "title": n.title, "message": n.message,
             "read": n.read, "created_at": n.created_at.isoformat() if n.created_at else None}
            for n in items
        ],
    }


@router.post("/read-all")
def mark_all_read(db: Session = Depends(get_db)):
    db.query(Notification).filter(Notification.read == False).update({"read": True})  # noqa: E712
    db.commit()
    return {"status": "ok"}
