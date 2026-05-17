from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.base import BaseModel

class Tenant(BaseModel):
    __tablename__ = "tenants"

    name = Column(String, nullable=False)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # Relationships
    owner = relationship("User", back_populates="tenants")
    subscriptions = relationship("Subscription", back_populates="tenant", cascade="all, delete-orphan")
    deployments = relationship("Deployment", back_populates="tenant", cascade="all, delete-orphan")
