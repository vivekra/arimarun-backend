"""
Resource model — tracks actual deployed runtime infrastructure.

Bridges billing (Subscription) ↔ runtime (Docker container / VPS).
A tenant can own many independent resources, each on its own billing cycle.
"""
from sqlalchemy import Column, String, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.base import BaseModel


class Resource(BaseModel):
    __tablename__ = "resources"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)

    # The subscription that funds this resource (nullable — trial resources have no paid sub)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id"), nullable=True)

    # mirrors Product.resource_type for quick filtering without a join
    resource_type = Column(String, nullable=False)

    # Runtime identifier (Docker container ID, VPS provider ID, etc.)
    runtime_id = Column(String, nullable=True)

    # Which worker node is hosting this resource
    node_id = Column(String, nullable=True)

    # Status state machine:
    # provisioning | running | stopped | suspended | deleted
    status = Column(String, nullable=False, default="provisioning")

    # Assigned IP or URL for direct customer access
    ip_address = Column(String, nullable=True)

    # Arbitrary runtime metadata (port mappings, image used, etc.)
    metadata = Column(JSON, nullable=True, default=dict)

    # Relationships
    tenant = relationship("Tenant", back_populates="resources")
    subscription = relationship("Subscription", back_populates="resources")
