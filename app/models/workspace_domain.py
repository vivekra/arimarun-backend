"""
WorkspaceDomain model — tracks custom domains and subdomains assigned to deployments.
"""
from sqlalchemy import Column, String, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.base import BaseModel

class WorkspaceDomain(BaseModel):
    __tablename__ = "workspace_domains"

    deployment_id = Column(UUID(as_uuid=True), ForeignKey("deployments.id"), nullable=False)
    
    # e.g., "ws-1234.arima.io" or "mycompany.com"
    domain = Column(String, nullable=False, unique=True, index=True)
    
    # Track if this requires custom certificate provisioning
    custom_cert = Column(Boolean, nullable=False, default=False)
    
    # Whether the routing is actively bound
    active = Column(Boolean, nullable=False, default=True)

    deployment = relationship("Deployment", back_populates="domains")
