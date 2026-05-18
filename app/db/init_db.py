"""
init_db.py — Schema initialisation + product catalog seeding.

Called once at API startup.  Idempotent: safe to run on every restart.
"""
import logging
from app.db.base import Base
from app.db.session import engine, SessionLocal

# Import every model so SQLAlchemy registers them in Base.metadata
from app.models.user import User
from app.models.tenant import Tenant
from app.models.product import Product
from app.models.subscription import Subscription
from app.models.resource import Resource
from app.models.deployment import Deployment
from app.models.events import DeploymentEvent, WebhookEvent, ApiToken

logger = logging.getLogger(__name__)

# ── Product catalog ──────────────────────────────────────────────────────────
# Prices are in PENCE (integer).  £1.00 = 100.
# slug = unique machine identifier used for lookups in code
SEED_PRODUCTS = [
    # ── Trial / Starter ──────────────────────────────────────────────────────
    {
        "name": "Starter Trial",
        "resource_type": "desktop",
        "monthly_price_pence": 0,
        "cpu": "0.5",
        "memory": "512m",
        "storage_gb": 10,
        "bandwidth_gb": 100,
        "max_instances": 1,
        "extra": {"slug": "starter-trial", "label": "Free Trial", "highlight": False},
    },
    # ── Desktop Workspaces ───────────────────────────────────────────────────
    {
        "name": "Basic Desktop",
        "resource_type": "desktop",
        "monthly_price_pence": 1500,   # £15.00
        "cpu": "1.0",
        "memory": "1g",
        "storage_gb": 20,
        "bandwidth_gb": 250,
        "max_instances": 1,
        "extra": {"slug": "basic-desktop", "label": "Basic", "highlight": False},
    },
    {
        "name": "Pro Desktop",
        "resource_type": "desktop",
        "monthly_price_pence": 3000,   # £30.00
        "cpu": "2.0",
        "memory": "2g",
        "storage_gb": 50,
        "bandwidth_gb": 500,
        "max_instances": 3,
        "extra": {"slug": "pro-desktop", "label": "Pro", "highlight": True},
    },
    # ── VPS Plans ────────────────────────────────────────────────────────────
    {
        "name": "VPS Small",
        "resource_type": "vps",
        "monthly_price_pence": 1000,   # £10.00
        "cpu": "1.0",
        "memory": "1g",
        "storage_gb": 25,
        "bandwidth_gb": 1000,
        "max_instances": 1,
        "extra": {"slug": "vps-small", "label": "VPS Small", "highlight": False},
    },
    {
        "name": "VPS Medium",
        "resource_type": "vps",
        "monthly_price_pence": 2000,   # £20.00
        "cpu": "2.0",
        "memory": "4g",
        "storage_gb": 80,
        "bandwidth_gb": 2000,
        "max_instances": 1,
        "extra": {"slug": "vps-medium", "label": "VPS Medium", "highlight": True},
    },
    {
        "name": "VPS Large",
        "resource_type": "vps",
        "monthly_price_pence": 4000,   # £40.00
        "cpu": "4.0",
        "memory": "8g",
        "storage_gb": 200,
        "bandwidth_gb": 5000,
        "max_instances": 1,
        "extra": {"slug": "vps-large", "label": "VPS Large", "highlight": False},
    },
    # ── Container Runners ────────────────────────────────────────────────────
    {
        "name": "Container Small",
        "resource_type": "container",
        "monthly_price_pence": 800,    # £8.00
        "cpu": "0.5",
        "memory": "512m",
        "storage_gb": 10,
        "bandwidth_gb": 100,
        "max_instances": 2,
        "extra": {"slug": "container-small", "label": "Container S", "highlight": False},
    },
    {
        "name": "Container Medium",
        "resource_type": "container",
        "monthly_price_pence": 1500,   # £15.00
        "cpu": "1.0",
        "memory": "1g",
        "storage_gb": 20,
        "bandwidth_gb": 500,
        "max_instances": 5,
        "extra": {"slug": "container-medium", "label": "Container M", "highlight": False},
    },
    # ── Storage Add-ons ──────────────────────────────────────────────────────
    {
        "name": "Storage 50 GB",
        "resource_type": "storage",
        "monthly_price_pence": 500,    # £5.00
        "cpu": "0",
        "memory": "0",
        "storage_gb": 50,
        "bandwidth_gb": 0,
        "max_instances": 1,
        "extra": {"slug": "storage-50gb", "label": "50 GB", "highlight": False},
    },
    {
        "name": "Storage 200 GB",
        "resource_type": "storage",
        "monthly_price_pence": 1500,   # £15.00
        "cpu": "0",
        "memory": "0",
        "storage_gb": 200,
        "bandwidth_gb": 0,
        "max_instances": 1,
        "extra": {"slug": "storage-200gb", "label": "200 GB", "highlight": False},
    },
]


def seed_products(db) -> None:
    """Insert default products if not already present.  Keyed on metadata->slug."""
    inserted = 0
    for spec in SEED_PRODUCTS:
        slug = spec["extra"]["slug"]
        # Idempotency: only insert if this slug does not exist yet
        exists = (
            db.query(Product)
            .filter(Product.extra["slug"].astext == slug)
            .first()
        )
        if not exists:
            db.add(Product(**spec))
            inserted += 1

    if inserted:
        db.commit()
        logger.info(f"Product catalog seeded — {inserted} products added.")
    else:
        logger.info("Product catalog already seeded — no changes made.")


def init_db() -> None:
    """Create all tables and seed the product catalog. Safe to call on every restart."""
    try:
        logger.info("Initializing database schema...")
        Base.metadata.create_all(bind=engine)
        logger.info("Database schema initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database schema: {e}")
        raise

    db = SessionLocal()
    try:
        seed_products(db)
    except Exception as e:
        logger.error(f"Failed to seed product catalog: {e}")
        db.rollback()
        # Non-fatal — API still boots even if seed fails
    finally:
        db.close()
