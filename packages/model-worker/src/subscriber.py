"""
XREAD polling loop — scan for features streams → poll new entries → run model → upsert vector.
No consumer groups. Tracks last-seen entry ID per stream in memory.
"""
import logging
import time

from .storage.redis_client import get_redis_client
from .storage.feature_store import load_features
from .storage.vector_client import upsert_vector
from .inference import model_registry
from .constants import FEATURES_STREAM_NAME

logger = logging.getLogger(__name__)

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
                continue

            result = load_features(redis, feature_key)
            if result is None:
                logger.warning("Feature key %s not found — skipping session %s", feature_key, session_id)
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
        except Exception as e:
            logger.error("Failed to process entry %s: %s", entry_id, e, exc_info=True)


def run_subscriber():
    global _last_inference_ms, _queue_depth

    redis = get_redis_client()
    known_streams: set[str] = set()
    last_ids: dict[str, str] = {}
    loop_count = 0

    logger.info("Subscriber ready — scanning for %s:* streams", FEATURES_STREAM_NAME)

    while True:
        try:
            # Re-discover org streams every 10 loops (~20s)
            if loop_count % 10 == 0:
                all_keys = set(_scan_keys(redis, f"{FEATURES_STREAM_NAME}:*"))
                new_streams = all_keys - known_streams
                for key in new_streams:
                    logger.info("Discovered new org features stream: %s", key)
                    last_ids[key] = "0"  # read from beginning
                known_streams = all_keys
            loop_count += 1

            if not known_streams:
                time.sleep(2)
                continue

            messages = redis.xread(streams=last_ids, count=50)

            if not messages:
                time.sleep(1)
                continue

            for stream_key, entries in messages:
                stream_key = stream_key.decode() if isinstance(stream_key, bytes) else stream_key
                if entries:
                    _process_entries(redis, stream_key, entries)
                    last_ids[stream_key] = entries[-1][0]

        except Exception as e:
            logger.error("Subscriber loop error: %s", e, exc_info=True)
            time.sleep(1)
