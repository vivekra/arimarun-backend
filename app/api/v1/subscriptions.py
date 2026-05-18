"""
subscriptions.py — Customer billing & product catalog API.

Endpoints:
  GET  /api/v1/subscriptions/products              — public product catalog
  GET  /api/v1/subscriptions/my                    — authenticated user's subscriptions
  GET  /api/v1/subscriptions/pro-rata/{product_id} — pro-rata charge calculation
"""
import logging
from datetime import datetime, timezone
from calendar import monthrange

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.models.product import Product
from app.models.subscription import Subscription
from app.models.tenant import Tenant
from app.models.user import User
from app.security.jwt import decode_token

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_authenticated_user(request: Request, db: Session) -> User:
    """Shared JWT cookie auth helper — raises 401 on failure."""
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def _format_product(p: Product) -> dict:
    return {
        "id":                    str(p.id),
        "name":                  p.name,
        "resource_type":         p.resource_type,
        "monthly_price_pence":   p.monthly_price_pence,
        "monthly_price_display": f"£{p.monthly_price_pence / 100:.2f}",
        "cpu":                   p.cpu,
        "memory":                p.memory,
        "storage_gb":            p.storage_gb,
        "bandwidth_gb":          p.bandwidth_gb,
        "max_instances":         p.max_instances,
        "extra":                 p.extra or {},
    }


# ── GET /products ─────────────────────────────────────────────────────────────
@router.get("/products")
def list_products(db: Session = Depends(get_db)):
    """
    Public endpoint — returns the active product catalog grouped by resource_type.
    Used by the pricing page and upgrade modals.
    """
    logger.info("GET /subscriptions/products")
    products = db.query(Product).filter(Product.is_active == True).order_by(
        Product.resource_type, Product.monthly_price_pence
    ).all()

    grouped: dict = {}
    for p in products:
        rt = p.resource_type
        grouped.setdefault(rt, []).append(_format_product(p))

    return {"products": grouped, "total": len(products)}


# ── GET /my ───────────────────────────────────────────────────────────────────
@router.get("/my")
def my_subscriptions(request: Request, db: Session = Depends(get_db)):
    """
    Returns all subscriptions for the authenticated user with product and
    billing lifecycle details.
    """
    logger.info("GET /subscriptions/my")
    user = _get_authenticated_user(request, db)

    tenant = db.query(Tenant).filter(Tenant.owner_id == user.id).first()
    if not tenant:
        return {"subscriptions": []}

    subs = (
        db.query(Subscription)
        .filter(Subscription.tenant_id == tenant.id)
        .order_by(Subscription.created_at.desc())
        .all()
    )

    result = []
    for s in subs:
        product_data = None
        if s.product_id:
            p = db.query(Product).filter(Product.id == s.product_id).first()
            if p:
                product_data = _format_product(p)

        result.append({
            "id":                          str(s.id),
            "status":                      s.status,
            "plan_name":                   s.plan_name,
            "paymenter_subscription_id":   s.paymenter_subscription_id,
            "trial_ends_at":               s.trial_ends_at.isoformat() if s.trial_ends_at else None,
            "started_at":                  s.started_at.isoformat() if s.started_at else None,
            "renews_at":                   s.renews_at.isoformat() if s.renews_at else None,
            "cancel_at":                   s.cancel_at.isoformat() if s.cancel_at else None,
            "limits":                      s.limits,
            "product":                     product_data,
        })

    return {"subscriptions": result}


# ── GET /pro-rata/{product_id} ────────────────────────────────────────────────
@router.get("/pro-rata/{product_id}")
def calculate_pro_rata(product_id: str, db: Session = Depends(get_db)):
    """
    Calculates the pro-rata charge if a customer purchases this product today.

    Formula:
        days_remaining  = days from today until the last day of this month
        days_in_month   = total days in this calendar month
        pro_rata_pence  = round(monthly_price_pence * days_remaining / days_in_month)

    This is informational only — Paymenter handles the actual charge.
    """
    logger.info(f"GET /subscriptions/pro-rata/{product_id}")

    product = db.query(Product).filter(
        Product.id == product_id, Product.is_active == True
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    now = datetime.now(timezone.utc)
    days_in_month   = monthrange(now.year, now.month)[1]
    days_remaining  = days_in_month - now.day + 1   # inclusive of today

    pro_rata_pence  = round(product.monthly_price_pence * days_remaining / days_in_month)
    full_pence      = product.monthly_price_pence

    logger.info(
        f"Pro-rata calculation — product={product.name} "
        f"days_remaining={days_remaining}/{days_in_month} "
        f"charge=£{pro_rata_pence/100:.2f}"
    )

    return {
        "product_id":             str(product.id),
        "product_name":           product.name,
        "monthly_price_pence":    full_pence,
        "monthly_price_display":  f"£{full_pence / 100:.2f}",
        "pro_rata_pence":         pro_rata_pence,
        "pro_rata_display":       f"£{pro_rata_pence / 100:.2f}",
        "days_remaining":         days_remaining,
        "days_in_month":          days_in_month,
        "calculation_note": (
            f"Charged £{pro_rata_pence/100:.2f} today "
            f"({days_remaining}/{days_in_month} days remaining this month). "
            f"Renews at full £{full_pence/100:.2f}/month from next billing cycle."
        ),
    }
