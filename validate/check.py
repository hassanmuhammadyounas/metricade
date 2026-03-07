#!/usr/bin/env python3
"""
Metricade Full Pipeline Health & Data Integrity Check
=====================================================
Validates every layer of the pipeline from pixel CDN to vector DB,
checks data counts per org, and runs an end-to-end test sending
real sessions through the full pipeline.

Usage:
  python check.py            # full check + end-to-end test
  python check.py --no-e2e   # skip end-to-end test (faster)
"""

import sys
import time
import json
import uuid
import argparse
import requests
from datetime import datetime, timezone

# ── ANSI colours ──────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BLUE   = "\033[94m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

def ok(msg):    print(f"  {GREEN}✓{RESET}  {msg}")
def warn(msg):  print(f"  {YELLOW}⚠{RESET}  {msg}")
def fail(msg):  print(f"  {RED}✗{RESET}  {msg}")
def info(msg):  print(f"  {BLUE}→{RESET}  {msg}")
def cfg(key, val): print(f"  {DIM}  {key:<22}{RESET} {val}")
def header(title):
    print(f"\n{BOLD}{CYAN}{'━'*62}{RESET}")
    print(f"{BOLD}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'━'*62}{RESET}")

# ── Config ────────────────────────────────────────────────────────────────────
PIXEL_CDN_URL    = "https://pixel.metricade.com/pixel.min.js"
INGEST_URL       = "https://worker.metricade.com/ingest"
WORKER_HEALTH    = "https://worker.metricade.com/health"
INFERENCE_HEALTH = "https://behavioral-inference.fly.dev/health"
INGEST_SECRET    = "a2714436ee112adcbd0780a68859a76b1522462984ccad0a3e69cdb86b81331b"
TEST_ORG_ID      = "org_3bq2jCKKsVv6"

REDIS_URL    = "https://singular-fawn-58838.upstash.io"
REDIS_TOKEN  = "AeXWAAIncDIyYThjM2Y1NTMxNDA0MjQ5YjViNGJhMTE0Y2VkZGNiN3AyNTg4Mzg"
VECTOR_URL   = "https://bright-tiger-54944-us1-vector.upstash.io"
VECTOR_TOKEN = "ABYFMGJyaWdodC10aWdlci01NDk0NC11czFhZG1pbk5HTTRObUl4WXpZdE1EWmtaaTAwWkdWbExXRXlaamN0Wm1SaE16TmxZV05pTldSaQ=="

HEARTBEAT_KEY        = "metricade_heartbeat"
HEARTBEAT_TIMEOUT_MS = 60_000
STREAM_PREFIX        = "metricade_stream"
DLQ_PREFIX           = "metricade_dlq"
INGEST_TOTAL_PREFIX  = "metricade_ingest_total"
CONSUMER_GROUP       = "inference_group"

E2E_TEST_COUNT = 3      # sessions to send through the pipeline
E2E_MAX_WAIT_S = 120    # max seconds to wait for vectors to appear
E2E_POLL_S     = 5      # polling interval

# ── State ─────────────────────────────────────────────────────────────────────
_issues = []
_warnings = []

def record_issue(msg):
    _issues.append(msg)

def record_warning(msg):
    _warnings.append(msg)

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

def redis_xpending_count(key: str) -> int:
    """Return number of unACKed (in-flight) messages for the consumer group."""
    try:
        result = redis_one(["XPENDING", key, CONSUMER_GROUP])
        # result: [total, min_id, max_id, [[consumer, count], ...]] or None/error
        if result and isinstance(result, list):
            return int(result[0] or 0)
    except Exception:
        pass
    return 0

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

