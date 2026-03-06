# Runbook: Cloudflare Worker Rollback (< 2 minutes)

**Trigger:** Worker error rate > 1% after deploy (`worker-error-rate` alert)

## Step 1 — Confirm the error

From `packages/edge-worker/`, run `wrangler tail` to stream live Worker logs.

Look for 5xx errors or exceptions in the live log stream.

## Step 2 — Rollback immediately

From `packages/edge-worker/`:
```
wrangler rollback
```

This reverts to the previous deployed version. Takes ~10 seconds.

## Step 3 — Verify recovery

```
curl https://your-domain.com/api/behavioral/health
```

## Step 4 — Check DLQ

During the bad deploy, some requests may have failed before reaching Redis. Check `LLEN behavioral_dlq` in the Upstash Redis console.

## Step 5 — Root cause

Review the failed deploy changes. Fix the issue. Redeploy only after the fix is confirmed in `wrangler dev` local testing.
