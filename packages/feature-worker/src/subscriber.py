"""
XREAD polling loop — scan for org streams → poll new entries → featurize → store → repeat.
No consumer groups. Tracks last-seen entry ID per stream in memory.
"""
import json
import logging
import time

from .storage.redis_client import get_redis_client
from .storage.feature_store import store_features
from .inference.featurizer import featurize
from .inference.token_merger import merge_tokens
from .constants import STREAM_NAME

logger = logging.getLogger(__name__)

_features_stored: int = 0
_queue_depth: int = 0
_session_cache: dict[str, tuple[list, float]] = {}
_SESSION_CACHE_TTL = 60
_SESSION_EVENT_TTL = 4 * 3600


def get_stats() -> dict:
    return {"features_stored": _features_stored, "queue_depth": _queue_depth}


def _scan_keys(r, pattern: str) -> list[str]:
    found = []
    cursor = 0
    while True:
        cursor, keys = r.scan(cursor, match=pattern, count=100)
        found.extend(k.decode() if isinstance(k, bytes) else k for k in keys)
        if cursor == 0 or str(cursor) == "0":
            break
    return found


def _accumulate_events(redis, org_id: str, session_id: str, new_events: list) -> list:
    global _session_cache
    key = f"metricade_sess:{org_id}:{session_id}"
    now = time.time()

    cache_entry = _session_cache.get(key)
    if cache_entry:
        cached_events, expiry_ts = cache_entry
        if now < expiry_ts:
            existing = cached_events
        else:
            del _session_cache[key]
            existing_raw = redis.get(key)
            existing = json.loads(existing_raw) if existing_raw else []
    else:
        existing_raw = redis.get(key)
        existing = json.loads(existing_raw) if existing_raw else []

    merged = existing + new_events
    redis.setex(key, _SESSION_EVENT_TTL, json.dumps(merged))
    _session_cache[key] = (merged, now + _SESSION_CACHE_TTL)
    return merged


def _process_entries(redis, stream_key: str, entries: list) -> None:
    global _features_stored, _queue_depth
    _queue_depth = len(entries)
    for entry_id, fields in entries:
        try:
            raw = fields.get("payload") or fields.get(b"payload") or "{}"
            if isinstance(raw, bytes):
                raw = raw.decode()
            enriched = json.loads(raw)
            if isinstance(enriched, list):
                enriched = json.loads(enriched[0]) if isinstance(enriched[0], str) else enriched[0]

            inner_payload = enriched.get("payload", {})
            flush_events = inner_payload.get("events", [])
            first_event = flush_events[0] if flush_events else {}
            org_id = enriched.get("org_id", "unknown")
            session_id = (
                inner_payload.get("session_id")
                or first_event.get("session_id")
                or enriched.get("trace_id", str(entry_id))
            )

            all_events = _accumulate_events(redis, org_id, session_id, flush_events)
            merged_payload = {**inner_payload, "events": all_events}

            features = featurize(merged_payload, enriched)
            merged_cont = merge_tokens(features.cont)

            metadata = {
                "trace_id": enriched.get("trace_id"),
                "received_at": enriched.get("received_at"),
                "hostname": enriched.get("hostname"),
                "client_id": inner_payload.get("client_id"),
                "ip_country": (enriched.get("ip_meta") or {}).get("ip_country"),
                "ip_type": (enriched.get("ip_meta") or {}).get("ip_type"),
                "device_type": (enriched.get("ua_meta") or {}).get("device_type"),
                "is_webview": (enriched.get("ua_meta") or {}).get("is_webview"),
            }

            store_features(redis, org_id, session_id, merged_cont, features.cat, metadata)
            _features_stored += 1
            logger.info("Stored features for session %s (org=%s)", session_id, org_id)
        except Exception as e:
            logger.error("Failed to process entry %s: %s", entry_id, e, exc_info=True)


def run_subscriber():
    global _features_stored, _queue_depth

    redis = get_redis_client()
    known_streams: set[str] = set()
    # last_ids: per-stream cursor — "0" means read from beginning, "$" means only new
    last_ids: dict[str, str] = {}
    loop_count = 0

    logger.info("Subscriber ready — scanning for %s:* streams", STREAM_NAME)

    while True:
        try:
            # Re-discover org streams every 10 loops (~20s)
            if loop_count % 10 == 0:
                all_keys = set(_scan_keys(redis, f"{STREAM_NAME}:*"))
                new_streams = all_keys - known_streams
                for key in new_streams:
                    logger.info("Discovered new org stream: %s", key)
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
                    # Advance cursor past last processed entry
                    last_ids[stream_key] = entries[-1][0]

        except Exception as e:
            logger.error("Subscriber loop error: %s", e, exc_info=True)
            time.sleep(1)
