import traceback
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

URL = "postgresql://postgres:Wzz3%25%40%23BQVyAVKE@db.oreaodhcmxyyzfproraa.supabase.co:5432/postgres"

print("Testing connection...")
try:
    engine = create_engine(URL)
    conn = engine.connect()
    print("Connection successful!")
    conn.close()
except Exception as e:
    print("Connection failed!")
    traceback.print_exc()
