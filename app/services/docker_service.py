import subprocess
import logging
import json

logger = logging.getLogger(__name__)

class DockerService:
    def __init__(self):
        # We now use the Docker CLI directly via subprocess
        pass

    def _run_docker(self, args: list):
        try:
            result = subprocess.run(
                ["docker"] + args,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            logger.error(f"Docker CLI Error: {e.stderr}")
            raise Exception(f"Docker command failed: {e.stderr}")

    def deploy_container(self, name: str, image: str, subdomain: str, mem_limit: str = "512m", cpu_quota: int = 100000) -> tuple:
        """
        Deploys a container using the Docker CLI.
        """
        try:
            logger.info(f"Pulling image {image}")
            self._run_docker(["pull", image])

            logger.info(f"Creating container {name}")
            
            labels = [
                "traefik.enable=true",
                f"traefik.http.routers.{name}.rule=Host(`{subdomain}`)",
                f"traefik.http.routers.{name}.entrypoints=web"
            ]
            
            label_args = []
            for l in labels:
                label_args.extend(["--label", l])

            cmd = [
                "run",
                "-d",
                "--name", name,
                "--memory", mem_limit,
                "--cpu-quota", str(cpu_quota),
                "--cpu-period", "100000",
                "--network", "bridge",
                "-p", "6901",
                "-e", "VNC_PW=password",
                "-e", "VNC_USER=kasm_user",
                "--user", "1000:1000",
                "--restart", "on-failure:3"
            ] + label_args + [image]

            container_id = self._run_docker(cmd)
            
            # Retrieve the dynamic port mapping allocated by Docker Desktop
            try:
                port_info = self._run_docker(["port", name, "6901"])
                allocated_port = port_info.split(":")[-1].strip()
                allocated_subdomain = f"localhost:{allocated_port}"
            except Exception:
                allocated_subdomain = subdomain

            return container_id, allocated_subdomain
        except Exception as e:
            logger.error(f"Failed to deploy container: {str(e)}")
            raise e

    def stop_container(self, container_id: str):
        try:
            self._run_docker(["stop", "-t", "10", container_id])
        except Exception as e:
            logger.warning(f"Failed to stop container {container_id}: {str(e)}")

    def start_container(self, container_id: str):
        try:
            self._run_docker(["start", container_id])
        except Exception as e:
            logger.error(f"Failed to start container {container_id}: {str(e)}")

    def delete_container(self, container_id: str):
        try:
            self._run_docker(["rm", "-f", container_id])
        except Exception:
            pass

docker_service = DockerService()