# ── Vector helpers ────────────────────────────────────────────────────────────
def vector_info() -> dict:
    r = requests.get(
        f"{VECTOR_URL}/info",
        headers={"Authorization": f"Bearer {VECTOR_TOKEN}"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["result"]

def vector_fetch(ids: list) -> list:
    r = requests.post(
        f"{VECTOR_URL}/fetch",
        headers={"Authorization": f"Bearer {VECTOR_TOKEN}", "Content-Type": "application/json"},
        json={"ids": ids, "includeMetadata": True},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["result"]

# ── Section 1: Pixel CDN ──────────────────────────────────────────────────────
def check_pixel():
    header("1 · PIXEL CDN")
    cfg("URL", PIXEL_CDN_URL)
    try:
        r = requests.get(PIXEL_CDN_URL, timeout=10)
        cfg("HTTP status", r.status_code)
        cfg("Content-Type", r.headers.get("Content-Type", "—"))
        cfg("Cache-Control", r.headers.get("Cache-Control", "—"))
        if r.status_code != 200:
            fail(f"pixel.min.js returned HTTP {r.status_code}")
            record_issue(f"Pixel CDN returned {r.status_code}")
            return
        size_kb = len(r.content) / 1024
        ok(f"pixel.min.js reachable  ({len(r.content):,} bytes  /  {size_kb:.1f} KB)")
        if b"__METRICADE_CONFIG__" in r.content:
            ok("Contains METRICADE config hook")
        else:
            warn("__METRICADE_CONFIG__ not found in pixel — may be minified differently")
        if b"x-ingest-secret" in r.content or b"ingest" in r.content.lower():
            ok("Ingest secret / URL baked in")
        else:
            warn("Cannot confirm ingest URL is baked in — check build")
    except Exception as e:
        fail(f"Pixel CDN unreachable: {e}")
        record_issue(f"Pixel CDN unreachable: {e}")

# ── Section 2: Edge Worker ────────────────────────────────────────────────────
def check_edge_worker():
    header("2 · EDGE WORKER  (worker.metricade.com)")
    cfg("Health URL", WORKER_HEALTH)
    cfg("Ingest URL", INGEST_URL)
    cfg("Test org_id", TEST_ORG_ID)

    # /health
    try:
        r = requests.get(WORKER_HEALTH, timeout=10)
        cfg("HTTP status", r.status_code)
        data = r.json()
        if data.get("status") == "ok":
            ok("Health OK")
        else:
            warn(f"Health degraded: {data}")
            record_warning("Edge worker health degraded")
        cfg("status", data.get("status", "—"))
        cfg("version", data.get("version", "—"))
        cfg("environment", data.get("environment", "—"))
        cfg("redis_ping", data.get("redis_ping", "—"))
        for k, v in data.items():
            if k not in ("status", "version", "environment", "redis_ping"):
                cfg(k, v)
    except Exception as e:
        fail(f"/health unreachable: {e}")
        record_issue(f"Edge worker health unreachable: {e}")

    # Auth + ingest smoke test
    try:
        smoke_trace = f"smoke_{uuid.uuid4().hex[:8]}"
        payload = {
            "org_id": TEST_ORG_ID,
            "trace_id": smoke_trace,
            "events": [{"event_type": "init", "ts": int(time.time() * 1000),
                        "client_id": "smoke", "session_id": "smoke",
                        "page_id": "smoke", "page_load_index": 1}],
        }
        r = requests.post(
            INGEST_URL,
            headers={"x-ingest-secret": INGEST_SECRET, "Content-Type": "application/json",
                     "x-trace-id": smoke_trace},
            json=payload,
            timeout=10,
        )
        cfg("Smoke ingest status", r.status_code)
        if r.status_code == 200 and r.json().get("ok"):
            resp = r.json()
            ok(f"Auth accepted  (200 ok:true)")
            cfg("trace_id echoed", resp.get("trace_id", "—"))
        elif r.status_code == 401:
            fail("Auth REJECTED — INGEST_SECRET mismatch between pixel and worker")
            record_issue("Edge worker auth rejected — INGEST_SECRET mismatch")
        else:
            fail(f"Ingest returned {r.status_code}: {r.text[:120]}")
            record_issue(f"Edge worker ingest failed: {r.status_code}")
    except Exception as e:
        fail(f"Ingest request failed: {e}")
        record_issue(f"Edge worker ingest unreachable: {e}")

# ── Section 3: Redis ──────────────────────────────────────────────────────────
def check_redis() -> dict:
    """Returns {'stream_totals': {org: n}, 'dlq_totals': {org: n}, 'ingest_totals': {org: n}}"""
    header("3 · REDIS  (Upstash)")
    cfg("Endpoint", REDIS_URL)
    cfg("Heartbeat key", HEARTBEAT_KEY)
    cfg("Heartbeat timeout", f"{HEARTBEAT_TIMEOUT_MS // 1000}s")
    cfg("Stream prefix", f"{STREAM_PREFIX}:{{org_id}}")
    cfg("DLQ prefix", f"{DLQ_PREFIX}:{{org_id}}")
    cfg("Counter prefix", f"{INGEST_TOTAL_PREFIX}:{{org_id}}")
    result = {"stream_totals": {}, "dlq_totals": {}, "ingest_totals": {}}

    # Heartbeat
    try:
        hb = redis_one(["GET", HEARTBEAT_KEY])
        if hb is None:
            fail("Heartbeat MISSING — inference worker has never connected")
            record_issue("Heartbeat missing")
        else:
            age_s = (int(time.time() * 1000) - int(hb)) / 1000
            last_seen = datetime.fromtimestamp(int(hb) / 1000).strftime("%Y-%m-%d %H:%M:%S")
            if age_s < HEARTBEAT_TIMEOUT_MS / 1000:
                ok(f"Heartbeat fresh  ({age_s:.0f}s ago)")
            else:
                fail(f"Heartbeat STALE  ({age_s:.0f}s ago, threshold {HEARTBEAT_TIMEOUT_MS//1000}s)")
                record_issue(f"Heartbeat stale — inference worker may be down ({age_s:.0f}s)")
            cfg("last heartbeat at", last_seen)
            cfg("age", f"{age_s:.0f}s")
    except Exception as e:
        fail(f"Redis unreachable: {e}")
        record_issue(f"Redis unreachable: {e}")
        return result

    # Streams — use XPENDING (unACKed) not XLEN (historical total, never decreases)
    stream_keys = redis_scan(f"{STREAM_PREFIX}:*")
    if stream_keys:
        for key in stream_keys:
            xlen    = int(redis_one(["XLEN", key]) or 0)
            pending = redis_xpending_count(key)
            org = key[len(STREAM_PREFIX)+1:]
            result["stream_totals"][org] = pending
            if pending > 0:
                warn(f"Stream  {key}  —  {pending} unACKed message(s)  (total in stream: {xlen})")
            else:
                ok(f"Stream  {key}  —  0 unACKed  (total entries: {xlen})")
        total_pending = sum(result["stream_totals"].values())
        if total_pending > 0:
            record_warning(f"{total_pending} stream message(s) not yet ACKed by inference worker")
    else:
        ok("No stream keys found  (streams empty or not yet created)")

    # DLQ
    dlq_keys = redis_scan(f"{DLQ_PREFIX}:*")
    if dlq_keys:
        lens = redis_pipeline([["LLEN", k] for k in dlq_keys])
        for key, length in zip(dlq_keys, lens):
            org = key[len(DLQ_PREFIX)+1:]
            n = int(length or 0)
            result["dlq_totals"][org] = n
            if n > 0:
                warn(f"DLQ     {key}  —  {n} message(s)  (will drain when heartbeat is alive)")
                record_warning(f"DLQ has {n} messages for {org}")
            else:
                ok(f"DLQ     {key}  —  empty")
    else:
        ok("DLQ empty  (no DLQ keys found)")

    # Ingest counters
    ingest_keys = redis_scan(f"{INGEST_TOTAL_PREFIX}:*")
    if ingest_keys:
        totals = redis_pipeline([["GET", k] for k in ingest_keys])
        for key, total in zip(ingest_keys, totals):
            org = key[len(INGEST_TOTAL_PREFIX)+1:]
            n = int(total or 0)
            result["ingest_totals"][org] = n
            info(f"Counter {key}  —  {n} session(s) accepted by edge worker")
    else:
        info("No ingest counters found — deploy edge worker to enable strict tracking")

    return result

# ── Section 4: Inference Worker ───────────────────────────────────────────────
def check_inference():
    header("4 · INFERENCE WORKER  (behavioral-inference.fly.dev)")
    cfg("Health URL", INFERENCE_HEALTH)
    try:
        r = requests.get(INFERENCE_HEALTH, timeout=15)
        cfg("HTTP status", r.status_code)
        if r.status_code == 200:
            data = r.json()
            status = data.get("status", "unknown")
            if status == "ok":
                ok("Health OK")
            else:
                warn(f"Status: {status}")
                record_warning(f"Inference worker status: {status}")
            cfg("status", status)
            cfg("version", data.get("version", "—"))
            cfg("last_inference_ms", f"{data.get('last_inference_ms', 0):.2f} ms")
            cfg("queue_depth", data.get("queue_depth", 0))
            cfg("model", data.get("model", "—"))
            cfg("uptime_s", data.get("uptime_s", "—"))
            # Show any extra fields from the health response
            known = {"status", "version", "last_inference_ms", "queue_depth", "model", "uptime_s"}
            for k, v in data.items():
                if k not in known:
                    cfg(k, v)
        else:
            fail(f"Health returned HTTP {r.status_code}")
            record_issue(f"Inference worker health {r.status_code}")
    except Exception as e:
        fail(f"Inference worker unreachable: {e}")
        record_issue(f"Inference worker unreachable: {e}")

# ── Section 5: Vector DB ──────────────────────────────────────────────────────
def check_vector() -> int:
    header("5 · VECTOR DATABASE  (Upstash Vector)")
    cfg("Endpoint", VECTOR_URL)
    try:
        data = vector_info()
        total   = data.get("vectorCount", 0)
        pending = data.get("pendingVectorCount", 0)
        ok(f"Reachable — {total} vector(s) stored")
        cfg("vectorCount", total)
        cfg("pendingVectorCount", pending)
        cfg("dimension", data.get("dimension", "—"))
        cfg("similarityFunction", data.get("similarityFunction", "—"))
        cfg("indexSize", data.get("indexSize", "—"))
        cfg("namespace", data.get("namespace", "(default)"))
        # Show any extra fields
        known = {"vectorCount", "pendingVectorCount", "dimension", "similarityFunction",
                 "indexSize", "namespace"}
        for k, v in data.items():
            if k not in known:
                cfg(k, v)
        return total
    except Exception as e:
        fail(f"Vector DB unreachable: {e}")
        record_issue(f"Vector DB unreachable: {e}")
        return 0

# ── Section 6: Data Integrity ─────────────────────────────────────────────────
def check_data_integrity(redis_data: dict, vector_total: int):
    header("6 · DATA INTEGRITY")

    ingest_totals = redis_data["ingest_totals"]
    stream_totals = redis_data["stream_totals"]
    dlq_totals    = redis_data["dlq_totals"]

    if not ingest_totals:
        warn("No ingest counters found — deploy edge worker update to enable strict tracking")
        info(f"Current vector count: {vector_total} session(s) stored")
        return

    total_ingested       = sum(ingest_totals.values())
    total_pending_stream = sum(stream_totals.values())   # XPENDING (truly unACKed/stuck)
    total_pending_dlq    = sum(dlq_totals.values())
    # Pipeline gap = sessions sent but not yet vectorized (in stream or being processed)
    # We exclude stream from the formula because XLEN/XPENDING can't distinguish
    # "not yet delivered" from "already vectorized" — latency causes false positives.
    # DLQ is reliable (LLEN = exact count waiting to drain).
    pipeline_gap = total_ingested - vector_total - total_pending_dlq

    print()
    info(f"Sessions accepted by edge worker:  {total_ingested}")
    info(f"Sessions vectorized:               {vector_total}")
    info(f"Sessions in DLQ:                   {total_pending_dlq}")
    if total_pending_stream > 0:
        info(f"UnACKed in stream (stuck/PEL):     {total_pending_stream}")
    print()

    if pipeline_gap < 0:
        # More vectors than ingested — historical data before counter was added
        warn(f"Vector count ({vector_total}) exceeds ingest counter ({total_ingested})")
        info("Expected if ingest counter was added after data was already collected")
    elif pipeline_gap == 0:
        ok(f"DATA INTEGRITY OK — {total_ingested} sent == {vector_total} vectorized + {total_pending_dlq} DLQ (0 lost)")
    else:
        # Gap > 0: sessions are in the pipeline but not yet vectorized (normal latency)
        info(f"{pipeline_gap} session(s) still in pipeline (queued for inference)")
        if total_pending_stream > 0:
            warn(f"{total_pending_stream} message(s) unACKed in stream — may be stuck")
            record_warning(f"{total_pending_stream} unACKed stream message(s) — inference worker may be stuck")

    # Per-org breakdown
    all_orgs = set(list(ingest_totals.keys()) + list(stream_totals.keys()) + list(dlq_totals.keys()))
    if len(all_orgs) > 1:
        print()
        info("Per-org breakdown:")
        for org in sorted(all_orgs):
            ingested = ingest_totals.get(org, 0)
            in_vector = "?"  # can't easily query per-org without scanning all vectors
            in_stream = stream_totals.get(org, 0)
            in_dlq    = dlq_totals.get(org, 0)
            info(f"  [{org}]  ingested={ingested}  stream={in_stream}  dlq={in_dlq}")

# ── Section 7: End-to-End Test ────────────────────────────────────────────────
def run_e2e_test():
    header("7 · END-TO-END TEST")
    info(f"Sending {E2E_TEST_COUNT} synthetic session(s) through the full pipeline...")

    # Baseline — record vectors AND pending stream so we can account for both
    try:
        baseline = vector_info().get("vectorCount", 0)
        info(f"Vector count before test: {baseline}")
    except Exception as e:
        fail(f"Cannot read vector baseline: {e}")
        record_issue("E2E test aborted — vector DB unreachable")
        return

    # How many messages are truly unACKed (in-flight) before we send E2E sessions?
    try:
        pre_pending = sum(redis_xpending_count(k) for k in redis_scan(f"{STREAM_PREFIX}:*"))
    except Exception:
        pre_pending = 0
    if pre_pending:
        info(f"Pre-existing unACKed messages: {pre_pending} (will be included in expected vector increase)")

    # Send test sessions
    trace_ids = []
    sent = 0
    for i in range(E2E_TEST_COUNT):
        trace_id = f"e2e_{uuid.uuid4().hex[:12]}"
        trace_ids.append(trace_id)
        ts = int(time.time() * 1000)
        payload = {
            "org_id": TEST_ORG_ID,
            "trace_id": trace_id,
            "events": [
                {"event_type": "init",       "ts": ts,       "client_id": f"e2e_{i}", "session_id": f"e2e_{i}", "page_id": "e2e", "page_load_index": 1},
                {"event_type": "scroll",     "ts": ts + 500, "client_id": f"e2e_{i}", "session_id": f"e2e_{i}", "page_id": "e2e", "page_load_index": 1,
                 "delta_ms": 500, "scroll_velocity_px_s": 400, "scroll_depth_pct": 20},
                {"event_type": "tab_hidden", "ts": ts + 8000, "client_id": f"e2e_{i}", "session_id": f"e2e_{i}", "page_id": "e2e", "page_load_index": 1,
                 "delta_ms": 7500},
            ],
        }
        try:
            r = requests.post(
                INGEST_URL,
                headers={"x-ingest-secret": INGEST_SECRET, "Content-Type": "application/json", "x-trace-id": trace_id},
                json=payload,
                timeout=10,
            )
            if r.status_code == 200 and r.json().get("ok"):
                sent += 1
                info(f"  Sent session {i+1}/{E2E_TEST_COUNT}  trace_id={trace_id}")
            elif r.status_code == 401:
                fail("Auth rejected — stopping E2E test")
                record_issue("E2E test failed — auth rejected")
                return
            else:
                fail(f"  Session {i+1} rejected: {r.status_code}  {r.text[:100]}")
        except Exception as e:
            fail(f"  Session {i+1} failed: {e}")

    if sent == 0:
        fail("No sessions accepted — E2E test cannot proceed")
        record_issue("E2E test failed — edge worker rejected all sessions")
        return

    info(f"Sent {sent}/{E2E_TEST_COUNT} — polling vector DB every {E2E_POLL_S}s (max {E2E_MAX_WAIT_S}s)...")

    # Poll until all trace_ids appear in vector DB
    start = time.time()
    deadline = start + E2E_MAX_WAIT_S
    found_count = 0
    last_print_len = 0

    while time.time() < deadline:
        time.sleep(E2E_POLL_S)
        elapsed = int(time.time() - start)
        try:
            results = vector_fetch(trace_ids)
            found_count = sum(1 for r in results if r is not None)
            msg = f"  [{elapsed:3d}s]  Vectors found: {found_count}/{sent}"
            print(f"\r{msg:{last_print_len}}", end="", flush=True)
            last_print_len = max(last_print_len, len(msg))
            if found_count == sent:
                break
        except Exception:
            pass

    print()  # newline after \r

    elapsed = int(time.time() - start)
    if found_count == sent:
        ok(f"E2E PASS  ✓  all {sent} session(s) found in vector DB  ({elapsed}s)")
    elif found_count > 0:
        warn(f"E2E PARTIAL  —  {found_count}/{sent} found after {elapsed}s (inference still catching up?)")
        record_warning(f"E2E partial: {found_count}/{sent} sessions found after {elapsed}s")
    else:
        fail(f"E2E FAIL  ✗  0/{sent} sessions found after {E2E_MAX_WAIT_S}s")
        record_issue(f"E2E failed — sessions sent but never appeared in vector DB after {E2E_MAX_WAIT_S}s")

    # Confirm exact vector count increase (accounting for pre-existing pending messages)
    try:
        new_total = vector_info().get("vectorCount", 0)
        increase  = new_total - baseline
        expected  = sent + pre_pending
        concurrent = increase - sent
        info(f"Vector count after test: {new_total}  (increased by {increase})")
        if increase >= sent:
            ok(f"All {sent} E2E session(s) produced vectors" +
               (f"  (+{concurrent} concurrent from other sessions)" if concurrent > 0 else ""))
        else:
            lost_count = sent - increase
            fail(f"DATA INTEGRITY: sent {sent} E2E sessions but only {increase} vectors created — {lost_count} lost")
            record_issue(f"DATA INTEGRITY: {lost_count} E2E session(s) did not produce vectors")
    except Exception:
        pass

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Metricade pipeline health check")
    parser.add_argument("--no-e2e", action="store_true", help="Skip end-to-end test")
    args = parser.parse_args()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{BOLD}{'═'*62}")
    print(f"  METRICADE PIPELINE HEALTH CHECK")
    print(f"  {now}")
    print(f"{'═'*62}{RESET}")

    check_pixel()
    check_edge_worker()
    redis_data   = check_redis()
    check_inference()
    vector_total = check_vector()
    check_data_integrity(redis_data, vector_total)

    if not args.no_e2e:
        header("7 · END-TO-END TEST")
        print(f"\n  Send {E2E_TEST_COUNT} synthetic session(s) through the full pipeline? [y/N] ", end="", flush=True)
        try:
            answer = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"
        if answer == "y":
            run_e2e_test()
        else:
            info("E2E test skipped.")

    # ── Summary ───────────────────────────────────────────────────────────────
    header("SUMMARY")
    if not _issues and not _warnings:
        print(f"\n{GREEN}{BOLD}  ✓  ALL CHECKS PASSED — pipeline is healthy{RESET}\n")
    else:
        if _issues:
            print(f"\n{RED}{BOLD}  FAILURES:{RESET}")
            for issue in _issues:
                print(f"  {RED}✗{RESET}  {issue}")
        if _warnings:
            print(f"\n{YELLOW}{BOLD}  WARNINGS:{RESET}")
            for w in _warnings:
                print(f"  {YELLOW}⚠{RESET}  {w}")
        print()
        if _issues:
            sys.exit(1)


if __name__ == "__main__":
    main()
