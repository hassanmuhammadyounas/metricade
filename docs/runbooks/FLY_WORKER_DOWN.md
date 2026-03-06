# Runbook: Fly.io Worker Down

**Trigger:** `heartbeat-missing` alert fires (fly_worker_heartbeat older than 60s)

## Step 1 — Confirm the worker is down

```bash
fly status --app behavioral-inference
curl https://behavioral-inference.fly.dev/health
```

## Step 2 — Check DLQ accumulation

Check `LLEN behavioral_dlq` in the Upstash Redis console.

Events are safe in `behavioral_dlq` — nothing is lost.

## Step 3 — Restart the machine

```bash
fly machine restart --app behavioral-inference
```

Wait 30 seconds, then verify the `fly_worker_heartbeat` key has a recent timestamp in the Upstash Redis console.

## Step 4 — If restart fails, redeploy

```bash
cd packages/inference-worker && fly deploy
```

## Step 5 — Drain DLQ

Once worker is healthy, drain the DLQ manually: RPOP from `behavioral_dlq` and XADD to `behavioral_stream` for each message via Upstash Redis console or REST API.

## Step 6 — Verify stream caught up

Check `XINFO GROUPS behavioral_stream` in the Upstash Redis console. Pending count should reach 0 within a few minutes.
