"""
auth.py — Authentication & user lifecycle router.

Registration:  User → Tenant → Subscription (linked to Starter Trial product).
Upgrade path:  Paymenter webhook updates existing subscription in-place.
"""
import logging
import time
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.models.tenant import Tenant
from app.models.product import Product
from app.models.subscription import Subscription
from app.security.password import get_password_hash, verify_password
from app.security.jwt import create_access_token, create_refresh_token, decode_token

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Pydantic schemas ─────────────────────────────────────────────────────────
class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


# ── Register ─────────────────────────────────────────────────────────────────
@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(user_in: UserRegister, db: Session = Depends(get_db)):
    """
    Fully transactional registration:
      1. Validate email uniqueness
      2. Create User
      3. Create Tenant
      4. Look up Starter Trial product
      5. Create trial Subscription linked to that product
    Rollback all on any failure — no orphan resources.
    """
    t_start = time.time()
    logger.info(f"REGISTER ROUTE HIT — email={user_in.email}")

    try:
        # ── 1. Email uniqueness ──────────────────────────────────────────────
        logger.debug("Checking for duplicate email...")
        if db.query(User).filter(User.email == user_in.email).first():
            logger.warning(f"Duplicate registration — email={user_in.email}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An account with this email address already exists.",
            )

        # ── 2. Create User ───────────────────────────────────────────────────
        logger.debug("Hashing password and creating User...")
        new_user = User(
            email=user_in.email,
            hashed_password=get_password_hash(user_in.password),
            full_name=user_in.full_name,
        )
        db.add(new_user)
        db.flush()
        logger.info(f"User flushed — user_id={new_user.id}")

        # ── 3. Create Tenant ─────────────────────────────────────────────────
        logger.debug("Creating Tenant...")
        new_tenant = Tenant(
            name=f"{user_in.full_name}'s Workspace",
            owner_id=new_user.id,
        )
        db.add(new_tenant)
        db.flush()
        logger.info(f"Tenant flushed — tenant_id={new_tenant.id}")

        # ── 4. Look up Starter Trial product ─────────────────────────────────
        starter = (
            db.query(Product)
            .filter(Product.extra["slug"].astext == "starter-trial")
            .first()
        )
        if not starter:
            logger.warning("Starter Trial product not found in catalog — using bare limits.")

        trial_limits = (
            {"cpu": starter.cpu, "memory": starter.memory,
             "deployments": starter.max_instances, "storage_gb": starter.storage_gb}
            if starter else {"cpu": "0.5", "memory": "512m", "deployments": 1}
        )

        # ── 5. Create trial Subscription ─────────────────────────────────────
        trial_ends = datetime.now(timezone.utc) + timedelta(days=settings.TRIAL_DAYS)
        logger.debug(f"Creating trial Subscription — trial_ends_at={trial_ends.date()}")
        trial_sub = Subscription(
            tenant_id=new_tenant.id,
            product_id=starter.id if starter else None,
            paymenter_subscription_id=None,
            plan_name="starter",
            status="trialing",
            trial_ends_at=trial_ends,
            limits=trial_limits,
        )
        db.add(trial_sub)

        # ── 6. Commit ────────────────────────────────────────────────────────
        logger.debug("Committing registration transaction...")
        db.commit()
        db.refresh(new_user)

        logger.info(
            f"REGISTER SUCCESS — user_id={new_user.id} "
            f"tenant_id={new_tenant.id} plan=starter/trialing "
            f"trial_ends={trial_ends.date()} elapsed={time.time()-t_start:.3f}s"
        )
        return {
            "message": f"Registration successful. Your {settings.TRIAL_DAYS}-day trial has started.",
            "user_id": str(new_user.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"REGISTER FAILED — rolling back — elapsed={time.time()-t_start:.3f}s")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed due to a server error. Please try again.",
        )


