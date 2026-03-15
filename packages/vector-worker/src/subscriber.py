"""
Redis Streams XREADGROUP loop — consume → infer → upsert → ACK.
Dynamically discovers all metricade_stream:{org_id} keys via SCAN.
"""
import json
import logging
import os
import time

from .storage.redis_client import get_redis_client, ensure_consumer_group, ack_message
from .storage.vector_client import upsert_vector
from .inference.transformer import BehavioralTransformer
from .inference.featurizer import featurize
from .inference.model_loader import load_model
from .constants import STREAM_NAME, CONSUMER_GROUP, CONSUMER_NAME

logger = logging.getLogger(__name__)

# Module-level state
_last_inference_ms: float = 0.0
_queue_depth: int = 0

# Optimization: track streams with consumer groups initialized
_streams_with_groups: set[str] = set()

# Optimization: in-memory cache for session data to reduce Redis GETs
_session_cache: dict[str, tuple[list, float]] = {}  # key -> (events, expiry_ts)
_SESSION_CACHE_TTL = 60  # Cache sessions for 60 seconds in memory


def get_stats() -> dict:
    return {"last_inference_ms": _last_inference_ms, "queue_depth": _queue_depth}


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
    """Discover org stream keys and ensure consumer groups exist on all of them."""
    global _streams_with_groups
    all_keys = set(_scan_keys(r, f"{STREAM_NAME}:*"))
    new_streams = all_keys - known
    if new_streams:
        for key in new_streams:
            logger.info("Discovered new org stream: %s", key)
    # Only ensure consumer group on NEW streams (optimization: skip known streams)
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
            # Optimization: check XPENDING first — only XAUTOCLAIM if there are pending messages
            pending_info = r.xpending_range(stream_key, CONSUMER_GROUP, "-", "+", 1)
            pending_count = pending_info[0] if pending_info and len(pending_info) > 0 else 0
            if not pending_count or pending_count == 0:
                continue  # No pending messages, skip expensive XAUTOCLAIM

            result = r.xautoclaim(
                stream_key, CONSUMER_GROUP, CONSUMER_NAME,
                min_idle_time=60000, start_id="0-0", count=10,
            )
            # result: (next_id, [(entry_id, fields), ...], deleted_ids)
            entries = result[1] if result and result[1] else []
            if entries:
                logger.warning("Re-claimed %d idle PEL messages from %s — processing now", len(entries), stream_key)
                pending[stream_key] = entries
        except Exception:
            pass  # Redis < 6.2 or stream not yet created
    return pending



_SESSION_EVENT_TTL = 4 * 3600  # 4 hours — auto-expire abandoned session accumulators


def _accumulate_events(redis, org_id: str, session_id: str, new_events: list) -> list:
    """Merge new events into the per-session accumulator in Redis, return full event list."""
    global _session_cache
    key = f"metricade_sess:{org_id}:{session_id}"
    now = time.time()

    # Check in-memory cache first (optimization: avoid Redis GET on hot sessions)
    cache_entry = _session_cache.get(key)
    if cache_entry:
        cached_events, expiry_ts = cache_entry
        if now < expiry_ts:
            existing = cached_events
        else:
            # Cache expired, remove it
            del _session_cache[key]
            existing_raw = redis.get(key)
            existing = json.loads(existing_raw) if existing_raw else []
    else:
        # Not in cache, fetch from Redis
        existing_raw = redis.get(key)
        existing = json.loads(existing_raw) if existing_raw else []

    merged = existing + new_events
    redis.setex(key, _SESSION_EVENT_TTL, json.dumps(merged))

    # Update in-memory cache
    _session_cache[key] = (merged, now + _SESSION_CACHE_TTL)

    return merged


def _cleanup_session_cache():
    """Remove expired entries from in-memory session cache."""
    global _session_cache
    now = time.time()
    expired_keys = [k for k, (_, expiry) in _session_cache.items() if now >= expiry]
    for k in expired_keys:
        del _session_cache[k]
    if expired_keys:
        logger.debug("Cleaned up %d expired session cache entries", len(expired_keys))


def _process_entries(redis, stream_key: str, entries: list, model: "BehavioralTransformer") -> None:
    global _last_inference_ms, _queue_depth
    _queue_depth = len(entries)
    for entry_id, fields in entries:
        try:
            enriched = json.loads(fields.get(b"payload", b"{}"))
            if isinstance(enriched, list):
                enriched = json.loads(enriched[0]) if isinstance(enriched[0], str) else enriched[0]
            inner_payload = enriched.get("payload", {})
            flush_events = inner_payload.get("events", [])
            first_event = flush_events[0] if flush_events else {}
            org_id = enriched.get("org_id", "unknown")
            session_id = inner_payload.get("session_id") or first_event.get("session_id") or enriched.get("trace_id", str(entry_id))

            # Accumulate events across flushes so the vector covers the full session
            all_events = _accumulate_events(redis, org_id, session_id, flush_events)
            merged_payload = {**inner_payload, "events": all_events}

            t0 = time.perf_counter()
            features = featurize(merged_payload, enriched)
            vector = model.encode(features)
            _last_inference_ms = (time.perf_counter() - t0) * 1000
            meta = {
                "org_id": org_id,
                "trace_id": enriched.get("trace_id"),
                "received_at": enriched.get("received_at"),
                "hostname": enriched.get("hostname"),
                "client_id": inner_payload.get("client_id") or first_event.get("client_id"),
                "session_id": session_id,
                "ip_country": (enriched.get("ip_meta") or {}).get("ip_country"),
                "ip_type": (enriched.get("ip_meta") or {}).get("ip_type"),
                "device_type": (enriched.get("ua_meta") or {}).get("device_type"),
                "is_webview": (enriched.get("ua_meta") or {}).get("is_webview"),
                "cluster_label": None,
            }
            # Use session_id as vector ID — upsert overwrites on each flush → one vector per session
            upsert_vector(session_id, vector, meta)
            ack_message(redis, stream_key, CONSUMER_GROUP, entry_id)
        except Exception as e:
            logger.error("Failed to process message %s: %s", entry_id, e)


def run_subscriber():
    global _last_inference_ms, _queue_depth

    redis = get_redis_client()
    model: BehavioralTransformer = load_model()

    known_streams: set[str] = set()
    loop_count = 0

    logger.info("Subscriber ready — scanning for %s:* streams", STREAM_NAME)

    while True:
        try:
            # Re-discover org streams every 150 loops (~5 min with 2s block) — was 60, increased to reduce Redis scans
            if loop_count % 150 == 0:
                known_streams = _refresh_streams(redis, known_streams)
                reclaimed = _claim_idle_pending(redis, known_streams)
                # Clean up expired session cache entries
                _cleanup_session_cache()
                # Process reclaimed entries immediately (XREADGROUP > won't re-deliver them)
                if reclaimed:
                    for stream_key, entries in reclaimed.items():
                        _process_entries(redis, stream_key, entries, model)
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
                _process_entries(redis, stream_key, entries, model)

        except Exception as e:
            logger.error("Subscriber loop error: %s", e)
            time.sleep(1)
