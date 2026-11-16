"""API endpoints for the Paper Strategy Runner."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import crud
from app.db import get_db
from app.engines.paper_strategy_runner import get_runner

router = APIRouter(prefix="/api/paper", tags=["paper"])


@router.get("/status")
def paper_status(db: Session = Depends(get_db)):
    """Runner state (see PaperStrategyRunner.get_status) plus automation_enabled
    (False = a risk guard halted auto-trading)."""
    status = get_runner().get_status()
    user = crud.get_user(db, "admin")
    status["automation_enabled"] = bool(user and user.automation_enabled)
    return status


@router.post("/start")
async def paper_start():  # async: start() needs the event loop (create_task)
    get_runner().start()   # also un-pauses
    return {"status": "started"}


@router.post("/pause")
def paper_pause():
    get_runner().pause()
    return {"status": "paused"}
