"""
Writes fly_worker_heartbeat to Redis every 30s.
The Cloudflare Worker checks this key to decide whether to publish to the stream
or fall back to the DLQ.
"""
import time
import logging

from ..storage.redis_client import get_redis_client
from ..constants import HEARTBEAT_KEY, HEARTBEAT_INTERVAL_S

logger = logging.getLogger(__name__)


def run_heartbeat():
    r = get_redis_client()
    while True:
        try:
            timestamp_ms = int(time.time() * 1000)
            r.set(HEARTBEAT_KEY, str(timestamp_ms), ex=HEARTBEAT_INTERVAL_S * 3)
            logger.debug("Heartbeat written: %d", timestamp_ms)
        except Exception as e:
            logger.error("Heartbeat write failed: %s", e)
        time.sleep(HEARTBEAT_INTERVAL_S)
