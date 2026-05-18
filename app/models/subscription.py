"""
Subscription model — one row per purchased product per tenant.

A tenant can have many independent subscriptions (one per product).
paymenter_subscription_id is NULL for trial/free tiers (PostgreSQL allows
multiple NULL values in a unique column, so this is safe).
"""
from sqlalchemy import Column, String, ForeignKey, JSON, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.base import BaseModel


class Subscription(BaseModel):
    __tablename__ = "subscriptions"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)

    # Which product this subscription is for (nullable for legacy rows)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=True)

    # External billing reference — NULL for trial, populated on paid activation
    # unique=True: two tenants cannot share the same Paymenter subscription
    paymenter_subscription_id = Column(String, unique=True, index=True, nullable=True)

    # Denormalised plan label for fast reads without joining Products
    # trialing → starter  |  active → basic / pro / vps-small etc.
    plan_name = Column(String, nullable=False, default="starter")

    # State machine: trialing | active | past_due | suspended | cancelled | expired
    status = Column(String, nullable=False, default="trialing")

    # e.g. "monthly", "yearly", "free_trial"
    billing_cycle = Column(String, nullable=False, default="monthly")

    # Billing lifecycle dates
    started_at   = Column(DateTime(timezone=True), nullable=True)  # When paid period began
    renews_at    = Column(DateTime(timezone=True), nullable=True)  # Next renewal date
    cancel_at    = Column(DateTime(timezone=True), nullable=True)  # Scheduled cancellation

    # Trial period end (NULL for paid plans)
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)

    # Resource limits snapshot (denormalised from Product for quick enforcement)
    # e.g. {"cpu": "1.0", "memory": "1g", "deployments": 2}
    limits = Column(JSON, nullable=False, default=dict)

    # Relationships
    tenant    = relationship("Tenant", back_populates="subscriptions")
    product   = relationship("Product")
    resources = relationship("Resource", back_populates="subscription")
