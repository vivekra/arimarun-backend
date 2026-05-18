import logging
import requests
import os
from app.services.docker_service import docker_service

logger = logging.getLogger(__name__)

# Fallback envs if not set in worker daemon config
API_BASE_URL = os.environ.get("API_BASE_URL", "http://api:8000")
WORKER_SECRET = os.environ.get("WORKER_SECRET", "change_me_in_production")

def update_status(deployment_id: str, status: str, message: str = None, container_id: str = None, worker_ip: str = None, port: int = None):
    """Securely updates deployment status via the Control Plane API."""
    url = f"{API_BASE_URL}/api/v1/deployments/{deployment_id}/status"
    headers = {"X-Worker-Secret": WORKER_SECRET}
    payload = {"status": status}
    if message:
        payload["message"] = message
    if container_id:
        payload["container_id"] = container_id
    if worker_ip:
        payload["worker_ip"] = worker_ip
    if port is not None:
        payload["port"] = port

    try:
        res = requests.patch(url, json=payload, headers=headers)
        res.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to update status for {deployment_id} to {status}: {e}")

def provision_deployment_task(payload: dict):
    deployment_id = payload.get("deployment_id")
    name = payload.get("name")
    image = payload.get("image")
    subdomain = payload.get("subdomain")
    specs = payload.get("specs", {})

    if not deployment_id:
        logger.error("Deployment ID missing in payload")
        return

    try:
        # Update state to provisioning
        update_status(deployment_id, "provisioning", "Starting provisioning process")

        # Parse specs
        mem_limit = specs.get("mem_limit", "512m")
        cpu_quota = specs.get("cpu_quota", 100000)

        # Call Docker Service
        container_id, worker_ip, port = docker_service.deploy_container(
            name=name,
            image=image,
            subdomain=subdomain,
            mem_limit=mem_limit,
            cpu_quota=cpu_quota
        )

        # Update state to running
        update_status(
            deployment_id, 
            status="running", 
            message=f"Container {container_id} started successfully on {worker_ip}:{port}",
            container_id=container_id,
            worker_ip=worker_ip,
            port=port
        )

    except Exception as e:
        logger.error(f"Provisioning failed for {deployment_id}: {str(e)}")
        update_status(deployment_id, "failed", str(e))

def stop_deployment_task(deployment_id: str):
    """
    Stops and removes the deployment.
    Since we only pass deployment_id here, we assume the container name is arimarun-{deployment_id}.
    """
    try:
        update_status(deployment_id, "stopped", "Stopping workspace container")
        docker_service.delete_container(f"arimarun-{deployment_id}")
        update_status(deployment_id, "terminated", "Workspace container removed")
    except Exception as e:
        logger.error(f"Failed to stop deployment {deployment_id}: {str(e)}")
        # In a real environment we might want to flag it as error, but often deletion is idempotent
