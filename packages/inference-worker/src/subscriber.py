"""
Redis Streams XREADGROUP loop — consume → infer → upsert → ACK.
"""
import json
import logging
import time

from .storage.redis_client import get_redis_client, ensure_consumer_group, ack_message, drain_dlq
from .storage.vector_client import upsert_vector
from .inference.transformer import BehavioralTransformer
from .inference.featurizer import featurize
from .inference.model_loader import load_model
from .constants import STREAM_NAME, CONSUMER_GROUP, CONSUMER_NAME, DLQ_KEY

logger = logging.getLogger(__name__)

# Module-level state
_last_inference_ms: float = 0.0
_queue_depth: int = 0


def get_stats() -> dict:
    return {"last_inference_ms": _last_inference_ms, "queue_depth": _queue_depth}


def run_subscriber():
    global _last_inference_ms, _queue_depth

    redis = get_redis_client()
    ensure_consumer_group(redis, STREAM_NAME, CONSUMER_GROUP)
    model: BehavioralTransformer = load_model()

    logger.info("Subscriber ready — reading from %s/%s", STREAM_NAME, CONSUMER_GROUP)

    while True:
        try:
            # XREADGROUP — block up to 2s waiting for new messages
            messages = redis.xreadgroup(
                CONSUMER_GROUP, CONSUMER_NAME,
                {STREAM_NAME: ">"},
                count=10, block=2000,
            )

            if not messages:
                continue

            for stream_name, entries in messages:
                _queue_depth = len(entries)
                for entry_id, fields in entries:
                    try:
                        payload = json.loads(fields.get(b"payload", b"{}"))
                        t0 = time.perf_counter()
                        features = featurize(payload)
                        vector = model.encode(features)
                        _last_inference_ms = (time.perf_counter() - t0) * 1000
                        upsert_vector(payload.get("trace_id", str(entry_id)), vector, payload)
                        ack_message(redis, STREAM_NAME, CONSUMER_GROUP, entry_id)
                    except Exception as e:
                        logger.error("Failed to process message %s: %s", entry_id, e)
                        # Leave unACKed — will be redelivered after PEL timeout

            # Drain DLQ on each loop — move messages back to stream
            drain_dlq(redis, DLQ_KEY, STREAM_NAME)

        except Exception as e:
            logger.error("Subscriber loop error: %s", e)
            time.sleep(1)
