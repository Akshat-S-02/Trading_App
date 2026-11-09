from sqlalchemy import text
from sqlalchemy.orm import Session
from . import models

def get_user(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()

PAPER_STRATEGY_ID = 1  # PaperStrategyRunner / DecisionEngine emit signals under this id
PAPER_STRATEGY_NAME = "decision_engine"

def create_default_user(db: Session):
    user = get_user(db, 'admin')
    if not user:
        user = models.User(username='admin', capital_initial=50000.0, capital_current=50000.0)
        db.add(user); db.commit(); db.refresh(user)
    seed_trading_defaults(db, user)
    return user

def seed_trading_defaults(db: Session, user: models.User):
    """
    Idempotently create the rows ExecutionEngine needs to route signals:
    the paper Strategy, the user's allocation to it, and PortfolioMetrics.
    Existing rows are left untouched.
    """
    strategy = db.query(models.Strategy).filter(models.Strategy.id == PAPER_STRATEGY_ID).first()
    if not strategy:
        strategy = models.Strategy(id=PAPER_STRATEGY_ID, name=PAPER_STRATEGY_NAME, active=True)
        db.add(strategy)
        db.commit()
        if db.bind.dialect.name == "postgresql":
            # Inserting an explicit id doesn't advance the serial sequence
            db.execute(text(
                "SELECT setval(pg_get_serial_sequence('strategies', 'id'), "
                "(SELECT MAX(id) FROM strategies))"
            ))
            db.commit()

    alloc = db.query(models.UserStrategyAllocation).filter(
        models.UserStrategyAllocation.user_id == user.id,
        models.UserStrategyAllocation.strategy_id == strategy.id,
    ).first()
    if not alloc:
        db.add(models.UserStrategyAllocation(
            user_id=user.id,
            strategy_id=strategy.id,
            allocation_percentage=100.0,
            risk_per_trade=1.0,
        ))
        db.commit()

    metrics = db.query(models.PortfolioMetrics).filter(models.PortfolioMetrics.user_id == user.id).first()
    if not metrics:
        # available_margin starts at capital: nothing syncs margin in paper mode,
        # and the local margin guard rejects every order when it is 0.
        db.add(models.PortfolioMetrics(
            user_id=user.id,
            peak_equity=user.capital_initial,
            available_margin=user.capital_current,
        ))
        db.commit()

def add_tokens(db: Session, username: str, amount: float):
    user = get_user(db, username)
    if user:
        user.capital_current += amount
        db.add(user); db.commit(); db.refresh(user)
    return user

# holdings, trades helpers omitted for brevity; add as needed
