# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Pipeline

```
Browser (pixel.js)
  └─> Cloudflare Edge Worker (Hono)       POST /ingest  →  worker.metricade.com
          └─> Upstash Redis Streams        metricade_stream:{org_id}
                  └─> Fly.io Inference Worker  Transformer → 192-dim vector
                          └─> Upstash Vector   cosine similarity, keyed by session_id
```

All deployments are **manual**. There is no CI/CD.

---

## Live Deployments

| Component          | URL / Location                                      | Platform              |
|--------------------|-----------------------------------------------------|-----------------------|
| Pixel CDN          | https://pixel.metricade.com/pixel.min.js            | Cloudflare Pages      |
| Edge Worker        | https://worker.metricade.com                        | Cloudflare Workers    |
| Inference Worker   | https://behavioral-inference.fly.dev                | Fly.io (`iad` region) |
| Monitor Worker     | https://monitor.metricade.com                       | Cloudflare Workers    |
| Redis              | https://singular-fawn-58838.upstash.io              | Upstash               |
| Vector DB          | https://bright-tiger-54944-us1-vector.upstash.io    | Upstash Vector        |
| Uptime monitoring  | BetterStack (heartbeat: FhH2PuxmF8ZE5tJs5rZ7fYrx)  | BetterStack           |

---

## Commands

### pixel (`packages/pixel/`)
```bash
npm install
npm run build          # esbuild → dist/pixel.min.js
```
Deploy: `wrangler pages deploy dist --project-name metricade`

Install on a Shopify store (in theme `<head>`):
```html
<script>window.__METRICADE_CONFIG__ = { orgId: 'org_XXXX' };</script>
<script src="https://pixel.metricade.com/pixel.min.js" async></script>
```

### edge-worker (`packages/edge-worker/`)
```bash
cd packages/edge-worker
npm install
npm run dev            # wrangler dev (local)
npm run type-check     # tsc --noEmit
npm run deploy         # wrangler deploy → worker.metricade.com
```
Secrets (never in wrangler.toml — set via CLI):
```bash
wrangler secret put UPSTASH_REDIS_URL
wrangler secret put UPSTASH_REDIS_TOKEN
wrangler secret put INGEST_SHARED_SECRET
```

### inference-worker (`packages/inference-worker/`)
```bash
cd packages/inference-worker
pip install -r requirements.txt
python -m py_compile src/inference/featurizer.py   # syntax check
fly deploy
```
Secrets (set once, persist on Fly):
```bash
fly secrets set \
  UPSTASH_REDIS_URL=... \
  UPSTASH_REDIS_TOKEN=... \
  UPSTASH_VECTOR_URL=... \
  UPSTASH_VECTOR_TOKEN=...
```
Fly config (`fly.toml`):
- App: `behavioral-inference`, region: `iad`, 2 machines
- VM: `shared-cpu-1x`, 512 MB RAM
- Env vars set in `fly.toml` (non-secret): `STREAM_NAME=metricade_stream`, `DLQ_KEY=metricade_dlq`, `HEARTBEAT_KEY=metricade_heartbeat`, `CONSUMER_GROUP=inference_group`, `CONSUMER_NAME=fly_worker_1`, `HEARTBEAT_INTERVAL_S=30`, `VECTOR_DIMS=192`, `MODEL_PATH=/models/v1_simclr_trained.pt`

### monitor-worker (`packages/monitor-worker/`)
```bash
cd packages/monitor-worker
npm install
wrangler deploy        # → monitor.metricade.com
```
Secrets:
```bash
wrangler secret put UPSTASH_REDIS_TOKEN
wrangler secret put UPSTASH_VECTOR_TOKEN
wrangler secret put INGEST_SHARED_SECRET
```
Manual trigger (curl):
```bash
curl -H "x-monitor-secret: <INGEST_SHARED_SECRET>" https://monitor.metricade.com/
```

---

## Testing & Validation

### Full pipeline health check
```bash
cd validate
pip install -r requirements.txt
PYTHONIOENCODING=utf-8 python check.py
```
Checks: pixel CDN, edge worker health, Redis heartbeat, Redis stream (unACKed count), DLQ empty, inference worker health, vector DB reachable, data integrity (sessions accepted == sessions vectorized). Optionally sends E2E synthetic sessions (prompts y/N).

