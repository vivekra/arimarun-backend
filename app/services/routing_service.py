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

            # --------------------------------
            # ROUTER CONFIG
            # --------------------------------

            self.redis_client.set(
                f"traefik/http/routers/{safe_id}/rule",
                rule
            )

            self.redis_client.set(
                f"traefik/http/routers/{safe_id}/service",
                safe_id
            )

            self.redis_client.set(
                f"traefik/http/routers/{safe_id}/entryPoints",
                "websecure"
            )

            self.redis_client.set(
                f"traefik/http/routers/{safe_id}/tls",
                "true"
            )

            self.redis_client.set(
                f"traefik/http/routers/{safe_id}/tls/certResolver",
                "letsencrypt"
            )

            # --------------------------------
            # SERVICE CONFIG
            # --------------------------------

            target_url = f"http://{worker_ip}:{port}"

            self.redis_client.set(
                f"traefik/http/services/{safe_id}/loadBalancer/servers/0/url",
                target_url
            )

            self.redis_client.set(
                f"traefik/http/services/{safe_id}/loadBalancer/passHostHeader",
                "true"
            )

            # --------------------------------
            # SERVER TRANSPORT
            # --------------------------------

            transport_name = f"{safe_id}-transport"

            self.redis_client.set(
                f"traefik/http/services/{safe_id}/loadBalancer/serversTransport",
                transport_name
            )

            # IMPORTANT:
            # Skip TLS verification for Kasm self-signed certs

            self.redis_client.set(
                f"traefik/http/servertransports/{transport_name}/insecureSkipVerify",
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
                f"traefik/http/routers/{safe_id}/entryPoints",
                f"traefik/http/routers/{safe_id}/tls",
                f"traefik/http/routers/{safe_id}/tls/certResolver",

                f"traefik/http/services/{safe_id}/loadBalancer/servers/0/url",
                f"traefik/http/services/{safe_id}/loadBalancer/passHostHeader",
                f"traefik/http/services/{safe_id}/loadBalancer/serversTransport",

                f"traefik/http/servertransports/{transport_name}/insecureSkipVerify",
            ]

            self.redis_client.delete(*keys)

            logger.info(f"Removed route for {subdomain}")

        except Exception as e:
            logger.error(
                f"Failed removing route for {subdomain}: {str(e)}"
            )

routing_service = RoutingService()