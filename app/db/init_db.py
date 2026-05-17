import logging
from app.db.base import Base
from app.db.session import engine

# Import all models to ensure metadata is registered before create_all()
from app.models.user import User
from app.models.tenant import Tenant
from app.models.subscription import Subscription
from app.models.deployment import Deployment
from app.models.events import DeploymentEvent, WebhookEvent, ApiToken

logger = logging.getLogger(__name__)

def init_db():
    try:
        logger.info("Initializing database schema...")
        Base.metadata.create_all(bind=engine)
        logger.info("Database schema initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database schema: {str(e)}")
        raise e
