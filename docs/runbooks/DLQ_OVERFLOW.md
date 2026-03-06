# Runbook: DLQ > 10,000 Messages

**Trigger:** DLQ count exceeds 10,000 (sustained worker outage)

## Assessment

Check `LLEN behavioral_dlq` and `LINDEX behavioral_dlq 0` in the Upstash Redis console.

Determine: how old is the oldest message? If > 24 hours, data may be stale.

## Option A — Worker recovered, drain normally

1. Verify worker is healthy: `curl https://behavioral-inference.fly.dev/health`
2. Drain manually in batches via Upstash Redis console: RPOP from `behavioral_dlq`, XADD to `behavioral_stream`. Repeat until `LLEN behavioral_dlq` returns 0.
3. Monitor via `XINFO GROUPS behavioral_stream` -- pending count should decrease.

## Option B — Data too old, discard and move on

Only use this if DLQ messages are > 48 hours old or from a known bad data period.

Record the count (`LLEN behavioral_dlq`) in an audit log, then run `DEL behavioral_dlq` in the Upstash Redis console. Document the incident in a post-mortem.
