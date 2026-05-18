import logging
import time
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.user import User
from app.models.tenant import Tenant
from app.models.subscription import Subscription
from app.security.password import get_password_hash, verify_password
from app.security.jwt import create_access_token, create_refresh_token, decode_token
from pydantic import BaseModel, EmailStr

logger = logging.getLogger(__name__)
router = APIRouter()

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(user_in: UserRegister, db: Session = Depends(get_db)):
    t_start = time.time()
    logger.info(f"REGISTER ROUTE HIT — email={user_in.email}")
    try:
        # Check if user exists
        logger.debug("Querying for existing user...")
        user = db.query(User).filter(User.email == user_in.email).first()
        if user:
            logger.warning(f"Registration attempt for existing email: {user_in.email}")
            raise HTTPException(
                status_code=400,
                detail="The user with this username already exists in the system.",
            )

        # Hash password
        logger.debug("Hashing password...")
        hashed = get_password_hash(user_in.password)
        logger.debug("Password hashed successfully")

        # Create User
        logger.debug("Creating User record...")
        new_user = User(
            email=user_in.email,
            hashed_password=hashed,
            full_name=user_in.full_name,
        )
        db.add(new_user)
        db.flush()
        logger.info(f"User flushed with id={new_user.id}")

        # Create Default Tenant
        logger.debug("Creating Tenant record...")
        new_tenant = Tenant(
            name=f"{user_in.full_name}'s Workspace",
            owner_id=new_user.id
        )
        db.add(new_tenant)
        db.flush()
        logger.info(f"Tenant flushed with id={new_tenant.id}")

        # Create default subscription
        logger.debug("Creating default Subscription record...")
        mock_sub = Subscription(
            tenant_id=new_tenant.id,
            paymenter_subscription_id="mock_sub_demo_123",
            plan_name="basic",
            status="active",
            limits={"mem_limit": "2g", "cpu_quota": 200000}
        )
        db.add(mock_sub)

        logger.debug("Committing transaction...")
        db.commit()
        db.refresh(new_user)
        logger.info(f"REGISTER SUCCESS — user_id={new_user.id} in {time.time()-t_start:.3f}s")

        return {"message": "User registered successfully", "user_id": str(new_user.id)}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"REGISTER FAILED — unexpected error after {time.time()-t_start:.3f}s")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")


@router.post("/login")
def login(response: Response, user_in: UserLogin, db: Session = Depends(get_db)):
    t_start = time.time()
    logger.info(f"LOGIN ROUTE HIT — email={user_in.email}")
    try:
        # Authenticate
        logger.debug("Querying user by email...")
        user = db.query(User).filter(User.email == user_in.email).first()
        if not user:
            logger.warning(f"Login attempt for non-existent email: {user_in.email}")
            raise HTTPException(status_code=400, detail="Incorrect email or password")

        logger.debug("Verifying password...")
        if not verify_password(user_in.password, user.hashed_password):
            logger.warning(f"Password mismatch for email: {user_in.email}")
            raise HTTPException(status_code=400, detail="Incorrect email or password")

        # Generate tokens
        logger.debug("Generating JWT tokens...")
        access_token = create_access_token(subject=user.id)
        refresh_token = create_refresh_token(subject=user.id)
        logger.debug("JWT tokens generated successfully")

        # Set HTTP-only cookies
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=True,
            samesite="lax"
        )
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=True,
            samesite="lax",
            path="/api/v1/auth/refresh"
        )

        logger.info(f"LOGIN SUCCESS — user_id={user.id} in {time.time()-t_start:.3f}s")
        return {"message": "Login successful"}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"LOGIN FAILED — unexpected error after {time.time()-t_start:.3f}s")
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")


@router.post("/refresh")
def refresh_token(request: Request, response: Response, db: Session = Depends(get_db)):
    logger.info("REFRESH ROUTE HIT")
    try:
        refresh_token = request.cookies.get("refresh_token")
        if not refresh_token:
            raise HTTPException(status_code=401, detail="Refresh token missing")

        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid refresh token payload")

        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User not found or inactive")

        access_token = create_access_token(subject=user.id)
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=True,
            samesite="lax"
        )
        logger.info(f"REFRESH SUCCESS — user_id={user.id}")
        return {"message": "Token refreshed"}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("REFRESH FAILED — unexpected error")
        raise HTTPException(status_code=500, detail=f"Token refresh failed: {str(e)}")


@router.post("/logout")
def logout(response: Response):
    logger.info("LOGOUT ROUTE HIT")
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token", path="/api/v1/auth/refresh")
    return {"message": "Logged out successfully"}


@router.get("/me")
def get_current_user(request: Request, db: Session = Depends(get_db)):
    logger.info("ME ROUTE HIT")
    try:
        access_token = request.cookies.get("access_token")
        if not access_token:
            raise HTTPException(status_code=401, detail="Not authenticated")

        payload = decode_token(access_token)
        if not payload or payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token")

        user_id = payload.get("sub")
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        tenant = db.query(Tenant).filter(Tenant.owner_id == user.id).first()
        subscription = None
        if tenant:
            subscription = db.query(Subscription).filter(
                Subscription.tenant_id == tenant.id
            ).order_by(Subscription.created_at.desc()).first()

            if not subscription:
                logger.info(f"No subscription found for tenant={tenant.id}, creating default basic plan")
                subscription = Subscription(
                    tenant_id=tenant.id,
                    paymenter_subscription_id=f"mock_sub_legacy_{str(tenant.id)[:8]}",
                    plan_name="basic",
                    status="active",
                    limits={"mem_limit": "2g", "cpu_quota": 200000}
                )
                db.add(subscription)
                db.commit()
                db.refresh(subscription)

        plan_name = "free"
        if subscription:
            p_name = subscription.plan_name.lower()
            plan_name = "basic" if p_name in ["starter", "basic"] else p_name

        logger.info(f"ME SUCCESS — user_id={user.id} plan={plan_name}")
        return {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "tenant_id": str(tenant.id) if tenant else None,
            "subscription_status": subscription.status if subscription else "none",
            "plan": plan_name
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("ME FAILED — unexpected error")
        raise HTTPException(status_code=500, detail=f"Failed to fetch user: {str(e)}")