### Reset all data (irreversible)
```bash
cd validate
python reset.py            # interactive — shows preview, asks "yes" to confirm
python reset.py --force    # skip confirmation
python reset.py --redis    # Redis only (streams + DLQs + counters + heartbeat)
python reset.py --vectors  # Upstash Vector only
```
Deletes: all `metricade_stream:*`, `metricade_dlq:*`, `metricade_ingest_total:*` keys, the heartbeat key, and all vectors in the index.

### Inspect live vectors (Python one-liner)
```python
cd validate && python -c "
import check as c, httpx, json
from datetime import datetime, timezone
r = httpx.post(c.VECTOR_URL.rstrip('/')+'/range', headers={'Authorization': f'Bearer {c.VECTOR_TOKEN}'},
               json={'cursor':'0','limit':50,'includeMetadata':True,'includeVectors':False})
for v in r.json().get('result',{}).get('vectors',[]):
    m = v.get('metadata') or {}
    ts = m.get('received_at')
    dt = datetime.fromtimestamp(ts/1000,tz=timezone.utc).strftime('%H:%M:%S UTC') if ts else '?'
    print(dt, m.get('session_id','?')[:36], m.get('ip_country'), m.get('device_type'))
"
```

### Check inference worker logs
```bash
fly logs --app behavioral-inference --no-tail 2>&1 | tail -50
```

---

## Architecture

### pixel.js (`packages/pixel/src/pixel.js`)
- Vanilla JS IIFE — no framework, no dependencies
- `INGEST_URL` and `INGEST_SECRET` are **baked in at build time** via esbuild — merchants only configure `orgId`
- Hard stops if `orgId` is missing (`console.error`, pixel does not run)
- **Identity**: `client_id` persisted in `localStorage` (survives sessions); `session_id` in `sessionStorage` (new per tab/session); `page_id` is a UUID refreshed on each page navigation
- **Flush triggers**: every 10 seconds (`FLUSH_INTERVAL_MS`), or when buffer hits 30 events (`FLUSH_SIZE`), or on `pagehide` (tab close/navigate away)
- **Flush payload structure**: `{ org_id, trace_id, events[] }` — `trace_id` is `{session_id}_{flushCounter}_{timestamp}`
- **Transport**: `fetch` with `x-ingest-secret` header when tab visible; `sendBeacon` with `?s=SECRET` query param on `pagehide` (sendBeacon cannot set headers)
- **Event types emitted**: `init`, `page_view`, `scroll`, `touch_end`, `click`, `tab_hidden`, `tab_visible`
- **`delta_ms`** on each event is computed at push time (`now - lastScrollTs` etc.) — the gap is correctly preserved across flush boundaries
- New ad-click IDs → `packages/pixel/src/ad-identifiers.js`; referrer mappings → `packages/pixel/src/referrer-mapping.js`
- `page_path_hash` is a 32-bit hash of `location.pathname` returned as a **hex string** (`.toString(16)`) — e.g. `"13177c2e"`

### edge-worker (`packages/edge-worker/`)
- Hono app on Cloudflare Workers, deployed to `worker.metricade.com`
- Routes: `POST /ingest` (public, auth inline), `GET /health` (public), `GET /dlq/status` (auth via header)
- `/ingest` supports both `x-ingest-secret` header AND `?s=` query param (for sendBeacon compatibility)
- **Enrichment added server-side before publishing to stream:**
  - `ip_meta`: `{ ip, ip_country, ip_asn, ip_org, ip_type: 'residential'|'datacenter'|'unknown', ip_timezone }` — from Cloudflare `cf` object (free, no external API). `ip_type` is classified by checking ASN against known datacenter/cloud provider list (AWS, GCP, Azure, DO, etc.)
  - `ua_meta`: `{ browser_family, browser_version, os_family, os_version, device_type: 'desktop'|'mobile'|'tablet'|'bot'|'unknown', device_vendor, is_webview }` — via `ua-parser-js`; `is_webview` detected by FBAN/FBAV/Instagram/wv patterns
  - `time_features`: `{ hour_sin, hour_cos, dow_sin, dow_cos, local_hour, is_weekend }` — sin/cos encoded from server clock at time of ingest
  - `timezone_mismatch`: boolean — `ip_meta.ip_timezone !== browser_timezone` from init event
