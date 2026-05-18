import logging
from app.db.base import Base
from app.db.session import engine, SessionLocal

logger = logging.getLogger(__name__)

# Dependency to get DB session with full lifecycle logging
def get_db():
    db = SessionLocal()
    logger.debug("DB session opened")
    try:
        yield db
        logger.debug("DB session yield complete")
    except Exception as e:
        logger.error(f"DB session exception — rolling back: {e}")
        db.rollback()
        raise
    finally:
        db.close()
        logger.debug("DB session closed")
