# DLQ Lifecycle

## How messages enter the DLQ

The Cloudflare Worker checks the `fly_worker_heartbeat` Redis key before publishing. If the heartbeat is missing or older than `HEARTBEAT_TIMEOUT_S` (60s), the message is LPUSH'd to `behavioral_dlq` instead of XADD'd to `behavioral_stream`.

## How to drain

After the inference worker has recovered, drain the DLQ manually by running RPOP on `behavioral_dlq` and XADD to `behavioral_stream` for each message. Use the Upstash Redis console or REST API.

## When to discard

Only discard if:
- Messages are from a known bad data period (pixel.js bug, malformed events)
- Messages are > 48 hours old and you've decided the data isn't worth processing
- You've confirmed the vector store doesn't need those sessions

To discard, first record the count (`LLEN behavioral_dlq`) in an audit log, then run `DEL behavioral_dlq` in the Upstash Redis console.

## Scripts

| Script | Action |
|---|---|
| Inspect DLQ | `LLEN behavioral_dlq` + `LRANGE behavioral_dlq 0 -1` in Upstash console |
| Drain DLQ | RPOP each message from `behavioral_dlq`, XADD to `behavioral_stream` |
| Discard DLQ | Note the count, then `DEL behavioral_dlq` in Upstash console |