- **Stream key**: `metricade_stream:{org_id}` — namespaced per org. DLQ: `metricade_dlq:{org_id}`
- **Ingest counter**: `INCR metricade_ingest_total:{org_id}` on each accepted payload
- Full enriched message serialized as a single `payload` JSON field in the stream entry
- `Env` type and `Variables` type both defined in `src/index.ts`
- **Default wrangler.toml vars**: `STREAM_NAME=metricade_stream`, `DLQ_KEY=metricade_dlq`, `HEARTBEAT_KEY=metricade_heartbeat`, `HEARTBEAT_TIMEOUT_S=60`, `TRACE_HEADER=x-trace-id`

### inference-worker (`packages/inference-worker/`)
- Three threads: Redis subscriber (`run_subscriber`), heartbeat writer (writes unix timestamp to `metricade_heartbeat` every 30s), HTTP health server (port 8080, `/health` returns JSON)
- **Processing loop** (`src/subscriber.py`):
  1. `XREADGROUP` — deliver new messages from `metricade_stream:{org_id}` (uses `>` cursor)
  2. Accumulate events into `metricade_sess:{org_id}:{session_id}` in Redis (GET + SETEX, 4h TTL)
  3. `featurize(merged_payload, enriched)` — produces `[64, 51]` float32 tensor
  4. `model.encode(features)` — Transformer → L2-normalized 192-dim vector
  5. `upsert_vector(session_id, vector, meta)` — keyed by `session_id` (one vector per session)
  6. `XACK`
- Every 60 loops (~2 min): re-scan for new org streams, run `XAUTOCLAIM` to reclaim idle PEL messages (idle > 60s), drain DLQs back to streams. **Reclaimed messages are processed immediately** (not dropped back into PEL)
- **One vector per session**: vector ID = `session_id`. Multiple flushes from the same session upsert the same slot. Events from all flushes are accumulated in Redis and the vector is updated with the full event sequence on each flush.
- Model file expected at `MODEL_PATH=/models/v1_simclr_trained.pt`; falls back to random initialization (bootstrap phase) if not found
- **`src/constants.py` default values are wrong** (`behavioral_stream`, `behavioral_dlq`) — always overridden by `fly.toml` env vars

### monitor-worker (`packages/monitor-worker/`)
- Cloudflare Worker, deployed to `monitor.metricade.com`
- **Cron**: every hour on the hour (`0 * * * *`)
- **Checks** (all run in parallel): pixel CDN reachable, edge worker `/health` OK, Redis heartbeat fresh (< 60s), DLQ empty, inference worker `/health` OK, vector DB reachable
- Pings BetterStack heartbeat URL **only if ALL checks pass** — absence of ping triggers BetterStack alert
- HTTP fetch handler gated by `x-monitor-secret` header (= `INGEST_SHARED_SECRET`) — all other requests get 404 to prevent bot abuse

---

## Feature Vector — Complete Reference

`packages/inference-worker/src/inference/featurizer.py` produces a `[64, 51]` float32 tensor.
- **64 rows** = up to 64 events per session (zero-padded). Events are the full accumulated sequence across all flushes for the session, oldest first.
- **51 features** per event row — see table below.

All values are normalized to approximately [0, 1] or [-1, 1] before encoding.
String categories are encoded as djb2 hash / 0xFFFFFFFF (normalized to [0, 1]).
`page_path_hash` from pixel.js is a hex string (e.g. `"13177c2e"`) — parsed with `int(val, 16) / 0xFFFFFFFF`.

