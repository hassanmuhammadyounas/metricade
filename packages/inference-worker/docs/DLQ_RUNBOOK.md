# DLQ Runbook

## What to do when DLQ count > 0

### Step 1 — Diagnose

Check DLQ length manually via Upstash Redis console or REST API:
```
GET {UPSTASH_REDIS_URL}/llen/behavioral_dlq
```

### Step 2 — Check worker health
```bash
curl https://behavioral-inference.fly.dev/health
fly status
```

### Step 3 — If worker is down
```bash
# Restart the worker
fly machine restart

# Wait for heartbeat to appear (< 35s)
# Check fly_worker_heartbeat key in Upstash Redis console
```

### Step 4 — Drain DLQ back to stream

Drain manually using the Upstash Redis REST API or console: RPOP from `behavioral_dlq` and XADD to `behavioral_stream` until the queue is empty.

### Step 5 — Monitor

Watch `dlq_count` drop to 0 by checking `LLEN behavioral_dlq` in the Upstash Redis console.

## When to discard instead of drain

Only discard if the DLQ messages are from a period where data quality is known to be bad (e.g. bug in pixel.js that sent malformed events). To discard, run `DEL behavioral_dlq` in the Upstash Redis console -- note the count first for audit purposes.
