from app.db import SessionLocal, Base, engine
from app import models
from app.crud import create_default_user

Base.metadata.create_all(bind=engine)
db = SessionLocal()
create_default_user(db)
db.close()
print("DB initialized and default user created.")
