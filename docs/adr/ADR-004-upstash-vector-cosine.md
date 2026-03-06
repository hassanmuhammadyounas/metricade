# ADR-004: Use Upstash Vector with Cosine Similarity

**Status:** Accepted
**Date:** 2024-01-01

## Context

We need a vector database to store 192-dim session fingerprints and support approximate nearest-neighbor search for similarity queries and clustering.

## Decision

Use Upstash Vector with cosine similarity and 192 dimensions.

## Why Cosine

SimCLR training L2-normalizes the output vectors. For unit vectors, cosine similarity and dot product are equivalent, and both measure the angle between vectors rather than magnitude. Behavioral differences between cohorts are directional — a FRAUD_BOT vector points in a different direction in embedding space from a HIGH_INTENT vector, regardless of vector magnitude.

## Why Upstash

- Serverless — no persistent instance to manage
- Per-request pricing — cost scales to zero at idle
- REST API — accessible from both Cloudflare Workers and Python
- Managed index — no tuning required at this scale

## Consequences

- **Positive:** Zero operational overhead, scales to zero at idle
- **Negative:** Index dimension is immutable — requires new index if dim changes
- **Negative:** No SQL-style filtering at query time — metadata filtering is post-query
