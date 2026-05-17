from sqlalchemy import Column, String, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.base import BaseModel

class Deployment(BaseModel):
    __tablename__ = "deployments"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    name = Column(String, nullable=False)
    image = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending") # pending, provisioning, running, stopped, suspended, failed, expired, deleting, deleted
    container_id = Column(String, nullable=True) # The actual docker container ID
    subdomain = Column(String, unique=True, index=True, nullable=False)
    specs = Column(JSON, nullable=False, default=dict) # e.g. {"mem_limit": "1g", "nano_cpus": 1000000000}

    # Relationships
    tenant = relationship("Tenant", back_populates="deployments")
    events = relationship("DeploymentEvent", back_populates="deployment", cascade="all, delete-orphan")