| Index | Feature | Source | Encoding |
|-------|---------|--------|----------|
| 0 | event_type == init | event | one-hot (1 or 0) |
| 1 | event_type == page_view | event | one-hot |
| 2 | event_type == scroll | event | one-hot |
| 3 | event_type == touch_end | event | one-hot |
| 4 | event_type == click | event | one-hot |
| 5 | event_type == tab_hidden | event | one-hot |
| 6 | event_type == tab_visible | event | one-hot |
| 7 | delta_ms | event | / 10000 |
| 8 | scroll_velocity_px_s | event | / 1000 |
| 9 | scroll_acceleration | event | / 500 |
| 10 | y_reversal | event | bool (0 or 1) |
| 11 | scroll_depth_pct | event | / 100 |
| 12 | tap_interval_ms | event | / 5000 |
| 13 | tap_radius_x | event | / 50 |
| 14 | dead_tap | event | bool |
| 15 | tap_pressure | event | / 1 (already 0–1) |
| 16 | patch_x | event | / 1 (already 0–1) |
| 17 | patch_y | event | / 1 (already 0–1) |
| 18 | scroll_direction | event | -1 / 0 / 1 |
| 19 | scroll_pause_duration_ms | event | / 10000 |
| 20 | page_load_index | event | raw int (page nav count) |
| 21 | long_press_duration_ms | event | / 5000 |
| 22 | page_path_hash | event (hex string) | int(val,16) / 0xFFFFFFFF; falls back to init event's value |
| 23 | page_id | event | djb2 hash / 0xFFFFFFFF |
| 24 | is_webview | enriched.ua_meta.is_webview | bool |
| 25 | is_touch | enriched.ua_meta.device_type in (mobile, tablet) | bool |
| 26 | is_paid | init event.is_paid | bool |
| 27 | click_id_type | init event.click_id_type (param name string, e.g. "gclid") | djb2 hash / 0xFFFFFFFF |
| 28 | ip_type | enriched.ip_meta.ip_type | residential=0.0, datacenter=1.0, unknown=0.5 |
| 29 | ip_country | enriched.ip_meta.ip_country (ISO code) | djb2 hash / 0xFFFFFFFF |
| 30 | tap_radius_y | event | / 50 |
| 31 | device_pixel_ratio | init event (fallback session) | min(val, 4.0) / 4.0 |
| 32 | viewport_w_norm | init event (fallback session) | already 0–1 (viewport/2560) |
| 33 | viewport_h_norm | init event (fallback session) | already 0–1 (viewport/1440) |
| 34 | browser_family | enriched.ua_meta.browser_family | djb2 hash / 0xFFFFFFFF |
| 35 | os_family | enriched.ua_meta.os_family | djb2 hash / 0xFFFFFFFF |
| 36 | hour_sin | enriched.time_features.hour_sin | sin(2π × hour/24) |
| 37 | hour_cos | enriched.time_features.hour_cos | cos(2π × hour/24) |
| 38 | dow_sin | enriched.time_features.dow_sin | sin(2π × dow/7) |
| 39 | dow_cos | enriched.time_features.dow_cos | cos(2π × dow/7) |
| 40 | is_weekend | enriched.time_features.is_weekend | bool |
| 41 | timezone_mismatch | enriched.timezone_mismatch | bool (ip_timezone ≠ browser_timezone) |
| 42–50 | reserved | — | 0.0 |

**Critical constraint**: if adding a new feature, update `featurizer.py` AND `packages/shared/constants/feature-list.ts` keeping identical index order.

---

## Redis Key Schema

| Key pattern | Type | Purpose |
|-------------|------|---------|
| `metricade_stream:{org_id}` | Stream | Ingest event stream, consumed by inference worker |
| `metricade_dlq:{org_id}` | List | Dead-letter queue for failed edge-worker publishes |
| `metricade_ingest_total:{org_id}` | String (counter) | Total sessions accepted by edge worker |
| `metricade_heartbeat` | String | Unix timestamp (ms), written by inference worker every 30s |
| `metricade_sess:{org_id}:{session_id}` | String (JSON) | Accumulated event list for session, TTL 4h |

---

## Vector Metadata Schema

Each vector stored in Upstash Vector has the following metadata:

| Field | Value |
|-------|-------|
| `org_id` | The merchant's org ID |
| `trace_id` | trace_id of the **last** flush that updated this vector |
| `received_at` | Unix timestamp (ms) of last flush |
| `client_id` | Persistent browser ID (localStorage) |
| `session_id` | Session ID — also the vector ID |
| `ip_country` | ISO 2-letter country code |
| `ip_type` | `residential`, `datacenter`, or `unknown` |
| `device_type` | `desktop`, `mobile`, `tablet`, `bot`, or `unknown` |
| `is_webview` | `true`/`false` |
| `cluster_label` | `null` until clustering job runs |

---

## Key Constraints

- `org_id` must be at the top level of every ingest payload — returns 400 if missing
- Stream entries store the full enriched message as a single `payload` JSON field
- The Transformer outputs L2-normalized 192-dim vectors — cosine similarity in Upstash Vector is equivalent to dot product on these vectors
- One vector per `session_id` — multiple flushes upsert the same vector slot; accumulated events are stored in `metricade_sess:*` Redis keys
- `page_path_hash` from pixel.js is always a hex string (`.toString(16)`) — never parse with `float()` directly, use `int(val, 16)`
- **`src/constants.py` defaults are wrong** — always rely on `fly.toml` env vars overriding them
- No test framework configured for edge-worker or pixel — add if needed
- All deployments are manual — no CI/CD
