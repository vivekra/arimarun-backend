import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1.auth import router as auth_router
from app.api.v1.deployments import router as deployments_router
from app.api.v1.webhooks import router as webhooks_router
from app.db.init_db import init_db

# Configure root logging so all DEBUG logs are visible in docker logs
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.PROJECT_NAME)

@app.on_event("startup")
def startup_event():
    logger.info("=== ARIMARUN API STARTING UP ===")
    try:
        init_db()
        logger.info("=== DATABASE CONNECTION SUCCESSFUL ===")
    except Exception as e:
        logger.error(f"=== DATABASE INITIALIZATION FAILED: {e} ===")
        raise

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(deployments_router, prefix="/api/v1/deployments", tags=["deployments"])
app.include_router(webhooks_router, prefix="/api/v1/webhooks", tags=["webhooks"])

@app.get("/health")
def health_check():
    return {"status": "ok", "project": settings.PROJECT_NAME}
