"""
Redis client — consumer group setup, ACK, DLQ drain.
Backend: upstash-redis (REST/HTTPS) when URL starts with https://, else redis-py.
"""
import os
import json
import logging

logger = logging.getLogger(__name__)


def get_redis_client():
    url = os.environ["UPSTASH_REDIS_URL"]
    token = os.environ.get("UPSTASH_REDIS_TOKEN", "")
    if url.startswith("https://"):
        from .upstash_rest import UpstashRestClient
        return UpstashRestClient(url=url, token=token)
    else:
        import redis as redis_lib
        kwargs = {"decode_responses": False}
        if token:
            kwargs["password"] = token
        return redis_lib.from_url(url, **kwargs)


def ensure_consumer_group(r, stream: str, group: str) -> None:
    try:
        r.xgroup_create(stream, group, id="0", mkstream=True)
        logger.info("Created consumer group %s on %s", group, stream)
    except Exception as e:
        if "BUSYGROUP" in str(e):
            logger.debug("Consumer group %s already exists", group)
        else:
            raise


def ack_message(r, stream: str, group: str, entry_id) -> None:
    r.xack(stream, group, entry_id)


def drain_dlq(r, dlq_key: str, stream: str, batch: int = 10) -> int:
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
