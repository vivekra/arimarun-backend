import logging
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.deployment import Deployment
from app.models.events import DeploymentEvent
from app.services.docker_service import docker_service

logger = logging.getLogger(__name__)

def provision_deployment_task(deployment_id: str):
    db: Session = SessionLocal()
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    
    if not deployment:
        logger.error(f"Deployment {deployment_id} not found")
        db.close()
        return

    try:
        # Update state to provisioning
        deployment.status = "provisioning"
        db.add(DeploymentEvent(deployment_id=deployment.id, status="provisioning", message="Starting provisioning process"))
        db.commit()

        # Parse specs
        mem_limit = deployment.specs.get("mem_limit", "512m")
        cpu_quota = deployment.specs.get("cpu_quota", 100000)

        # Call Docker Service
        container_id, allocated_subdomain = docker_service.deploy_container(
            name=f"arimarun-{deployment.id}",
            image=deployment.image,
            subdomain=deployment.subdomain,
            mem_limit=mem_limit,
            cpu_quota=cpu_quota
        )

        # Update state to running
        deployment.container_id = container_id
        deployment.subdomain = allocated_subdomain
        deployment.status = "running"
        db.add(DeploymentEvent(deployment_id=deployment.id, status="running", message=f"Container {container_id} started successfully"))
        db.commit()

    except Exception as e:
        logger.error(f"Provisioning failed for {deployment_id}: {str(e)}")
        deployment.status = "failed"
        db.add(DeploymentEvent(deployment_id=deployment.id, status="failed", message=str(e)))
        db.commit()
    finally:
        db.close()

def stop_deployment_task(deployment_id: str):
    db: Session = SessionLocal()
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    
    # Forcefully delete container by name to handle hung/unregistered states cleanly
    try:
        docker_service.delete_container(f"arimarun-{deployment_id}")
    except Exception:
        pass

    if not deployment:
        db.close()
        return
        
    try:
        deployment.status = "stopped"
        db.add(DeploymentEvent(deployment_id=deployment.id, status="stopped", message="Container forcefully stopped and reset"))
        db.commit()
    except Exception as e:
        deployment.status = "failed"
        db.add(DeploymentEvent(deployment_id=deployment.id, status="failed", message=str(e)))
        db.commit()
    finally:
        db.close()
