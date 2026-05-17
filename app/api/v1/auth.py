from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.user import User
from app.models.tenant import Tenant
from app.models.subscription import Subscription
from app.security.password import get_password_hash, verify_password
from app.security.jwt import create_access_token, create_refresh_token, decode_token
from pydantic import BaseModel, EmailStr

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
    # Check if user exists
    user = db.query(User).filter(User.email == user_in.email).first()
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this username already exists in the system.",
        )
    
    # Create User
    new_user = User(
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        full_name=user_in.full_name,
    )
    db.add(new_user)
    db.flush() # Get user ID
    
    # Create Default Tenant
    new_tenant = Tenant(
        name=f"{user_in.full_name}'s Workspace",
        owner_id=new_user.id
    )
    db.add(new_tenant)
    db.flush()

    # Automatically provision a mock active subscription for local testing/demo
    mock_sub = Subscription(
        tenant_id=new_tenant.id,
        paymenter_subscription_id="mock_sub_demo_123",
        plan_name="pro",
        status="active",
        limits={"mem_limit": "2g", "cpu_quota": 200000}
    )
    db.add(mock_sub)
    db.commit()
    db.refresh(new_user)
    
    return {"message": "User registered successfully", "user_id": new_user.id}

@router.post("/login")
def login(response: Response, user_in: UserLogin, db: Session = Depends(get_db)):
    # Authenticate
    user = db.query(User).filter(User.email == user_in.email).first()
    if not user or not verify_password(user_in.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    
    # Generate tokens
    access_token = create_access_token(subject=user.id)
    refresh_token = create_refresh_token(subject=user.id)
    
    # Set HTTP-only cookies
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True, # Require HTTPS in prod
        samesite="lax"
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/api/v1/auth/refresh" # Restrict refresh token to refresh endpoint
    )
    
    return {"message": "Login successful"}

@router.post("/refresh")
def refresh_token(request: Request, response: Response, db: Session = Depends(get_db)):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token missing")
        
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
        
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid refresh token payload")
        
    # Verify user still exists and is active
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
        
    # Generate new access token
    access_token = create_access_token(subject=user.id)
    
    # Set new access token cookie
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="lax"
    )
    
    return {"message": "Token refreshed"}

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token", path="/api/v1/auth/refresh")
    return {"message": "Logged out successfully"}

@router.get("/me")
def get_current_user(request: Request, db: Session = Depends(get_db)):
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
        subscription = db.query(Subscription).filter(Subscription.tenant_id == tenant.id).order_by(Subscription.created_at.desc()).first()
        if not subscription:
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

    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "tenant_id": str(tenant.id) if tenant else None,
        "subscription_status": subscription.status if subscription else "none",
        "plan": plan_name
    }
