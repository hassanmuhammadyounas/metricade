# Secrets Management

## wrangler.toml (non-sensitive config)

Non-sensitive env vars go in `[vars]` in `wrangler.toml`:
- `STREAM_NAME`, `DLQ_KEY`, `HEARTBEAT_KEY`, `HEARTBEAT_TIMEOUT_S`, `TRACE_HEADER`, `ENVIRONMENT`

## Cloudflare Dashboard / wrangler secret put (sensitive secrets)

Set these via `wrangler secret put <NAME>` — never put values in wrangler.toml or git:

```bash
wrangler secret put UPSTASH_REDIS_URL
wrangler secret put UPSTASH_REDIS_TOKEN
wrangler secret put INGEST_SHARED_SECRET
```

Secrets are encrypted at rest by Cloudflare and injected into the Worker runtime via `env.*`.
