import logging
import redis
from app.core.config import settings

logger = logging.getLogger(__name__)

class RoutingService:
    def __init__(self):
        # We use the same redis connection
        self.redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

    def register_route(self, subdomain: str, worker_ip: str, port: int):
        """
        Dynamically registers a Traefik HTTP router and service via Redis provider.
        Assumes Traefik is configured with `providers.redis` pointing to the same Redis instance.
        """
        try:
            # Create a unique, clean identifier for the route
            safe_id = subdomain.replace(".", "-")

            # Route definition: Host(`subdomain.arima.io`) or similar based on `subdomain`
            # The subdomain passed from the API includes the full FQDN (e.g. ws-123.arima.io)
            rule = f"Host(`{subdomain}`)"
            
            # Write Traefik Configuration into Redis keys
            self.redis_client.set(f"traefik/http/routers/{safe_id}/rule", rule)
            self.redis_client.set(f"traefik/http/routers/{safe_id}/service", safe_id)
            
            # Since Traefik runs on port 443 via Let's Encrypt, we might want TLS
            self.redis_client.set(f"traefik/http/routers/{safe_id}/tls", "true")
            self.redis_client.set(f"traefik/http/routers/{safe_id}/tls/certresolver", "letsencrypt")

            # Service definition: Point loadbalancer to worker_ip:port using HTTPS
            target_url = f"https://{worker_ip}:{port}"
            self.redis_client.set(f"traefik/http/services/{safe_id}/loadbalancer/servers/0/url", target_url)

            logger.info(f"Registered Traefik route for {subdomain} -> {target_url} in Redis.")

        except Exception as e:
            logger.error(f"Failed to register Traefik route for {subdomain}: {str(e)}")

    def remove_route(self, subdomain: str):
        """Removes the Traefik route for the given subdomain."""
        try:
            safe_id = subdomain.replace(".", "-")
            keys_to_delete = [
                f"traefik/http/routers/{safe_id}/rule",
                f"traefik/http/routers/{safe_id}/service",
                f"traefik/http/routers/{safe_id}/tls",
                f"traefik/http/routers/{safe_id}/tls/certresolver",
                f"traefik/http/services/{safe_id}/loadbalancer/servers/0/url"
            ]
            self.redis_client.delete(*keys_to_delete)
            logger.info(f"Removed Traefik route for {subdomain} from Redis.")
        except Exception as e:
            logger.error(f"Failed to remove Traefik route for {subdomain}: {str(e)}")

routing_service = RoutingService()
