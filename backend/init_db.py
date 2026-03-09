from app.db import SessionLocal, Base, engine
from app import models
from app.crud import create_default_user

print("Dropping old tables...")
Base.metadata.drop_all(bind=engine)

print("Creating new FinTech tables...")
Base.metadata.create_all(bind=engine)

db = SessionLocal()
create_default_user(db)
db.close()
print("DB initialized and default user migrated to new schema.")
