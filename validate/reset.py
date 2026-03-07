#!/usr/bin/env python3
"""
Metricade pipeline reset — wipes all data for a clean slate.
Clears Redis streams, DLQs, ingest counters, heartbeat, and all Upstash vectors.

Usage:
  python reset.py             # interactive confirmation
  python reset.py --force     # skip confirmation prompt
  python reset.py --redis     # Redis only (skip vector DB)
  python reset.py --vectors   # Vector DB only (skip Redis)
"""

import sys
import argparse
import requests

# ── ANSI colours ──────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BLUE   = "\033[94m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

def ok(msg):   print(f"  {GREEN}✓{RESET}  {msg}")
def warn(msg): print(f"  {YELLOW}⚠{RESET}  {msg}")
def fail(msg): print(f"  {RED}✗{RESET}  {msg}")
def info(msg): print(f"  {BLUE}→{RESET}  {msg}")

# ── Config ────────────────────────────────────────────────────────────────────
REDIS_URL    = "https://singular-fawn-58838.upstash.io"
REDIS_TOKEN  = "AeXWAAIncDIyYThjM2Y1NTMxNDA0MjQ5YjViNGJhMTE0Y2VkZGNiN3AyNTg4Mzg"
VECTOR_URL   = "https://bright-tiger-54944-us1-vector.upstash.io"
VECTOR_TOKEN = "ABYFMGJyaWdodC10aWdlci01NDk0NC11czFhZG1pbk5HTTRObUl4WXpZdE1EWmtaaTAwWkdWbExXRXlaamN0Wm1SaE16TmxZV05pTldSaQ=="

HEARTBEAT_KEY       = "metricade_heartbeat"
STREAM_PREFIX       = "metricade_stream"
DLQ_PREFIX          = "metricade_dlq"
INGEST_TOTAL_PREFIX = "metricade_ingest_total"

# ── Redis helpers ─────────────────────────────────────────────────────────────
def redis_pipeline(cmds: list) -> list:
    r = requests.post(
        f"{REDIS_URL}/pipeline",
        headers={"Authorization": f"Bearer {REDIS_TOKEN}", "Content-Type": "application/json"},
        json=cmds,
        timeout=10,
    )
    r.raise_for_status()
    return [item.get("result") for item in r.json()]

def redis_one(cmd: list):
    return redis_pipeline([cmd])[0]

def redis_scan(pattern: str) -> list:
    found = []
    cursor = "0"
    while True:
        result = redis_one(["SCAN", cursor, "MATCH", pattern, "COUNT", "100"])
        cursor = str(result[0])
        found.extend(result[1])
        if cursor == "0":
            break
    return found

# ── Reset functions ───────────────────────────────────────────────────────────
def reset_redis() -> dict:
    """Delete all streams, DLQs, ingest counters, and heartbeat. Returns counts."""
    print(f"\n{BOLD}  Scanning Redis keys...{RESET}")
    counts = {"streams": 0, "dlqs": 0, "counters": 0, "heartbeat": 0}

    # Streams
    stream_keys = redis_scan(f"{STREAM_PREFIX}:*")
    if stream_keys:
        lens = redis_pipeline([["XLEN", k] for k in stream_keys])
        total_msgs = sum(int(n or 0) for n in lens)
        redis_pipeline([["DEL", k] for k in stream_keys])
        counts["streams"] = len(stream_keys)
        for key, n in zip(stream_keys, lens):
            ok(f"Deleted stream  {key}  ({int(n or 0)} messages)")
        info(f"Removed {len(stream_keys)} stream(s), {total_msgs} total messages")
    else:
        info("No stream keys found")

    # DLQs
    dlq_keys = redis_scan(f"{DLQ_PREFIX}:*")
    if dlq_keys:
        lens = redis_pipeline([["LLEN", k] for k in dlq_keys])
        total_msgs = sum(int(n or 0) for n in lens)
        redis_pipeline([["DEL", k] for k in dlq_keys])
        counts["dlqs"] = len(dlq_keys)
        for key, n in zip(dlq_keys, lens):
            ok(f"Deleted DLQ     {key}  ({int(n or 0)} messages)")
        info(f"Removed {len(dlq_keys)} DLQ(s), {total_msgs} total messages")
    else:
        info("No DLQ keys found")

    # Ingest counters
    counter_keys = redis_scan(f"{INGEST_TOTAL_PREFIX}:*")
    if counter_keys:
        totals = redis_pipeline([["GET", k] for k in counter_keys])
        redis_pipeline([["DEL", k] for k in counter_keys])
        counts["counters"] = len(counter_keys)
        for key, n in zip(counter_keys, totals):
            ok(f"Deleted counter {key}  (was {int(n or 0)})")
        info(f"Removed {len(counter_keys)} ingest counter(s)")
    else:
        info("No ingest counter keys found")

    # Heartbeat
    hb = redis_one(["GET", HEARTBEAT_KEY])
    if hb is not None:
        redis_one(["DEL", HEARTBEAT_KEY])
        counts["heartbeat"] = 1
        ok(f"Deleted heartbeat key  ({HEARTBEAT_KEY})")
    else:
        info(f"Heartbeat key not present  ({HEARTBEAT_KEY})")

    return counts

