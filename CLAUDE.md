# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Pipeline

```
Browser (pixel.js)
  └─> Cloudflare Edge Worker (Hono)       POST /ingest  →  worker.metricade.com
          └─> Upstash Redis Streams        metricade_stream:{org_id}
                  └─> Fly.io Vector Worker  accumulate → featurize → raw feature vector
                          └─> Upstash Vector   cosine similarity, keyed by session_id
```

All deployments are **manual**. There is no CI/CD.

---

## Live Deployments

| Component          | URL / Location                                      | Platform              |
|--------------------|-----------------------------------------------------|-----------------------|
| Pixel CDN          | https://pixel.metricade.com/pixel.min.js            | Cloudflare Pages      |
| Edge Worker        | https://worker.metricade.com                        | Cloudflare Workers    |
| Vector Worker      | https://behavioral-inference.fly.dev                | Fly.io (`iad` region) |
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

### vector-worker (`packages/vector-worker/`)
```bash
cd packages/vector-worker
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

### Check vector worker logs
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
    trace_id,                           // {session_id}_{flushCounter}_{timestamp}
    is_touch, browser_timezone,
    viewport_w_norm, viewport_h_norm,   // normalized to 2560×1440
    is_paid, session_source, session_medium,
    device_pixel_ratio, click_id_type,
    time_to_first_interaction_ms,       // null on bounce; ms from page load to first scroll/click/touch/keydown
    events: [...]
  }
  ```
- **Transport**: `fetch` with `keepalive: true` + `x-ingest-secret` header when tab visible; `sendBeacon` with `?s=SECRET` query param on `pagehide` (sendBeacon cannot set headers). If `sendBeacon` returns `false` (browser queue full), falls back to keepalive fetch. On non-200 response, events are re-queued into the buffer for retry with `is_retry: true` flag on each event.
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
  - `prior_session_count`: integer — number of prior sessions for this `client_id` (key: `metricade_client_sessions:{org_id}:{client_id}`). Session dedup via `SETNX metricade_new_sess:{org_id}:{session_id}` (4h TTL). First visit = 0. INCR is fire-and-forget via `ctx.waitUntil`.
- **Publishing**: always attempts `XADD` to stream. Falls back to `LPUSH` on `metricade_dlq:{org_id}` only if XADD fails. If both fail, throws → returns 500 to pixel (pixel re-queues events for retry).
- **Slack alerting** (`src/alerts/slack.ts`): `notifySlack(webhookUrl, message)` — called on Redis failure. Requires `SLACK_WEBHOOK_URL` secret.
- Full enriched message serialized as a single `payload` JSON field in the stream entry

### vector-worker (`packages/vector-worker/`)
- Entry point: `src/main.py` — starts subscriber thread (`run_subscriber`) and HTTP health server (uvicorn on port 8080)
- **Processing loop** (`src/subscriber.py`):
  1. `XREADGROUP` — consume new messages from all discovered `metricade_stream:{org_id}` streams
  2. Accumulate events: `_accumulate_events()` merges new flush events into `metricade_sess:{org_id}:{session_id}` in Redis (GET + SETEX, 4h TTL). Has an in-memory cache (60s TTL) to avoid Redis reads on hot sessions.
  3. `featurize(merged_payload, enriched)` — produces `FeatureOutput(cont=[64, N_CONT], cat=[N_CAT])` — see Feature Vector section below
  4. `model.encode(features)` — Transformer → L2-normalized 192-dim vector
  5. `upsert_vector(session_id, vector, meta)` — keyed by `session_id` (one vector per session, upserted on every flush)
  6. `XACK`
