"""
Redis Streams XREADGROUP loop — consume features → run model → upsert vector → ACK.
Dynamically discovers all metricade_features_stream:{org_id} keys via SCAN.
"""
import logging
import time

from .storage.redis_client import get_redis_client, ensure_consumer_group, ack_message
from .storage.feature_store import load_features
from .storage.vector_client import upsert_vector
from .inference import model_registry
from .constants import FEATURES_STREAM_NAME, CONSUMER_GROUP, CONSUMER_NAME

logger = logging.getLogger(__name__)

# Module-level state
_last_inference_ms: float = 0.0
_queue_depth: int = 0

# Optimization: track streams with consumer groups initialized
_streams_with_groups: set[str] = set()


def get_stats() -> dict:
    return {
        "last_inference_ms": _last_inference_ms,
        "models_loaded": len(model_registry._model_cache),
        "queue_depth": _queue_depth,
    }


def _scan_keys(r, pattern: str) -> list[str]:
    """Return all Redis keys matching pattern."""
    found = []
    cursor = 0
    while True:
        cursor, keys = r.scan(cursor, match=pattern, count=100)
        found.extend(k.decode() if isinstance(k, bytes) else k for k in keys)
        if cursor == 0:
            break
    return found


def _refresh_streams(r, known: set) -> set:
    """Discover org features stream keys and ensure consumer groups exist on all of them."""
    global _streams_with_groups
    all_keys = set(_scan_keys(r, f"{FEATURES_STREAM_NAME}:*"))
    new_streams = all_keys - known
    if new_streams:
        for key in new_streams:
            logger.info("Discovered new org features stream: %s", key)
    # Only ensure consumer group on NEW streams
    for key in new_streams:
        try:
            ensure_consumer_group(r, key, CONSUMER_GROUP)
            _streams_with_groups.add(key)
        except Exception as e:
            logger.warning("Failed to create consumer group on %s: %s", key, e)
    return all_keys


def _claim_idle_pending(r, streams: set) -> dict[str, list]:
    """Re-claim messages idle >60s and return them keyed by stream for immediate processing."""
    pending: dict[str, list] = {}
    for stream_key in streams:
        try:
            pending_info = r.xpending_range(stream_key, CONSUMER_GROUP, "-", "+", 1)
            pending_count = pending_info[0] if pending_info and len(pending_info) > 0 else 0
            if not pending_count or pending_count == 0:
                continue

            result = r.xautoclaim(
                stream_key, CONSUMER_GROUP, CONSUMER_NAME,
                min_idle_time=60000, start_id="0-0", count=10,
            )
            entries = result[1] if result and result[1] else []
            if entries:
                logger.warning("Re-claimed %d idle PEL messages from %s — processing now", len(entries), stream_key)
                pending[stream_key] = entries
        except Exception:
            pass
    return pending


def _decode_field(fields: dict, key: bytes) -> str | None:
    val = fields.get(key)
    if val is None:
        return None
    return val.decode() if isinstance(val, bytes) else str(val)


def _process_entries(redis, stream_key: str, entries: list) -> None:
    global _last_inference_ms, _queue_depth
    _queue_depth = len(entries)
    for entry_id, fields in entries:
        try:
            org_id = _decode_field(fields, b"org_id") or "unknown"
            session_id = _decode_field(fields, b"session_id")
            feature_key = _decode_field(fields, b"feature_key")

            if not session_id or not feature_key:
                logger.warning("Missing session_id or feature_key in stream message %s", entry_id)
                ack_message(redis, stream_key, CONSUMER_GROUP, entry_id)
                continue

            result = load_features(redis, feature_key)
            if result is None:
                logger.warning("Feature key %s not found in Redis — skipping session %s", feature_key, session_id)
                ack_message(redis, stream_key, CONSUMER_GROUP, entry_id)
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
            # Extract remaining metadata fields from stream message
            for key_bytes, meta_key in [
                (b"trace_id", "trace_id"),
                (b"received_at", "received_at"),
                (b"hostname", "hostname"),
                (b"client_id", "client_id"),
                (b"ip_country", "ip_country"),
                (b"ip_type", "ip_type"),
                (b"device_type", "device_type"),
                (b"is_webview", "is_webview"),
            ]:
                val = _decode_field(fields, key_bytes)
                if val is not None:
                    metadata[meta_key] = val

            # Use session_id as vector ID — upsert overwrites on each update → one vector per session
            upsert_vector(session_id, vector, metadata)
            ack_message(redis, stream_key, CONSUMER_GROUP, entry_id)
        except Exception as e:
            logger.error("Failed to process message %s: %s", entry_id, e)


def run_subscriber():
    global _last_inference_ms, _queue_depth

    redis = get_redis_client()

    known_streams: set[str] = set()
    loop_count = 0

    logger.info("Subscriber ready — scanning for %s:* streams", FEATURES_STREAM_NAME)

    while True:
        try:
            # Re-discover org streams every 150 loops (~5 min with 2s block)
            if loop_count % 150 == 0:
                known_streams = _refresh_streams(redis, known_streams)
                reclaimed = _claim_idle_pending(redis, known_streams)
                # Process reclaimed entries immediately
                if reclaimed:
                    for stream_key, entries in reclaimed.items():
                        _process_entries(redis, stream_key, entries)
            loop_count += 1

            if not known_streams:
                time.sleep(2)
                continue

            # XREADGROUP across all discovered org streams simultaneously
            messages = redis.xreadgroup(
                CONSUMER_GROUP, CONSUMER_NAME,
                {s: ">" for s in known_streams},
                count=10, block=2000,
            )

            if not messages:
                continue

            for stream_key, entries in messages:
                stream_key = stream_key.decode() if isinstance(stream_key, bytes) else stream_key
                _process_entries(redis, stream_key, entries)

        except Exception as e:
            logger.error("Subscriber loop error: %s", e)
            time.sleep(1)
