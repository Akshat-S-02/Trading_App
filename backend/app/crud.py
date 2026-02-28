from sqlalchemy.orm import Session
from . import models

def get_user(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()

def create_default_user(db: Session):
    user = get_user(db, 'admin')
    if not user:
        user = models.User(username='admin', tokens=50000.0)
        db.add(user); db.commit(); db.refresh(user)
    return user

def add_tokens(db: Session, username: str, amount: float):
    user = get_user(db, username)
    if user:
        user.tokens += amount
        db.add(user); db.commit(); db.refresh(user)
    return user

# holdings, trades helpers omitted for brevity; add as needed