def reset_vectors() -> int:
    """Reset (delete all vectors from) Upstash Vector index. Returns deleted count."""
    print(f"\n{BOLD}  Resetting Upstash Vector index...{RESET}")

    # Get current count first
    try:
        info_r = requests.get(
            f"{VECTOR_URL}/info",
            headers={"Authorization": f"Bearer {VECTOR_TOKEN}"},
            timeout=10,
        )
        info_r.raise_for_status()
        before = info_r.json()["result"].get("vectorCount", 0)
        info(f"Vectors before reset: {before}")
    except Exception as e:
        warn(f"Could not read pre-reset count: {e}")
        before = "?"

    # Reset
    r = requests.delete(
        f"{VECTOR_URL}/reset",
        headers={"Authorization": f"Bearer {VECTOR_TOKEN}"},
        timeout=30,
    )
    if r.status_code == 200:
        ok(f"Vector index reset  ({before} vector(s) deleted)")
        return int(before) if isinstance(before, int) else 0
    else:
        fail(f"Vector reset failed: HTTP {r.status_code}  {r.text[:200]}")
        return 0

# ── Preview (dry-run scan) ────────────────────────────────────────────────────
def preview():
    """Scan and report what would be deleted without actually deleting."""
    print(f"\n{BOLD}  Scanning what would be reset...{RESET}\n")
    total_redis_keys = 0

    for prefix, cmd, label in [
        (STREAM_PREFIX,       "XLEN", "stream"),
        (DLQ_PREFIX,          "LLEN", "DLQ"),
        (INGEST_TOTAL_PREFIX, "GET",  "counter"),
    ]:
        keys = redis_scan(f"{prefix}:*")
        if keys:
            results = redis_pipeline([[cmd, k] for k in keys])
            for key, n in zip(keys, results):
                print(f"    {RED}DEL{RESET}  {label:<8}  {key}  ({int(n or 0)} item(s))")
            total_redis_keys += len(keys)
        else:
            print(f"    {DIM}—    {label:<8}  (none){RESET}")

    hb = redis_one(["GET", HEARTBEAT_KEY])
    if hb is not None:
        print(f"    {RED}DEL{RESET}  heartbeat  {HEARTBEAT_KEY}")
        total_redis_keys += 1
    else:
        print(f"    {DIM}—    heartbeat  (not present){RESET}")

    try:
        info_r = requests.get(
            f"{VECTOR_URL}/info",
            headers={"Authorization": f"Bearer {VECTOR_TOKEN}"},
            timeout=10,
        )
        vc = info_r.json()["result"].get("vectorCount", 0)
        print(f"    {RED}DEL{RESET}  vectors    {vc} vector(s) in Upstash Vector index")
    except Exception as e:
        print(f"    {YELLOW}?{RESET}    vectors    (could not read count: {e})")

    print()
    return total_redis_keys

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Metricade pipeline reset")
    parser.add_argument("--force",   action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--redis",   action="store_true", help="Reset Redis only (skip vectors)")
    parser.add_argument("--vectors", action="store_true", help="Reset vectors only (skip Redis)")
    args = parser.parse_args()

    do_redis   = not args.vectors  # reset Redis unless --vectors flag
    do_vectors = not args.redis    # reset vectors unless --redis flag

    print(f"\n{BOLD}{RED}{'═'*62}")
    print(f"  METRICADE PIPELINE RESET")
    print(f"{'═'*62}{RESET}")

    scope_parts = []
    if do_redis:   scope_parts.append("Redis (streams + DLQs + counters + heartbeat)")
    if do_vectors: scope_parts.append("Upstash Vector (all vectors)")
    print(f"\n  Scope: {', '.join(scope_parts)}\n")

    if not args.force:
        preview()
        print(f"  {BOLD}{RED}This is irreversible.{RESET}  Type  {BOLD}yes{RESET}  to continue: ", end="")
        try:
            answer = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)
        if answer != "yes":
            print(f"\n  {YELLOW}Aborted.{RESET}\n")
            sys.exit(0)

    errors = 0

    if do_redis:
        try:
            counts = reset_redis()
        except Exception as e:
            fail(f"Redis reset failed: {e}")
            errors += 1

    if do_vectors:
        try:
            reset_vectors()
        except Exception as e:
            fail(f"Vector reset failed: {e}")
            errors += 1

    print()
    if errors == 0:
        print(f"{GREEN}{BOLD}  ✓  Reset complete — pipeline is now clean.{RESET}\n")
    else:
        print(f"{RED}{BOLD}  ✗  Reset completed with {errors} error(s). Check output above.{RESET}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
