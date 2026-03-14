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
| Redis              | https://singular-fawn-58838.upstash.io              | Upstash               |
| Vector DB          | https://bright-tiger-54944-us1-vector.upstash.io    | Upstash Vector        |

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

Optional config keys: `flushSize` (default 30), `flushIntervalMs` (default 10000), `debug` (bool).

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
wrangler secret put SLACK_WEBHOOK_URL
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
- App: `behavioral-inference`, region: `iad`
- VM: `shared-cpu-1x`, 512 MB RAM
- Env vars set in `fly.toml` (non-secret): `STREAM_NAME=metricade_stream`, `DLQ_KEY=metricade_dlq`, `CONSUMER_GROUP=inference_group`, `CONSUMER_NAME=fly_worker_1`, `VECTOR_DIMS=192`, `MODEL_PATH=/models/v1_simclr_trained.pt`, `SPOT_CHECK_RATE=0.01`

---

## Testing & Validation

### Check inference worker logs
```bash
fly logs --app behavioral-inference --no-tail 2>&1 | tail -50
```

### Inspect live vectors (Python one-liner)
```python
python -c "
import httpx
from datetime import datetime, timezone
VECTOR_URL = 'https://bright-tiger-54944-us1-vector.upstash.io'
VECTOR_TOKEN = '<token>'
r = httpx.post(VECTOR_URL.rstrip('/')+'/range', headers={'Authorization': f'Bearer {VECTOR_TOKEN}'},
               json={'cursor':'0','limit':50,'includeMetadata':True,'includeVectors':False})
for v in r.json().get('result',{}).get('vectors',[]):
    m = v.get('metadata') or {}
    ts = m.get('received_at')
    dt = datetime.fromtimestamp(ts/1000,tz=timezone.utc).strftime('%H:%M:%S UTC') if ts else '?'
    print(dt, m.get('session_id','?')[:36], m.get('ip_country'), m.get('device_type'))
"
```

---

## Architecture

### pixel.js (`packages/pixel/src/pixel.js`)
- Vanilla JS IIFE — no framework, no dependencies
- `ingestUrl` and `ingestSecret` are **baked in at build time** via esbuild — merchants only configure `orgId`
- Hard stops if `orgId` is missing (`console.error`, pixel does not run)
- **Identity**: `client_id` persisted in `localStorage` (`_mtr_cid`, survives sessions); `session_id` in `sessionStorage` (`_mtr_sid`, new per tab/session); `page_id` is a UUID refreshed on each page navigation; `flushCounter` persisted in `sessionStorage` (`_mtr_fc`, increments across reloads, used in `trace_id`)
- **Flush triggers**: every 10 seconds, or when buffer hits 30 events, or on `pagehide` (tab close/navigate away)
- **Flush payload structure** — session-level fields at the payload root, not repeated per event:
  ```
  {
    org_id, client_id, session_id,
    trace_id,           // {session_id}_{flushCounter}_{timestamp}
    is_touch, browser_timezone,
    viewport_w_norm, viewport_h_norm,   // normalized to 2560×1440
    is_paid, session_source, session_medium,
    device_pixel_ratio, click_id_type,
    events: [...]
  }
  ```
- **Transport**: `fetch` with `keepalive: true` + `x-ingest-secret` header when tab visible; `sendBeacon` with `?s=SECRET` query param on `pagehide` (sendBeacon cannot set headers). If `sendBeacon` returns `false` (browser queue full), falls back to keepalive fetch. On non-200 response, events are re-queued into the buffer for retry.
- **Event types**:
  - `page_view` — fires on every page load (initial load, full navigation). Contains `page_path_hash` + `page_url`. This is the primary page tracking event.
  - `route_change` — fires on SPA navigation only (`popstate` / `hashchange`). Also contains `page_path_hash` + `page_url`.
  - `scroll` — scroll activity with velocity, acceleration, depth, direction
  - `touch_end` — mobile touch events with radius, pressure, dead-tap detection
  - `click` — desktop clicks (suppressed if fired from touch)
  - `tab_hidden` / `tab_visible` — visibility change. `tab_visible` includes `backgrounded_ms`.
  - `engagement_tick` — fires every 5s while tab is visible and user was active within the last 5s. Includes `active_ms`. Two ticks = confirmed 10s engagement.
  - `idle` — fires once after 5s of inactivity. Resets when activity resumes. Includes `idle_duration_ms`.
