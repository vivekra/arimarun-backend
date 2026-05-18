import os
import time
import json
import logging
import psutil
import requests
import threading
import subprocess
import socket

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("WorkerDaemon")

API_BASE_URL = os.environ.get("API_BASE_URL", "http://api:8000")
WORKER_SECRET = os.environ.get("WORKER_SECRET", "change_me_in_production")
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
IS_CONTROL_PLANE = os.environ.get("IS_CONTROL_PLANE", "false").lower() == "true"

HOSTNAME = socket.gethostname()
IP_ADDRESS = socket.gethostbyname(HOSTNAME)

# Global worker ID received from control plane
worker_id = None

def get_telemetry():
    """Gathers hardware telemetry via psutil."""
    cpu_total = float(psutil.cpu_count(logical=True))
    cpu_used = float(psutil.cpu_percent(interval=1) / 100.0 * cpu_total)
    
    mem = psutil.virtual_memory()
    mem_total = mem.total / (1024 ** 3) # GB
    mem_used = mem.used / (1024 ** 3)
    
    disk = psutil.disk_usage('/')
    disk_total = disk.total / (1024 ** 3)
    disk_used = disk.used / (1024 ** 3)
    
    # Load capabilities from env if any
    caps_str = os.environ.get("WORKER_CAPABILITIES", "{}")
    try:
        capabilities = json.loads(caps_str)
    except Exception:
        capabilities = {}

    return {
        "hostname": HOSTNAME,
        "ip_address": IP_ADDRESS,
        "cpu_total": round(cpu_total, 2),
        "cpu_used": round(cpu_used, 2),
        "memory_total": round(mem_total, 2),
        "memory_used": round(mem_used, 2),
        "disk_total": round(disk_total, 2),
        "disk_used": round(disk_used, 2),
        "version": "1.1.0",
        "capabilities": capabilities,
        "is_control_plane": IS_CONTROL_PLANE
    }

def heartbeat_loop():
    global worker_id
    url = f"{API_BASE_URL}/api/v1/workers/heartbeat"
    headers = {"X-Worker-Secret": WORKER_SECRET}

    while True:
        try:
            payload = get_telemetry()
            logger.debug(f"Sending heartbeat to {url}: {payload}")
            res = requests.post(url, json=payload, headers=headers, timeout=10)
            res.raise_for_status()
            data = res.json()
            
            if not worker_id:
                worker_id = data.get("worker_id")
                logger.info(f"Registered with Control Plane. Assigned Worker ID: {worker_id}")
                logger.info(f"Role: {data.get('role')}, Status: {data.get('status')}")

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to heartbeat to control plane: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in heartbeat: {e}")

        time.sleep(30)

def main():
    logger.info("Starting Worker Daemon...")
    
    # Start heartbeat thread
    ht = threading.Thread(target=heartbeat_loop, daemon=True)
    ht.start()
    
    # Wait until we get an ID
    logger.info("Waiting for initial registration to acquire Worker ID...")
    while worker_id is None:
        time.sleep(1)
        
    if IS_CONTROL_PLANE:
        logger.info("Running on Control Plane. Worker role disabled. Only running heartbeat.")
        # We just block forever keeping the heartbeat thread alive
        while True:
            time.sleep(3600)
    else:
        queue_name = f"deployments:{worker_id}"
        logger.info(f"Starting RQ Worker listening on queue: {queue_name}")
        
        # Start RQ worker in a subprocess
        cmd = [
            "rq", "worker", 
            "-u", REDIS_URL, 
            queue_name
        ]
        
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"RQ worker exited with code {e.returncode}")
        except KeyboardInterrupt:
            logger.info("Shutting down worker daemon.")

if __name__ == "__main__":
    main()
