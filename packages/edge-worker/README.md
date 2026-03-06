# edge-worker — Cloudflare Worker (Hono)

Receives pixel.js event payloads, enriches them with IP geo and UA data, and publishes to Upstash Redis Streams.

## Routes

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/ingest` | None | Main event ingestion |
| `GET` | `/health` | None | Subsystem health check |
| `GET` | `/dlq/status` | Shared secret | DLQ queue depth |

## Local dev

```bash
npm install
wrangler dev
```

## Deploy

All deployment is handled manually. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the full step-by-step checklist.
