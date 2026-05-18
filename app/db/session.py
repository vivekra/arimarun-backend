import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

logger = logging.getLogger(__name__)
logger.info("Initializing SQLAlchemy engine...")

# SQLAlchemy engine with explicit timeouts and debug logging
# pool_recycle helps with Supabase Session Pooler dropping idle connections
engine = create_engine(
    settings.DATABASE_URL, 
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,  # Prevents hanging indefinitely waiting for a connection
    pool_recycle=1800, # Recycle connections every 30 mins
    echo=True, # Enable SQLAlchemy engine debug logging
    echo_pool=True
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
logger.info("Database connection engine initialized successfully")
