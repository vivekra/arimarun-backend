import logging
import redis
from app.core.config import settings

logger = logging.getLogger(__name__)

class RoutingService:
    def __init__(self):
        self.redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True
        )

    def register_route(self, subdomain: str, worker_ip: str, port: int):
        try:
            safe_id = subdomain.replace(".", "-")

            rule = f"Host(`{subdomain}`)"

            # -------------------------
            # ROUTER CONFIG
            # -------------------------

            self.redis_client.set(
                f"traefik/http/routers/{safe_id}/rule",
                rule
            )

            self.redis_client.set(
                f"traefik/http/routers/{safe_id}/service",
                safe_id
            )

            self.redis_client.set(
                f"traefik/http/routers/{safe_id}/entrypoints",
                "websecure"
            )

            self.redis_client.set(
                f"traefik/http/routers/{safe_id}/tls",
                "true"
            )

            self.redis_client.set(
                f"traefik/http/routers/{safe_id}/tls/certresolver",
                "letsencrypt"
            )

            # -------------------------
            # SERVICE CONFIG
            # -------------------------

            target_url = f"https://{worker_ip}:{port}"

            self.redis_client.set(
                f"traefik/http/services/{safe_id}/loadbalancer/servers/0/url",
                target_url
            )

            # IMPORTANT FOR KASM HTTPS
            self.redis_client.set(
                f"traefik/http/services/{safe_id}/loadbalancer/passhostheader",
                "true"
            )

            # -------------------------
            # SERVER TRANSPORT
            # -------------------------

            transport_name = f"{safe_id}-transport"

            self.redis_client.set(
                f"traefik/http/services/{safe_id}/loadbalancer/serverstransport",
                transport_name
            )

            self.redis_client.set(
                f"traefik/http/serverstransports/{transport_name}/insecureskipverify",
                "true"
            )

            logger.info(
                f"Registered Traefik route: {subdomain} -> {target_url}"
            )

        except Exception as e:
            logger.error(
                f"Failed to register route for {subdomain}: {str(e)}"
            )

    def remove_route(self, subdomain: str):
        try:
            safe_id = subdomain.replace(".", "-")
            transport_name = f"{safe_id}-transport"

            keys = [
                f"traefik/http/routers/{safe_id}/rule",
                f"traefik/http/routers/{safe_id}/service",
                f"traefik/http/routers/{safe_id}/entrypoints",
                f"traefik/http/routers/{safe_id}/tls",
                f"traefik/http/routers/{safe_id}/tls/certresolver",

                f"traefik/http/services/{safe_id}/loadbalancer/servers/0/url",
                f"traefik/http/services/{safe_id}/loadbalancer/passhostheader",
                f"traefik/http/services/{safe_id}/loadbalancer/serverstransport",

                f"traefik/http/serverstransports/{transport_name}/insecureskipverify",
            ]

            self.redis_client.delete(*keys)

            logger.info(f"Removed route for {subdomain}")

        except Exception as e:
            logger.error(
                f"Failed removing route for {subdomain}: {str(e)}"
            )

routing_service = RoutingService()