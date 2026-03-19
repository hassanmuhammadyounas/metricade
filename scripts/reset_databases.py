"""
Full database reset — wipes all metricade data from Redis and Upstash Vector.
Uses SCAN + DEL (never FLUSHALL). Reads credentials from .env at repo root.

Usage:
    python scripts/reset_databases.py
"""

import os
import sys
import httpx
from pathlib import Path

# Load .env from repo root
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

REDIS_URL    = os.environ.get("UPSTASH_REDIS_URL", "").rstrip("/")
REDIS_TOKEN  = os.environ.get("UPSTASH_REDIS_TOKEN", "")
VECTOR_URL   = os.environ.get("UPSTASH_VECTOR_URL", "").rstrip("/")
VECTOR_TOKEN = os.environ.get("UPSTASH_VECTOR_TOKEN", "")

for var, val in [("UPSTASH_REDIS_URL", REDIS_URL), ("UPSTASH_REDIS_TOKEN", REDIS_TOKEN),
                 ("UPSTASH_VECTOR_URL", VECTOR_URL), ("UPSTASH_VECTOR_TOKEN", VECTOR_TOKEN)]:
    if not val:
        print(f"ERROR: {var} is not set.")
        sys.exit(1)

http = httpx.Client(timeout=30)

def redis_pipeline(cmds):
    r = http.post(f"{REDIS_URL}/pipeline",
                  headers={"Authorization": f"Bearer {REDIS_TOKEN}"},
                  json=cmds)
    r.raise_for_status()
    return r.json()

def redis_cmd(cmd):
    return redis_pipeline([cmd])[0]["result"]

# ── Delete all keys matching pattern ─────────────────────────────────────────

def delete_pattern(pattern):
    deleted = 0
    cursor = "0"
    while True:
        result = redis_cmd(["SCAN", cursor, "MATCH", pattern, "COUNT", "500"])
        cursor = result[0]
        keys = result[1]
        if keys:
            # DEL in batches of 100
            for i in range(0, len(keys), 100):
                batch = keys[i:i+100]
                redis_cmd(["DEL"] + batch)
            deleted += len(keys)
        if cursor == "0":
            break
    return deleted

# ── Main ──────────────────────────────────────────────────────────────────────

patterns = [
    "metricade_stream:*",
    "metricade_features_stream:*",
    "metricade_features:*",
    "metricade_sess:*",
    "metricade_new_sess:*",
    "metricade_client_sessions:*",
    "metricade_label:*",
    "metricade_dlq:*",
]

print("Deleting Redis keys...")
total_deleted = 0
for pattern in patterns:
    n = delete_pattern(pattern)
    print(f"  {pattern:<35} {n:>6,} keys deleted")
    total_deleted += n

# ── Destroy consumer groups ───────────────────────────────────────────────────

print("\nDestroying consumer groups...")
orgs = ["org_3bq2jCKKsVv6", "org_4Cx7UTGz489q"]
groups = [
    ("metricade_stream:{org}",          "feature-worker-group"),
    ("metricade_features_stream:{org}", "model-worker-group"),
]
for org in orgs:
    for stream_tmpl, group in groups:
        stream = stream_tmpl.format(org=org)
        try:
            r = http.post(f"{REDIS_URL}/pipeline",
                          headers={"Authorization": f"Bearer {REDIS_TOKEN}"},
                          json=[["XGROUP", "DESTROY", stream, group]])
            r.raise_for_status()
            result = r.json()
            # result is list; first item may be {"result": N} or {"error": "..."}
            item = result[0] if isinstance(result, list) else result
            if isinstance(item, dict) and "error" in item:
                status = "not found (stream deleted)"
            else:
                status = "destroyed" if (item.get("result") if isinstance(item, dict) else item) else "not found"
        except Exception as e:
            status = f"error: {e}"
        print(f"  {stream} / {group}: {status}")

# ── Reset Upstash Vector ──────────────────────────────────────────────────────

print("\nResetting Upstash Vector...")
r = http.post(f"{VECTOR_URL}/reset",
              headers={"Authorization": f"Bearer {VECTOR_TOKEN}"},
              timeout=30)
if r.is_success:
    print("  Upstash Vector: wiped")
    vector_status = "wiped"
else:
    print(f"  Upstash Vector reset failed: {r.status_code} {r.text}")
    vector_status = "FAILED"

# ── Summary ───────────────────────────────────────────────────────────────────

print(f"""
Reset complete.
  Redis keys deleted: {total_deleted:,}
  Upstash Vector: {vector_status}
  Consumer groups: destroyed

Ready for fresh data collection.
""")
