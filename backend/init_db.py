"""
Drops EVERY table and recreates the schema with the default user.
All orders, fills and paper history are lost. Requires --wipe to run.
(The API creates missing tables on its own at startup; this is only for a full reset.)
"""
import sys

from app.db import SessionLocal, Base, engine
from app import models  # noqa: F401  (registers tables on Base)
from app.crud import create_default_user

if "--wipe" not in sys.argv:
    raise SystemExit(f"This deletes ALL data in database '{engine.url.database}'. "
                     f"Re-run as: python init_db.py --wipe")

print("Dropping old tables...")
Base.metadata.drop_all(bind=engine)

print("Creating new tables...")
Base.metadata.create_all(bind=engine)

db = SessionLocal()
create_default_user(db)
db.close()
print("DB initialized with the default user.")
