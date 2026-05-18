from fastapi import APIRouter, Depends, HTTPException, Security, Request, status
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import logging

from app.core.database import get_db
from app.core.config import settings
from app.models.worker_node import WorkerNode

logger = logging.getLogger(__name__)

router = APIRouter()

# Security scheme for worker daemon authentication
worker_secret_header = APIKeyHeader(name="X-Worker-Secret", auto_error=True)

def verify_worker_secret(secret: str = Security(worker_secret_header)):
    if secret != settings.WORKER_SECRET:
        raise HTTPException(status_code=403, detail="Invalid worker secret")
    return secret

class HeartbeatPayload(BaseModel):
    hostname: str
    ip_address: str
    cpu_total: float
    cpu_used: float
    memory_total: float
    memory_used: float
    disk_total: float
    disk_used: float
    version: Optional[str] = None
    capabilities: Dict[str, Any] = {}
    is_control_plane: bool = False

@router.post("/heartbeat", response_model=Dict[str, Any], status_code=status.HTTP_200_OK)
def worker_heartbeat(
    payload: HeartbeatPayload,
    secret: str = Depends(verify_worker_secret),
    db: Session = Depends(get_db)
):
    """
    Called periodically by worker nodes to register themselves and update their telemetry.
    Returns the worker_id which the worker daemon uses to listen to its specific RQ queue.
    """
    node = db.query(WorkerNode).filter(WorkerNode.hostname == payload.hostname).first()
    
    role = "control-plane" if payload.is_control_plane else "worker"
    
    if not node:
        logger.info(f"Registering new worker node: {payload.hostname} ({payload.ip_address})")
        node = WorkerNode(
            hostname=payload.hostname,
            ip_address=payload.ip_address,
            role=role,
            status="online",
            cpu_total=payload.cpu_total,
            cpu_used=payload.cpu_used,
            memory_total=payload.memory_total,
            memory_used=payload.memory_used,
            disk_total=payload.disk_total,
            disk_used=payload.disk_used,
            version=payload.version,
            capabilities=payload.capabilities,
            active=True,
            last_heartbeat=datetime.now(timezone.utc)
        )
        db.add(node)
    else:
        # Update existing node
        node.ip_address = payload.ip_address
        node.role = role
        # Only set status to online if it wasn't set to maintenance/draining manually
        if node.status in ["offline"]:
            node.status = "online"
        
        node.cpu_total = payload.cpu_total
        node.cpu_used = payload.cpu_used
        node.memory_total = payload.memory_total
        node.memory_used = payload.memory_used
        node.disk_total = payload.disk_total
        node.disk_used = payload.disk_used
        node.version = payload.version
        
        # Merge capabilities safely
        current_caps = dict(node.capabilities)
        current_caps.update(payload.capabilities)
        node.capabilities = current_caps
        
        node.last_heartbeat = datetime.now(timezone.utc)

    db.commit()
    db.refresh(node)

    return {
        "worker_id": str(node.id),
        "status": node.status,
        "role": node.role
    }
