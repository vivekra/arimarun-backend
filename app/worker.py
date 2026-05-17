import sys
import os
from rq import Worker, Connection

# Ensure the app is in the PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.redis import redis_conn

listen = ['high', 'default', 'low']

if __name__ == '__main__':
    with Connection(redis_conn):
        worker = Worker(map(Queue, listen))
        worker.work()
