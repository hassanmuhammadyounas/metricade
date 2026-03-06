# Upstash Module

Provisions the Upstash Redis database and Vector index.

## What it creates

- `upstash_redis_database` — Redis Streams for buffered event ingestion and audit trail
- `upstash_vector_index` — 192-dimensional cosine similarity vector index

## Why cosine similarity?

SimCLR-trained vectors are L2-normalized during training. For L2-normalized vectors, cosine similarity and dot product are equivalent, but cosine is more semantically meaningful: it measures angle between vectors in behavioral space, not magnitude. Behavioral differences between cohorts are directional, not scalar.

## Why 192 dimensions?

192 is divisible by 8 (GPU tensor alignment), provides sufficient representational capacity for ~5 behavioral cohorts with margin for fine-grained sub-clusters, and keeps per-vector storage at ~1.5KB. Do not change this after the first vector is upserted — the index schema is immutable.

## Region pairing

Match the region to your Fly.io region. For `iad` (Ashburn, VA) on Fly.io, use `us-east-1` on Upstash.
