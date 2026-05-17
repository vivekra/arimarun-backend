from sqlalchemy import Column, String, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.base import BaseModel

class Subscription(BaseModel):
    __tablename__ = "subscriptions"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    paymenter_subscription_id = Column(String, unique=True, index=True, nullable=False)
    plan_name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="active") # active, suspended, cancelled
    limits = Column(JSON, nullable=False, default=dict) # e.g. {"max_containers": 5, "max_ram_gb": 2}

    # Relationships
    tenant = relationship("Tenant", back_populates="subscriptions")
