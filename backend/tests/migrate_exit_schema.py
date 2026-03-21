import psycopg2

def migrate():
    try:
        conn = psycopg2.connect('postgresql://postgres:Akshat%401311@localhost:5432/trading_sandbox')
        cur = conn.cursor()
        
        print("🔨 Updating database schema...")
        
        # Add exit_reason
        cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS exit_reason VARCHAR;")
        # Add close_requested_at
        cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS close_requested_at TIMESTAMP WITH TIME ZONE;")
        
        # Add 'CLOSED' to orderstatus enum if not exists
        try:
            # PostgreSQL doesn't support IF NOT EXISTS for ADD VALUE directly in some versions, 
            # so we use a check or try/except.
            cur.execute("ALTER TYPE orderstatus ADD VALUE 'CLOSED';")
            print("✅ Added 'CLOSED' to orderstatus enum.")
        except psycopg2.errors.DuplicateObject:
            conn.rollback()
            conn = psycopg2.connect('postgresql://postgres:Akshat%401311@localhost:5432/trading_sandbox')
            cur = conn.cursor()
            print("ℹ️ 'CLOSED' already exists in enum.")
        
        conn.commit()
        print("✅ Migration complete.")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    migrate()