- `page_url` is present **only** on `page_view` and `route_change` events — not on scroll/click/etc.
- `page_path_hash` is FNV-1a 32-bit hash of `location.pathname` returned as a **hex string** — e.g. `"13177c2e"`
- Ad-click ID definitions → `packages/pixel/src/ad-identifiers.js`; referrer mappings → `packages/pixel/src/referrer-mapping.js`
- **Attribution logic** (priority: click ID → UTM → referrer → direct):
  - Google click IDs (`gclid`, `gbraid`, `wbraid`, `gclsrc`, `dclid`) have `paid_only: true` — always `is_paid: true`, UTM cannot override
  - `fbclid` is ambiguous (Meta appends it to both paid ads and organic links). Resolved by UTM: `utm_medium=social` → `organic_social` / `is_paid: false`; no UTM → defaults to `paid_social` / `is_paid: true`

### edge-worker (`packages/edge-worker/`)
- Hono app on Cloudflare Workers, deployed to `worker.metricade.com`
- `Env` and `Variables` types defined in `src/index.ts`
- Routes: `POST /ingest` (auth inline — supports header + `?s=` for sendBeacon), `GET /health` (public), `GET /dlq/status` (auth via shared secret header)
- Constants in `src/constants.ts` are camelCase: `traceHeader = 'x-trace-id'`, `ingestSharedSecretHeader = 'x-ingest-secret'`. Note: `TRACE_HEADER` in `wrangler.toml` is stale and unused — the value is hardcoded in `constants.ts`.
- **Enrichment added server-side before publishing to stream:**
  - `ip_meta`: `{ ip, ip_country, ip_asn, ip_org, ip_type: 'residential'|'datacenter'|'unknown', ip_timezone }` — from Cloudflare `cf` object (free, no external API). `ip_type` is classified by checking ASN against known datacenter/cloud provider list. IP read from `cf-connecting-ip` header.
  - `ua_meta`: `{ browser_family, browser_version, os_family, os_version, device_type: 'desktop'|'mobile'|'tablet'|'bot'|'unknown', device_vendor, is_webview }` — via `ua-parser-js`; `is_webview` detected by FBAN/FBAV/Instagram/wv patterns
  - `time_features`: `{ hour_sin, hour_cos, dow_sin, dow_cos, local_hour, is_weekend }` — sin/cos encoded from server clock at time of ingest
  - `timezone_mismatch`: boolean — `ip_meta.ip_timezone !== browser_timezone`
  - `hostname`: extracted from `Origin` or `Referer` header
- **Publishing**: always attempts `XADD` to stream. Falls back to `LPUSH` on `metricade_dlq:{org_id}` only if XADD fails. If both fail, throws → returns 500 to pixel (pixel re-queues events for retry).
- **Slack alerting** (`src/alerts/slack.ts`): `notifySlack(webhookUrl, message)` — called on Redis failure. Requires `SLACK_WEBHOOK_URL` secret.
- Full enriched message serialized as a single `payload` JSON field in the stream entry

### inference-worker (`packages/inference-worker/`)
- Entry point: `src/main.py` — starts subscriber thread (`run_subscriber`) and HTTP health server (uvicorn on port 8080)
- **Processing loop** (`src/subscriber.py`):
  1. `XREADGROUP` — consume new messages from all discovered `metricade_stream:{org_id}` streams
  2. Accumulate events: `_accumulate_events()` merges new flush events into `metricade_sess:{org_id}:{session_id}` in Redis (GET + SETEX, 4h TTL). Has an in-memory cache (60s TTL) to avoid Redis reads on hot sessions.
  3. `featurize(merged_payload, enriched)` — produces `[64, 51]` float32 tensor
  4. `model.encode(features)` — Transformer → L2-normalized 192-dim vector
  5. `upsert_vector(session_id, vector, meta)` — keyed by `session_id` (one vector per session, upserted on every flush)
  6. `XACK`
- Every 150 loops (~5 min): re-scan for new org streams, run `XAUTOCLAIM` to reclaim idle PEL messages (idle >60s), drain DLQs back to streams, clean up expired in-memory session cache.
- **Model** (`src/inference/transformer.py`): `BehavioralTransformer` — Linear(51→128) → TransformerEncoder(d_model=128, nhead=4, num_layers=2) → mean pooling over sequence → Linear(128→192) → L2 normalize. Falls back to random init if model file not found at `MODEL_PATH`.
- **Spot-check**: 1% of upserts are read back from Upstash Vector to verify persistence (`SPOT_CHECK_RATE=0.01`).
- **`src/constants.py` default values are wrong** (`behavioral_stream`, `behavioral_dlq`) — always overridden by `fly.toml` env vars.

---

## Feature Vector — Complete Reference

`packages/inference-worker/src/inference/featurizer.py` produces a `[64, 51]` float32 tensor. `featurizer.py` is the single source of truth for feature ordering.

