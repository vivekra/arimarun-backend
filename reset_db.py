import logging
from app.core.database import Base, engine
from app.db.init_db import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def reset_database():
    """DANGER: Drops all tables and recreates them fresh."""
    logger.warning("DROPPING ALL TABLES IN 3 SECONDS...")
    import time
    time.sleep(3)
    
    logger.info("Dropping all tables...")
    Base.metadata.drop_all(bind=engine)
    
    logger.info("Recreating all tables and seeding...")
    init_db()
    
    logger.info("Database reset complete. All models are now in sync with Supabase.")

if __name__ == "__main__":
    reset_database()
