from sqlalchemy import Column, String, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.base import BaseModel

class DeploymentEvent(BaseModel):
    __tablename__ = "deployment_events"

    deployment_id = Column(UUID(as_uuid=True), ForeignKey("deployments.id"), nullable=False)
    status = Column(String, nullable=False)
    message = Column(String, nullable=True)

    # Relationships
    deployment = relationship("Deployment", back_populates="events")

class WebhookEvent(BaseModel):
    __tablename__ = "webhook_events"

    event_id = Column(String, unique=True, index=True, nullable=False) # ID from Paymenter to ensure idempotency
    event_type = Column(String, nullable=False)
    payload = Column(JSON, nullable=False)
    processing_status = Column(String, nullable=False, default="pending") # pending, processed, failed
    error_message = Column(String, nullable=True)

class ApiToken(BaseModel):
    __tablename__ = "api_tokens"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    token_hash = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    expires_at = Column(String, nullable=True) # datetime string or proper datetime column
