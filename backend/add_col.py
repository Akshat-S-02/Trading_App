from app.db import engine
import sqlalchemy
try:
    with engine.connect() as conn:
        conn.execute(sqlalchemy.text('ALTER TABLE trade_fills ADD COLUMN paper_meta JSON;'))
        conn.commit()
    print('Added paper_meta to trade_fills')
except Exception as e:
    print(e)
