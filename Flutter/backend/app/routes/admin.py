from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import SessionLocal
from .. import crud, models, schemas

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/api/admin/limits")
def get_limits(db: Session = Depends(get_db)):
    user = crud.get_user(db, 'admin')
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "daily_limit": user.daily_limit,
        "monthly_limit": user.monthly_limit,
        "daily_spent": user.daily_spent,
        "monthly_spent": user.monthly_spent,
        "tokens": user.tokens
    }

@router.post("/api/admin/limits")
def set_limits(limits: schemas.LimitUpdate, db: Session = Depends(get_db)):
    user = crud.get_user(db, 'admin')
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.daily_limit = limits.daily_limit
    user.monthly_limit = limits.monthly_limit
    db.add(user)
    db.commit()
    return {"status": "ok", "message": "Limits updated", "daily_limit": user.daily_limit, "monthly_limit": user.monthly_limit}

@router.post("/api/admin/reset_spent")
def reset_spent(db: Session = Depends(get_db)):
    user = crud.get_user(db, 'admin')
    if user:
        user.daily_spent = 0
        user.monthly_spent = 0
        db.add(user)
        db.commit()
    return {"status": "ok", "message": "Spend counters reset"}