- **64 rows** = up to 64 events per session (zero-padded). Events are the full accumulated sequence across all flushes for the session, oldest first.
- **51 features** per event row — see table below.

All values normalized to approximately [0, 1] or [-1, 1]. Strings encoded as djb2 hash / 0xFFFFFFFF.
`page_path_hash` from pixel.js is a hex string — parsed with `int(val, 16) / 0xFFFFFFFF`.
Session-level fields (26–41) use `_pget()`: reads from payload root first, falls back to `page_view` event for backwards compatibility with old stream entries.

**Known discrepancy**: `featurizer.py` one-hot encoding and `_pget()` fallback still reference `"init"` as an event type. The pixel now emits `"page_view"` instead of `"init"`. The featurizer needs updating: replace `"init"` with `"page_view"` in `_one_hot_event_type()` and in the `_extract_session()` fallback lookup. `engagement_tick` and `idle` are also not yet encoded.

| Index | Feature | Source | Encoding |
|-------|---------|--------|----------|
| 0 | event_type == page_view | event | one-hot (1 or 0) |
| 1 | event_type == route_change | event | one-hot |
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
| 22 | page_path_hash | event (hex string) | int(val,16) / 0xFFFFFFFF; falls back to page_view event's value |
| 23 | page_id | event | djb2 hash / 0xFFFFFFFF |
| 24 | is_webview | enriched.ua_meta.is_webview | bool |
| 25 | is_touch | enriched.ua_meta.device_type in (mobile, tablet) | bool |
| 26 | is_paid | payload.is_paid (fallback: page_view event) | bool |
| 27 | click_id_type | payload.click_id_type (fallback: page_view event) | djb2 hash / 0xFFFFFFFF |
| 28 | ip_type | enriched.ip_meta.ip_type | residential=0.0, datacenter=1.0, unknown=0.5 |
| 29 | ip_country | enriched.ip_meta.ip_country (ISO code) | djb2 hash / 0xFFFFFFFF |
| 30 | tap_radius_y | event | / 50 |
| 31 | device_pixel_ratio | payload (fallback: page_view event) | min(val, 4.0) / 4.0 |
| 32 | viewport_w_norm | payload (fallback: page_view event) | already 0–1 (viewport/2560) |
| 33 | viewport_h_norm | payload (fallback: page_view event) | already 0–1 (viewport/1440) |
| 34 | browser_family | enriched.ua_meta.browser_family | djb2 hash / 0xFFFFFFFF |
| 35 | os_family | enriched.ua_meta.os_family | djb2 hash / 0xFFFFFFFF |
| 36 | hour_sin | enriched.time_features.hour_sin | sin(2π × hour/24) |
| 37 | hour_cos | enriched.time_features.hour_cos | cos(2π × hour/24) |
| 38 | dow_sin | enriched.time_features.dow_sin | sin(2π × dow/7) |
| 39 | dow_cos | enriched.time_features.dow_cos | cos(2π × dow/7) |
| 40 | is_weekend | enriched.time_features.is_weekend | bool |
| 41 | timezone_mismatch | enriched.timezone_mismatch | bool (ip_timezone ≠ browser_timezone) |
| 42–50 | reserved | — | 0.0 |

**When adding a new feature**: update only `featurizer.py` — there is no separate feature-list file.

---

## Redis Key Schema

| Key pattern | Type | Purpose |
|-------------|------|---------|
| `metricade_stream:{org_id}` | Stream | Ingest event stream, consumed by inference worker |
| `metricade_dlq:{org_id}` | List | Dead-letter queue — populated only on XADD failure |
| `metricade_sess:{org_id}:{session_id}` | String (JSON) | Accumulated event list for session, TTL 4h |

---

## Vector Metadata Schema

Each vector stored in Upstash Vector has the following metadata:

| Field | Value |
|-------|-------|
| `org_id` | The merchant's org ID |
| `trace_id` | trace_id of the **last** flush that updated this vector |
| `received_at` | Unix timestamp (ms) of last flush |
| `hostname` | Hostname extracted from Origin/Referer header at ingest |
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
- `page_path_hash` from pixel.js is always a hex string (FNV-1a, `.toString(16)`) — never parse with `float()` directly, use `int(val, 16)`
- Session-level fields (`is_paid`, `click_id_type`, `device_pixel_ratio`, `viewport_w_norm`, `viewport_h_norm`) live at the flush payload root — the featurizer reads them via `_pget()` which falls back to the `page_view` event for old stream entries
- **`src/constants.py` defaults are wrong** — always rely on `fly.toml` env vars overriding them
- No test framework configured for edge-worker or pixel — add if needed
- All deployments are manual — no CI/CD
