import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set. Add it to backend/.env.")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def require_test_db():
    """
    Call first in any script that deletes rows or drops tables. Scripts share the
    app's DATABASE_URL, so without this they wipe real paper-trading history.
    """
    name = engine.url.database or ""
    if not name.endswith("_test"):
        raise SystemExit(
            f"Refusing to run: DATABASE_URL points at database '{name}'. This script deletes data; "
            f"run it against a separate database whose name ends in '_test'."
        )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
