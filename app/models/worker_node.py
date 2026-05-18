"""
WorkerNode model — tracks physical/virtual host hypervisors that run customer deployments.
"""
from sqlalchemy import Column, String, Float, Boolean, DateTime, JSON
from app.models.base import BaseModel

class WorkerNode(BaseModel):
    __tablename__ = "worker_nodes"

    # Queue name is derived from this: "deployments:{id}"
    hostname = Column(String, nullable=False, unique=True)
    ip_address = Column(String, nullable=False)
    
    # e.g. "worker", "control-plane"
    role = Column(String, nullable=False, default="worker")
    
    # "online", "offline", "maintenance", "draining"
    status = Column(String, nullable=False, default="offline")
    
    # Telemetry
    cpu_total = Column(Float, nullable=False, default=0.0)
    cpu_used = Column(Float, nullable=False, default=0.0)
    memory_total = Column(Float, nullable=False, default=0.0)
    memory_used = Column(Float, nullable=False, default=0.0)
    disk_total = Column(Float, nullable=False, default=0.0)
    disk_used = Column(Float, nullable=False, default=0.0)
    
    # Worker daemon version
    version = Column(String, nullable=True)

    # {"gpu": true, "region": "eu-west-1", "tier": "premium"}
    capabilities = Column(JSON, nullable=False, default=dict)
    
    # Enabled/Disabled by admin
    active = Column(Boolean, nullable=False, default=True)
    
    last_heartbeat = Column(DateTime(timezone=True), nullable=True)
