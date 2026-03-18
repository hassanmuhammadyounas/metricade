"""
XREADGROUP consumer group loop — exactly-once delivery across multiple machines.
Each Fly.io machine gets a unique consumer name (FLY_MACHINE_ID or UUID).
All machines share the same group, so every features stream entry is processed by exactly one machine.
"""
import logging
import os
import time
import uuid

from .storage.redis_client import get_redis_client
from .storage.feature_store import load_features
from .storage.vector_client import upsert_vector
from .inference import model_registry
from .constants import FEATURES_STREAM_NAME, CONSUMER_GROUP

logger = logging.getLogger(__name__)

# Unique per machine — FLY_MACHINE_ID on Fly.io, random UUID locally
CONSUMER_NAME: str = os.environ.get("FLY_MACHINE_ID") or str(uuid.uuid4())

_last_inference_ms: float = 0.0
_queue_depth: int = 0


def get_stats() -> dict:
    return {
        "last_inference_ms": _last_inference_ms,
        "models_loaded": len(model_registry._model_cache),
        "queue_depth": _queue_depth,
    }


def _scan_keys(r, pattern: str) -> list[str]:
    found = []
    cursor = 0
    while True:
        cursor, keys = r.scan(cursor, match=pattern, count=100)
        found.extend(k.decode() if isinstance(k, bytes) else k for k in keys)
        if cursor == 0 or str(cursor) == "0":
            break
    return found


def _get_field(fields: dict, key: str) -> str | None:
    val = fields.get(key)
    if val is None:
        val = fields.get(key.encode() if isinstance(key, str) else key)
    if val is None:
        return None
    return val.decode() if isinstance(val, bytes) else str(val)


def _ensure_consumer_group(redis, stream: str) -> None:
    """Create consumer group with $ (new messages only). No-op if already exists."""
    created = redis.xgroup_create(stream, CONSUMER_GROUP, id="$", mkstream=True)
    if created:
        logger.info("Created consumer group %s on %s", CONSUMER_GROUP, stream)
    else:
        logger.debug("Consumer group %s already exists on %s", CONSUMER_GROUP, stream)


def _process_entries(redis, stream_key: str, entries: list) -> None:
    global _last_inference_ms, _queue_depth
    _queue_depth = len(entries)
    for entry_id, fields in entries:
        try:
            org_id = _get_field(fields, "org_id") or "unknown"
            session_id = _get_field(fields, "session_id")
            feature_key = _get_field(fields, "feature_key")

            if not session_id or not feature_key:
                logger.warning("Missing session_id or feature_key in entry %s", entry_id)
                # Ack malformed entries so they don't block the PEL forever
                redis.xack(stream_key, CONSUMER_GROUP, entry_id)
                continue

            result = load_features(redis, feature_key)
            if result is None:
                logger.warning("Feature key %s not found — skipping session %s", feature_key, session_id)
                # Ack missing features — the feature TTL expired, reprocessing won't help
                redis.xack(stream_key, CONSUMER_GROUP, entry_id)
                continue

            cont, cat = result
            model = model_registry.get_model(org_id)

            t0 = time.perf_counter()
            vector = model.encode(cont, cat)
            _last_inference_ms = (time.perf_counter() - t0) * 1000

            metadata = {
                "org_id": org_id,
                "session_id": session_id,
                "cluster_label": None,
            }
            for key in ["trace_id", "received_at", "hostname", "client_id",
                        "ip_country", "ip_type", "device_type", "is_webview"]:
                val = _get_field(fields, key)
                if val is not None:
                    metadata[key] = val

            upsert_vector(session_id, vector, metadata)
            logger.info("Upserted vector for session %s (org=%s, %.1fms)", session_id, org_id, _last_inference_ms)

            # Ack only after successful vector upsert
            redis.xack(stream_key, CONSUMER_GROUP, entry_id)

        except Exception as e:
            logger.error("Failed to process entry %s: %s", entry_id, e, exc_info=True)
            # Do not ack — will be reclaimed by XAUTOCLAIM after 60s idle


def _reclaim_pending(redis, stream: str) -> None:
    """On startup, reclaim any entries this consumer had in-flight and never acked."""
    try:
        next_id, entries, _ = redis.xautoclaim(
            stream, CONSUMER_GROUP, CONSUMER_NAME, min_idle_ms=60_000, start="0-0", count=50
        )
        if entries:
            logger.info("Reclaimed %d pending entries from %s", len(entries), stream)
            _process_entries(redis, stream, entries)
    except Exception as e:
        logger.warning("XAUTOCLAIM failed for %s: %s", stream, e)


def run_subscriber():
    global _last_inference_ms, _queue_depth

    redis = get_redis_client()
    known_streams: set[str] = set()
    loop_count = 0

    logger.info(
        "Subscriber ready — consumer=%s group=%s scanning for %s:* streams",
        CONSUMER_NAME, CONSUMER_GROUP, FEATURES_STREAM_NAME,
    )

    while True:
        try:
            # Re-discover org streams every 10 loops (~20s)
            if loop_count % 10 == 0:
                all_keys = set(_scan_keys(redis, f"{FEATURES_STREAM_NAME}:*"))
                new_streams = all_keys - known_streams
                for key in new_streams:
                    logger.info("Discovered new org features stream: %s", key)
                    _ensure_consumer_group(redis, key)
                    _reclaim_pending(redis, key)
                known_streams = all_keys
            loop_count += 1

            if not known_streams:
                time.sleep(2)
                continue

            # XREADGROUP with ">" — only undelivered messages
            messages = redis.xreadgroup(
                group=CONSUMER_GROUP,
                consumer=CONSUMER_NAME,
                streams={k: ">" for k in known_streams},
                count=50,
            )

            if not messages:
                time.sleep(1)
                continue

            for stream_key, entries in messages:
                stream_key = stream_key.decode() if isinstance(stream_key, bytes) else stream_key
                if entries:
                    _process_entries(redis, stream_key, entries)

        except Exception as e:
            logger.error("Subscriber loop error: %s", e, exc_info=True)
            time.sleep(1)
