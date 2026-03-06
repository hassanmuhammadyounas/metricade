# Architecture Overview

## Pipeline

```
Browser (pixel.js)
  │  POST /ingest (JSON, sendBeacon/fetch keepalive)
  ▼
Cloudflare Edge Worker (Hono)
  │  Enrich: IP geo, UA parse, time encoding
  │  XADD behavioral_stream (if heartbeat fresh)
  │  LPUSH behavioral_dlq (if no consumer detected)
  ▼
Upstash Redis Streams (behavioral_stream)
  │  XREADGROUP — inference_group / fly_worker_1
  ▼
Fly.io Inference Worker (Python)
  │  Featurize: 51-feature tensor
  │  Encode: BehavioralTransformer → 192-dim L2-normalized vector
  │  Upsert: Upstash Vector
  │  ACK: XACK
  ▼
Upstash Vector (192-dim, cosine similarity)
  │  Nightly clustering job
  ▼
HDBSCAN Clustering (Fly.io, scheduled)
  │  Assign: FRAUD_BOT / HIGH_INTENT / MEDIUM_INTENT / LOW_INTENT / UNASSIGNED
  │  Write: cluster_label back to Vector metadata
  │  Report: stats to Redis
  ▼
Queryable labeled vector store
```

## Technology Rationale

| Technology | Choice | Rationale |
|---|---|---|
| Cloudflare Workers | Edge ingestion | Zero cold start, sub-millisecond delta_ms fidelity, global PoP |
| Upstash Redis Streams | Event buffer | Crash-safe (ACK), consumer groups, DLQ pattern, serverless |
| Fly.io | ML inference | Persistent process (long-lived subscriber), CPU inference, low cost |
| Upstash Vector | Fingerprint store | Serverless, cosine ANN search, zero operational overhead |
| HDBSCAN | Clustering | Density-based, no fixed k, handles noise, finds natural cohorts |
| Transformer | Encoding | Captures event sequence order and interaction patterns |
