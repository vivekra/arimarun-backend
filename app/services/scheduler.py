import logging
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from app.models.worker_node import WorkerNode

logger = logging.getLogger(__name__)

class NoWorkerAvailableError(Exception):
    pass

class SchedulerService:
    def __init__(self):
        # Time window before a worker is considered stale/offline
        self.STALE_TIMEOUT_SECONDS = 90

    def select_worker(
        self, 
        db: Session, 
        cpu_req: float, 
        mem_req: float, 
        required_capabilities: Optional[Dict[str, Any]] = None
    ) -> WorkerNode:
        """
        Selects an available worker node that has enough capacity and matching capabilities.
        Implements a simple least-loaded algorithm for now.
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=self.STALE_TIMEOUT_SECONDS)

        # 1. Fetch active, online workers that have recently heartbeated and are NOT control planes
        available_workers = db.query(WorkerNode).filter(
            WorkerNode.active == True,
            WorkerNode.status == "online",
            WorkerNode.role == "worker",
            WorkerNode.last_heartbeat >= cutoff_time
        ).all()

        if not available_workers:
            logger.warning("No active worker nodes found or all are offline.")
            raise NoWorkerAvailableError("No worker nodes available. Please contact support.")

        best_worker = None
        best_score = -1

        for worker in available_workers:
            # Check basic capacity (allow slight overprovisioning or strict limits based on config, here we do strict)
            free_cpu = worker.cpu_total - worker.cpu_used
            free_mem = worker.memory_total - worker.memory_used

            if free_cpu < cpu_req or free_mem < mem_req:
                continue

            # Check capabilities if required (e.g., specific region, GPU)
            if required_capabilities:
                caps_match = all(
                    worker.capabilities.get(k) == v 
                    for k, v in required_capabilities.items()
                )
                if not caps_match:
                    continue

            # Score by most free memory (simple least-loaded strategy)
            if free_mem > best_score:
                best_score = free_mem
                best_worker = worker

        if not best_worker:
            logger.warning(f"Workers available, but none have capacity for {cpu_req} CPU / {mem_req} Mem")
            raise NoWorkerAvailableError("No worker nodes with sufficient capacity. Please contact support.")

        # Optimistic locking / immediate state update could be done here, 
        # but for MVP we rely on the heartbeat catching up quickly.
        return best_worker

scheduler = SchedulerService()