- Every 150 loops (~5 min): re-scan for new org streams, run `XAUTOCLAIM` to reclaim idle PEL messages (idle >60s), clean up expired in-memory session cache.
- **DLQ**: owned entirely by the edge worker. Vector worker does NOT drain DLQ.
- **Model** (`src/inference/transformer.py`): `BehavioralTransformer` — nn.Embedding tables (browser, os, country, ip_type, click_id, device_type, session_source, session_medium, device_vendor) → concat embeddings (90 dims) with continuous features → Linear(N_CONT+90→128) → CLS token + TransformerEncoder(d_model=128, nhead=4, num_layers=2) → CLS output → Linear(128→192) → L2 normalize. Falls back to random init if model file not found at `MODEL_PATH`. All embedding tables start random and become meaningful after training on real sessions.
- **Spot-check**: 1% of upserts are read back from Upstash Vector to verify persistence (`SPOT_CHECK_RATE=0.01`).
- **`src/constants.py` default values are wrong** (`behavioral_stream`, `behavioral_dlq`) — always overridden by `fly.toml` env vars.
- **Multi-org model strategy**: Two-tier — per-org model file (`models/{org_id}.pt`) for orgs with sufficient data; falls back to segment model (`models/segment_low_aov.pt` / `segment_mid_aov.pt` / `segment_high_aov.pt`) for new/small orgs. Segment assigned at org onboarding via `metricade_org:{org_id}` Redis key. Training pipeline is a separate offline script — not yet implemented.

---

## Feature Vector — Complete Reference

`packages/vector-worker/src/inference/featurizer.py` produces a `FeatureOutput` dataclass:
- `cont`: `[64, N_CONT]` float32 tensor — continuous features per event row
- `cat`: `[5]` int64 tensor — session-level categorical indices (one per categorical field)

**64 rows** = up to 64 events per session (zero-padded). Oldest event first.

`page_path_hash` from pixel.js is a hex string — parsed with `int(val, 16) / 0xFFFFFFFF`.
Session-level fields use `_pget()`: reads from payload root first, falls back to `page_view` event for backwards compatibility.

### Continuous features (`cont` tensor — per event row)

| Index | Feature | Source | Encoding |
|-------|---------|--------|----------|
| 0 | event_type == page_view | event | one-hot |
| 1 | event_type == route_change | event | one-hot |
| 2 | event_type == scroll | event | one-hot |
| 3 | event_type == touch_end | event | one-hot |
| 4 | event_type == click | event | one-hot |
| 5 | event_type == tab_hidden | event | one-hot |
| 6 | event_type == tab_visible | event | one-hot |
| 7 | event_type == engagement_tick | event | one-hot |
| 8 | event_type == idle | event | one-hot |
| 9 | delta_ms | event | / 10000 |
| 10 | scroll_velocity_px_s | event | sign(v) × log1p(abs(v)) / 10 |
| 11 | scroll_acceleration | event | sign(a) × log1p(abs(a)) / 15 |
| 12 | y_reversal | event | bool |
| 13 | scroll_depth_pct | event | / 100 |
| 14 | tap_interval_ms | event | / 5000 |
| 15 | tap_radius_x | event | / 50 |
| 16 | dead_tap | event | bool |
| 17 | tap_pressure | event | passthrough (0–1) |
| 18 | patch_x | event | passthrough (0–1) |
| 19 | patch_y | event | passthrough (0–1) |
| 20 | scroll_direction | event | -1 / 0 / 1 |
| 21 | scroll_pause_duration_ms | event | / 10000 |
| 22 | page_load_index | event | raw int |
| 23 | long_press_duration_ms | event | / 5000 |
| 24 | page_path_hash | event (hex string) | int(val,16) / 0xFFFFFFFF |
| 25 | tap_radius_y | event | / 50 |
| 26 | is_webview | enriched.ua_meta.is_webview | bool |
| 27 | is_touch | ua_meta.device_type in (mobile, tablet) | bool |
| 28 | is_paid | payload root (fallback: page_view event) | bool |
| 29 | device_pixel_ratio | payload root (fallback: page_view event) | min(val, 4.0) / 4.0 |
| 30 | viewport_w_norm | payload root | already 0–1 (viewport/2560) |
| 31 | viewport_h_norm | payload root | already 0–1 (viewport/1440) |
| 32 | hour_sin | enriched.time_features | sin(2π × hour/24) |
| 33 | hour_cos | enriched.time_features | cos(2π × hour/24) |
| 34 | dow_sin | enriched.time_features | sin(2π × dow/7) |
| 35 | dow_cos | enriched.time_features | cos(2π × dow/7) |
| 36 | is_weekend | enriched.time_features | bool |
| 37 | timezone_mismatch | enriched.timezone_mismatch | bool (ip_timezone ≠ browser_timezone) |
| 38 | prior_session_count | enriched.prior_session_count | log1p(val) / log1p(20), capped at 1.0 |

