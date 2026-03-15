"""
Redis client — consumer group setup, ACK, DLQ drain.
"""
import os
import json
import logging
import redis as redis_lib

logger = logging.getLogger(__name__)


def get_redis_client() -> redis_lib.Redis:
    url = os.environ["UPSTASH_REDIS_URL"]
    token = os.environ["UPSTASH_REDIS_TOKEN"]
    # Upstash Redis uses password auth via token
    return redis_lib.from_url(url, password=token, decode_responses=False)


def ensure_consumer_group(r: redis_lib.Redis, stream: str, group: str) -> None:
    try:
        r.xgroup_create(stream, group, id="0", mkstream=True)
        logger.info("Created consumer group %s on %s", group, stream)
    except redis_lib.exceptions.ResponseError as e:
        if "BUSYGROUP" in str(e):
            logger.debug("Consumer group %s already exists", group)
        else:
            raise


def ack_message(r: redis_lib.Redis, stream: str, group: str, entry_id: bytes) -> None:
    r.xack(stream, group, entry_id)


def drain_dlq(r: redis_lib.Redis, dlq_key: str, stream: str, batch: int = 10) -> int:
    """Move up to `batch` messages from DLQ back to the stream."""
    moved = 0
    for _ in range(batch):
        raw = r.rpop(dlq_key)
        if raw is None:
            break
        try:
            msg = json.loads(raw)
            r.xadd(stream, {"payload": json.dumps(msg)})
            moved += 1
        except Exception as e:
            logger.error("DLQ drain error: %s", e)
    if moved:
        logger.info("Drained %d messages from DLQ back to stream", moved)
    return moved
