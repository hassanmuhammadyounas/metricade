# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Pipeline

```
Browser (pixel.js)
  └─> Cloudflare Edge Worker (Hono)       POST /ingest  →  worker.metricade.com
          └─> Upstash Redis Streams        metricade_stream:{org_id}
                  └─> Fly.io Inference Worker  Transformer → 192-dim vector
                          └─> Upstash Vector   cosine similarity, ANN index
                                  └─> Clustering Job  HDBSCAN, run manually
```

All deployments are **manual**. There is no CI/CD.

## Commands

### pixel (`packages/pixel/`)
```bash
npm install
npm run build          # esbuild → dist/pixel.min.js
```
Deploy: `wrangler pages deploy dist --project-name metricade`

### edge-worker (`packages/edge-worker/`)
```bash
npm install
npm run dev            # wrangler dev (local)
npm run type-check     # tsc --noEmit
npm run deploy         # wrangler deploy → worker.metricade.com
```
Secrets (never in wrangler.toml — use CLI):
```bash
wrangler secret put UPSTASH_REDIS_URL
wrangler secret put UPSTASH_REDIS_TOKEN
wrangler secret put INGEST_SHARED_SECRET
```

### inference-worker (`packages/inference-worker/`)
```bash
pip install -r requirements.txt
python -m pytest tests/           # run all tests
python -m pytest tests/test_featurizer.py  # single test file
fly deploy
```
Secrets: `fly secrets set UPSTASH_REDIS_URL=... UPSTASH_REDIS_TOKEN=... UPSTASH_VECTOR_URL=... UPSTASH_VECTOR_TOKEN=...`

### clustering-job (`packages/clustering-job/`)
```bash
pip install -r requirements.txt
python -m pytest tests/
fly machine run       # triggered manually (not on a cron)
```

### infrastructure (`infra/`)
```bash
cp terraform.tfvars.example terraform.tfvars
terraform init && terraform apply
```

## Architecture

### pixel.js
- Vanilla JS IIFE — no framework, no dependencies
- `INGEST_URL` and `INGEST_SECRET` are **baked in at build time** — merchants only configure `orgId`
- Hard stops if `orgId` is missing (`console.error`, pixel does not run)
- Flush payload structure: `{ org_id, trace_id, events[] }` — `org_id` at top level (not inside events)
- Transport: `fetch` with `x-ingest-secret` header when tab visible; `sendBeacon` with `?s=SECRET` query param on page hide (sendBeacon cannot set headers)
- New ad-click IDs → `packages/pixel/src/ad-identifiers.js`; referrer mappings → `packages/pixel/src/referrer-mapping.js`

### edge-worker
- Hono app on Cloudflare Workers
- `/ingest` handles auth inline (supports both header + query param for sendBeacon compatibility) — **not** via the `auth()` middleware
- `/dlq/*` uses `auth()` middleware (header only)
- Stream keys are namespaced: `metricade_stream:{org_id}`, DLQ: `metricade_dlq:{org_id}`
- Enrichment added server-side: IP meta (from Cloudflare `cf` object — free, no external API), UA meta (via `ua-parser-js`), time features (sin/cos encoded + `local_hour`, `is_weekend`)
- `Env` type defined in `src/index.ts` — all bindings declared there

### inference-worker
- Three threads: Redis subscriber, heartbeat writer, HTTP health server (port 8080)
- Loop: `XREADGROUP` → `featurize()` → `model.encode()` → `upsert_vector()` → `XACK`
- Unprocessable messages are left un-ACKed; they redeliver after PEL timeout
- Model file expected at `MODEL_PATH` (default `/models/v1_simclr_trained.pt`); falls back to `BOOTSTRAP_MODEL_PATH` for bootstrap phase
- **Default stream key names in `src/constants.py` are wrong** (`behavioral_stream`, `behavioral_dlq`) — must be overridden via env vars to match `metricade_stream` / `metricade_dlq`

### clustering-job
- Runs to completion (not a long-lived process): fetch vectors → HDBSCAN cluster → assign labels → write labels back to vector metadata → report stats
- Skips if fewer than 10 vectors exist

### Feature vector — critical constraint
`packages/inference-worker/src/inference/featurizer.py` and `packages/shared/constants/feature-list.ts` **must stay in sync**. The featurizer produces a `[64, 51]` float32 tensor (64 events max, 51 features each). Features 18–50 are currently zero-filled reserved slots. When adding a new feature, update both files and keep the index order identical.

### Shared schemas
`packages/shared/schema/` contains JSON Schema files for the event payload, stream message, and vector metadata. These are the contracts between all packages.

## Key constraints

- `org_id` must be present at the top level of every ingest payload — the worker returns 400 if missing
- Redis stream entries contain the full enriched message (ip_meta, ua_meta, time_features, original payload) serialized as a single `payload` field
- The Transformer outputs L2-normalized 192-dim vectors — cosine similarity in Upstash Vector is equivalent to dot product on these vectors
- No test framework is configured for the edge-worker or pixel — tests were removed; add them if needed