# ── Login ─────────────────────────────────────────────────────────────────────
@router.post("/login")
def login(response: Response, user_in: UserLogin, db: Session = Depends(get_db)):
    t_start = time.time()
    logger.info(f"LOGIN ROUTE HIT — email={user_in.email}")
    try:
        user = db.query(User).filter(User.email == user_in.email).first()
        if not user:
            raise HTTPException(status_code=400, detail="Incorrect email or password")

        if not verify_password(user_in.password, user.hashed_password):
            raise HTTPException(status_code=400, detail="Incorrect email or password")

        access_token  = create_access_token(subject=user.id)
        refresh_token = create_refresh_token(subject=user.id)

        response.set_cookie(key="access_token",  value=access_token,
                            httponly=True, secure=True, samesite="lax")
        response.set_cookie(key="refresh_token", value=refresh_token,
                            httponly=True, secure=True, samesite="lax",
                            path="/api/v1/auth/refresh")

        logger.info(f"LOGIN SUCCESS — user_id={user.id} elapsed={time.time()-t_start:.3f}s")
        return {"message": "Login successful"}

    except HTTPException:
        raise
    except Exception:
        logger.exception(f"LOGIN FAILED — elapsed={time.time()-t_start:.3f}s")
        raise HTTPException(status_code=500, detail="Login failed due to a server error.")


# ── Refresh ───────────────────────────────────────────────────────────────────
@router.post("/refresh")
def refresh_token(request: Request, response: Response, db: Session = Depends(get_db)):
    logger.info("REFRESH ROUTE HIT")
    try:
        token = request.cookies.get("refresh_token")
        if not token:
            raise HTTPException(status_code=401, detail="Refresh token missing")

        payload = decode_token(token)
        if not payload or payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        user_id = payload.get("sub")
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User not found or inactive")

        new_access = create_access_token(subject=user.id)
        response.set_cookie(key="access_token", value=new_access,
                            httponly=True, secure=True, samesite="lax")
        logger.info(f"REFRESH SUCCESS — user_id={user.id}")
        return {"message": "Token refreshed"}

    except HTTPException:
        raise
    except Exception:
        logger.exception("REFRESH FAILED")
        raise HTTPException(status_code=500, detail="Token refresh failed.")


# ── Logout ────────────────────────────────────────────────────────────────────
@router.post("/logout")
def logout(response: Response):
    logger.info("LOGOUT ROUTE HIT")
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token", path="/api/v1/auth/refresh")
    return {"message": "Logged out successfully"}


# ── Me ────────────────────────────────────────────────────────────────────────
@router.get("/me")
def get_current_user(request: Request, db: Session = Depends(get_db)):
    logger.info("ME ROUTE HIT")
    try:
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Not authenticated")

        payload = decode_token(token)
        if not payload or payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token")

        user = db.query(User).filter(User.id == payload.get("sub")).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        tenant = db.query(Tenant).filter(Tenant.owner_id == user.id).first()
        subscription = None
        product = None

        if tenant:
            subscription = (
                db.query(Subscription)
                .filter(Subscription.tenant_id == tenant.id)
                .order_by(Subscription.created_at.desc())
                .first()
            )
            if subscription and subscription.product_id:
                product = db.query(Product).filter(
                    Product.id == subscription.product_id
                ).first()

        # Derive frontend plan label
        plan_name = "free"
        if subscription:
            plan_name = subscription.plan_name.lower()
            if plan_name == "starter":
                plan_name = "basic"   # frontend display mapping

        logger.info(f"ME SUCCESS — user_id={user.id} plan={plan_name}")
        return {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "tenant_id": str(tenant.id) if tenant else None,
            "subscription_status": subscription.status if subscription else "none",
            "trial_ends_at": (
                subscription.trial_ends_at.isoformat()
                if subscription and subscription.trial_ends_at else None
            ),
            "plan": plan_name,
            "product": {
                "name":                product.name,
                "resource_type":       product.resource_type,
                "monthly_price_pence": product.monthly_price_pence,
                "cpu":                 product.cpu,
                "memory":              product.memory,
                "storage_gb":          product.storage_gb,
            } if product else None,
        }

    except HTTPException:
        raise
    except Exception:
        logger.exception("ME FAILED")
        raise HTTPException(status_code=500, detail="Failed to fetch user profile.")
