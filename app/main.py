import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1.auth import router as auth_router
from app.api.v1.deployments import router as deployments_router
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.subscriptions import router as subscriptions_router
from app.api.v1.workers import router as workers_router
from app.db.init_db import init_db

# Configure root logging so all DEBUG logs are visible in docker logs
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.PROJECT_NAME)

# ── CORS Middleware ─────────────────────────────────────────────────────────
# MUST be added before routers so OPTIONS preflight requests are handled first
_cors_origins = settings.cors_origins_list
logger.info(f"CORS configured for origins: {_cors_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,          # Required for HttpOnly cookie-based JWT auth
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Set-Cookie"],   # Allows browser to read Set-Cookie on cross-origin
)

# ── Startup event ───────────────────────────────────────────────────────────
@app.on_event("startup")
def startup_event():
    logger.info("=== ARIMARUN API STARTING UP ===")
    logger.info(f"=== CORS ORIGINS ALLOWED: {_cors_origins} ===")
    try:
        init_db()
        logger.info("=== DATABASE CONNECTION SUCCESSFUL ===")
    except Exception as e:
        logger.error(f"=== DATABASE INITIALIZATION FAILED: {e} ===")
        raise

# ── Routers ─────────────────────────────────────────────────────────────────
app.include_router(auth_router,          prefix="/api/v1/auth",          tags=["auth"])
app.include_router(deployments_router,   prefix="/api/v1/deployments",   tags=["deployments"])
app.include_router(webhooks_router,      prefix="/api/v1/webhooks",       tags=["webhooks"])
app.include_router(subscriptions_router, prefix="/api/v1/subscriptions",  tags=["subscriptions"])
app.include_router(workers_router,       prefix="/api/v1/workers",        tags=["workers"])

@app.get("/health")
def health_check():
    return {"status": "ok", "project": settings.PROJECT_NAME}
