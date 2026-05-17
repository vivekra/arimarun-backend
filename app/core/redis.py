import redis
from rq import Queue
from app.core.config import settings

redis_conn = redis.from_url(settings.REDIS_URL)

# Queues
# High priority for user-initiated actions (start, stop)
high_queue = Queue('high', connection=redis_conn)
# Default priority for background syncing
default_queue = Queue('default', connection=redis_conn)
# Low priority for cleanups
low_queue = Queue('low', connection=redis_conn)
