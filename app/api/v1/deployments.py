from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import uuid

from app.core.database import get_db
from app.models.deployment import Deployment
from app.models.tenant import Tenant
from app.tasks.deployment_tasks import provision_deployment_task
from app.models.subscription import Subscription
from app.api.v1.workers import verify_worker_secret
from app.services.scheduler import scheduler, NoWorkerAvailableError
import redis
from app.core.config import settings

# Ideally this uses Depends(get_current_user) but for brevity assuming auth middleware provides it
# For MVP we will pass tenant_id explicitly (in prod, derive from secure cookie JWT)

router = APIRouter()

class DeploymentCreate(BaseModel):
    tenant_id: str
    name: str
    image: str
    subdomain: str
    specs: dict = {}

class DeploymentResponse(BaseModel):
    id: str
    name: str
    status: str
    subdomain: str

@router.post("/", response_model=DeploymentResponse, status_code=status.HTTP_201_CREATED)
def create_deployment(deploy_in: DeploymentCreate, db: Session = Depends(get_db)):
    # Validate tenant
    tenant = db.query(Tenant).filter(Tenant.id == deploy_in.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Check for active or trialing subscription
    sub = db.query(Subscription).filter(
        Subscription.tenant_id == tenant.id,
        Subscription.status.in_(["active", "trialing"])
    ).first()
    if not sub:
        raise HTTPException(status_code=403, detail="Active subscription required. Please upgrade your plan.")

        
    # Check subdomain uniqueness and auto-recover stale deployments
    existing_dep = db.query(Deployment).filter(Deployment.subdomain == deploy_in.subdomain).first()
    if existing_dep:
        if existing_dep.tenant_id == tenant.id:
            # Auto-purge the user's stale deployment to self-heal
            from app.tasks.deployment_tasks import stop_deployment_task
            from app.core.redis import high_queue
            from app.models.events import DeploymentEvent
            high_queue.enqueue(stop_deployment_task, str(existing_dep.id))
            db.query(DeploymentEvent).filter(DeploymentEvent.deployment_id == existing_dep.id).delete()
            db.delete(existing_dep)
            db.commit()
        else:
            raise HTTPException(status_code=400, detail="Subdomain already in use")
    # Call Scheduler
    cpu_req = 1.0  # Derive from deploy_in.specs in real implementation
    mem_req = 1.0  # Derive from deploy_in.specs in real implementation
    
    try:
        worker = scheduler.select_worker(db, cpu_req=cpu_req, mem_req=mem_req)
    except NoWorkerAvailableError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # Create record in DB (State = scheduled)
    deployment = Deployment(
        tenant_id=tenant.id,
        worker_node_id=worker.id,
        name=deploy_in.name,
        image=deploy_in.image,
        subdomain=deploy_in.subdomain,
        specs=deploy_in.specs,
        status="scheduled"
    )
    db.add(deployment)
    db.commit()
    db.refresh(deployment)

    # Enqueue async job to specific worker queue via Redis
    from rq import Queue
    redis_conn = redis.from_url(settings.REDIS_URL)
    worker_queue = Queue(f"deployments:{worker.id}", connection=redis_conn)
    
    payload = {
        "deployment_id": str(deployment.id),
        "name": f"arimarun-{deployment.id}",
        "image": deployment.image,
        "subdomain": deployment.subdomain,
        "specs": deployment.specs
    }
    
    worker_queue.enqueue(provision_deployment_task, payload, job_timeout=1800)

    return {
        "id": str(deployment.id),
        "name": deployment.name,
        "status": deployment.status,
        "subdomain": deployment.subdomain
    }

@router.get("/{tenant_id}", response_model=List[DeploymentResponse])
def list_deployments(tenant_id: str, db: Session = Depends(get_db)):
    deployments = db.query(Deployment).filter(Deployment.tenant_id == tenant_id).all()
    return [
        {"id": str(d.id), "name": d.name, "status": d.status, "subdomain": d.subdomain}
        for d in deployments
    ]

@router.get("/logs/{deployment_id}")
def get_deployment_logs(deployment_id: str, db: Session = Depends(get_db)):
    from app.models.events import DeploymentEvent
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")

    log_lines = []
    
    # 1. Fetch all DB events
    events = db.query(DeploymentEvent).filter(DeploymentEvent.deployment_id == deployment.id).order_by(DeploymentEvent.created_at.asc()).all()
    for e in events:
        log_lines.append(f"[{e.created_at.strftime('%Y-%m-%d %H:%M:%S')}] [{e.status.upper()}] {e.message}")

    # 2. Fetch container stdout/stderr live via native UNIX socket communication
    try:
        import socket
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect("/var/run/docker.sock")
        s.sendall(f"GET /v1.41/containers/arimarun-{deployment.id}/logs?stdout=1&stderr=1&tail=150 HTTP/1.1\r\nHost: localhost\r\n\r\n".encode())
        
        # Read the full HTTP response
        response = b""
        s.settimeout(0.5) # Avoid hanging
        while True:
            try:
                data = s.recv(4096)
                if not data:
                    break
                response += data
            except socket.timeout:
                break
        s.close()

        # Parse response
        parts = response.decode(errors='ignore').split("\r\n\r\n", 1)
        if len(parts) > 1 and parts[1].strip():
            raw_logs = parts[1]
            if "No such container" not in raw_logs:
                clean_lines = []
                for line in raw_logs.split("\n"):
                    # Strip Docker Multiplexing stream header (8 bytes) if present
                    if len(line) >= 8 and (line[0] in ['\x00', '\x01', '\x02']):
                        clean_lines.append(line[8:])
                    else:
                        clean_lines.append(line)
                
                if clean_lines:
                    log_lines.append("\n--- Container Live Logs (Stdout/Stderr) ---")
                    log_lines.extend(clean_lines)
    except Exception:
        # Docker container does not exist yet or socket is not mounted
        pass

    return {"logs": log_lines}

@router.delete("/{deployment_id}")
def delete_deployment(deployment_id: str, db: Session = Depends(get_db)):
    from app.models.events import DeploymentEvent
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")

    # 1. Enqueue dynamic stop task in background to destroy docker container if running
    from app.tasks.deployment_tasks import stop_deployment_task
    high_queue.enqueue(stop_deployment_task, str(deployment.id))

    # 2. Clear events and deployment record from database
    db.query(DeploymentEvent).filter(DeploymentEvent.deployment_id == deployment.id).delete()
    db.delete(deployment)
    db.commit()

    return {"message": "Workspace stopped and reset successfully"}


class DeploymentStatusUpdate(BaseModel):
    status: str
    message: Optional[str] = None
    container_id: Optional[str] = None
    worker_ip: Optional[str] = None
    port: Optional[int] = None

@router.patch("/{deployment_id}/status")
def update_deployment_status(
    deployment_id: str,
    payload: DeploymentStatusUpdate,
    secret: str = Depends(verify_worker_secret),
    db: Session = Depends(get_db)
):
    """
    Internal endpoint for worker nodes to update deployment status.
    Requires WORKER_SECRET.
    """
    from app.models.events import DeploymentEvent
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")

    valid_statuses = ["pending", "scheduled", "deploying", "provisioning", "running", "failed", "terminated", "stopped"]
    if payload.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of {valid_statuses}")

    deployment.status = payload.status
    if payload.container_id:
        deployment.container_id = payload.container_id

    if payload.status == "running" and payload.worker_ip and payload.port:
        from app.services.routing_service import routing_service
        # Use subdomain or generate one
        domain_name = deployment.subdomain
        routing_service.register_route(domain_name, payload.worker_ip, payload.port)
        
    if payload.status in ["stopped", "failed", "terminated", "deleted"]:
        from app.services.routing_service import routing_service
        routing_service.remove_route(deployment.subdomain)

    event_msg = payload.message or f"Status updated to {payload.status}"
    db.add(DeploymentEvent(deployment_id=deployment.id, status=payload.status, message=event_msg))
    db.commit()

    return {"message": "Status updated successfully"}