**Dropped**: `page_id` (was index 23 — pure noise, unique UUID per page, model can never learn from it).

### Categorical features (`cat` tensor — session-level, integer indices)

These are looked up in `nn.Embedding` tables inside `BehavioralTransformer`. Index 0 = unknown/fallback for any value not in vocabulary.

| cat index | Feature | Source | Vocab size | Embed dim |
|-----------|---------|--------|-----------|-----------|
| 0 | browser_family | enriched.ua_meta.browser_family | ~20 | 10 |
| 1 | os_family | enriched.ua_meta.os_family | ~15 | 8 |
| 2 | ip_country | enriched.ip_meta.ip_country (ISO code) | ~250 | 32 |
| 3 | ip_type | enriched.ip_meta.ip_type | 3 | 4 |
| 4 | click_id_type | payload.click_id_type | ~10 | 8 |
| 5 | device_type | enriched.ua_meta.device_type | 5 | 4 |
| 6 | session_source | payload.session_source | ~15 | 8 |
| 7 | session_medium | payload.session_medium | ~10 | 8 |
| 8 | device_vendor | enriched.ua_meta.device_vendor | ~15 | 8 |

Total embedding output = 10+8+32+4+8+4+8+8+8 = **90 dims** (concatenated, broadcast to all event rows, then concatenated with `cont` before `input_proj`).

**When adding a new feature**: update only `featurizer.py` for continuous features, or add a new `nn.Embedding` entry in `transformer.py` for categorical features.

---

## Redis Key Schema

| Key pattern | Type | Purpose |
|-------------|------|---------|
| `metricade_stream:{org_id}` | Stream | Ingest event stream, consumed by vector worker |
| `metricade_dlq:{org_id}` | List | Dead-letter queue — populated by edge worker only on XADD failure; drained back to stream every minute by cron |
| `metricade_sess:{org_id}:{session_id}` | String (JSON) | Accumulated event list for session, TTL 4h |
| `metricade_new_sess:{org_id}:{session_id}` | String | Session dedup key for prior_session_count — SETNX on first flush, TTL 4h |
| `metricade_client_sessions:{org_id}:{client_id}` | String (int) | Running count of sessions seen for this client_id — incremented on each new session, no TTL |

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
- Session-level fields (`is_paid`, `click_id_type`, `device_pixel_ratio`, `viewport_w_norm`, `viewport_h_norm`, `time_to_first_interaction_ms`) live at the flush payload root — the featurizer reads them via `_pget()` which falls back to the `page_view` event for old stream entries
- `prior_session_count` is injected as enrichment by the edge worker. The value is frozen at first flush of a session (stored in `metricade_new_sess:{org_id}:{session_id}`) so all flushes of the same session report the same count. The client counter (`metricade_client_sessions:{org_id}:{client_id}`) is incremented fire-and-forget via `ctx.waitUntil`.
- **`src/constants.py` defaults are wrong** — always rely on `fly.toml` env vars overriding them
- No test framework configured for edge-worker or pixel — add if needed
- All deployments are manual — no CI/CD
- Learned embeddings (`nn.Embedding` tables) are initialized randomly and produce meaningless vectors until the model is trained on real session data (~5,000 sessions minimum, ~20,000 for reliable embeddings). Collecting data now is the priority — training comes later.
