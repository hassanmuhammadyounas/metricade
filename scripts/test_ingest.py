"""
Push a fake flush payload to local Redis stream — simulates what the edge-worker does.
Usage: python scripts/test_ingest.py
"""
import json
import time
import uuid
import redis

ORG_ID = "org_test_local"
SESSION_ID = str(uuid.uuid4())
CLIENT_ID = str(uuid.uuid4())
NOW_MS = int(time.time() * 1000)

payload = {
    "org_id": ORG_ID,
    "client_id": CLIENT_ID,
    "session_id": SESSION_ID,
    "trace_id": f"{SESSION_ID}_1_{NOW_MS}",
    "is_touch": False,
    "browser_timezone": "America/New_York",
    "viewport_w_norm": 0.625,
    "viewport_h_norm": 0.667,
    "is_paid": False,
    "session_source": "google",
    "session_medium": "organic",
    "device_pixel_ratio": 2.0,
    "click_id_type": "none",
    "time_to_first_interaction_ms": 1200,
    "events": [
        {
            "event_type": "page_view",
            "delta_ms": 0,
            "page_path_hash": "13177c2e",
            "page_url": "https://example.com/products/shirt",
        },
        {
            "event_type": "scroll",
            "delta_ms": 800,
            "scroll_velocity_px_s": 320.5,
            "scroll_acceleration": 12.3,
            "scroll_depth_pct": 35,
            "scroll_direction": 1,
            "y_reversal": False,
            "scroll_pause_duration_ms": 0,
        },
        {
            "event_type": "engagement_tick",
            "delta_ms": 5000,
            "active_ms": 5000,
        },
        {
            "event_type": "click",
            "delta_ms": 7200,
            "patch_x": 0.5,
            "patch_y": 0.4,
        },
    ],
}

# Envelope — mirrors what the edge-worker writes to the stream
enriched = {
    "org_id": ORG_ID,
    "trace_id": payload["trace_id"],
    "received_at": NOW_MS,
    "hostname": "example.com",
    "timezone_mismatch": False,
    "prior_session_count": 2,
    "ip_meta": {
        "ip": "1.2.3.4",
        "ip_country": "US",
        "ip_asn": "AS15169",
        "ip_org": "Google LLC",
        "ip_type": "residential",
        "ip_timezone": "America/New_York",
    },
    "ua_meta": {
        "browser_family": "Chrome",
        "browser_version": "120",
        "os_family": "macOS",
        "os_version": "14",
        "device_type": "desktop",
        "device_vendor": "Apple",
        "is_webview": False,
    },
    "time_features": {
        "hour_sin": 0.5,
        "hour_cos": 0.866,
        "dow_sin": 0.434,
        "dow_cos": 0.900,
        "local_hour": 14,
        "is_weekend": False,
    },
    "payload": payload,
}

r = redis.from_url("redis://localhost:6379", decode_responses=False)
stream_key = f"metricade_stream:{ORG_ID}"
entry_id = r.xadd(stream_key, {"payload": json.dumps(enriched)})

print(f"✓ Pushed to {stream_key}")
print(f"  session_id : {SESSION_ID}")
print(f"  entry_id   : {entry_id.decode()}")
print(f"  stream len : {r.xlen(stream_key)}")
