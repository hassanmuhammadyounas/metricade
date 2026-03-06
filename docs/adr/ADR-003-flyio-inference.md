# ADR-003: Use Fly.io for Inference Worker

**Status:** Accepted
**Date:** 2024-01-01

## Context

The inference worker needs to maintain a persistent Redis Streams subscription (XREADGROUP blocking read). This requires a long-lived process, which is incompatible with serverless/edge runtimes.

## Decision

Deploy the Python inference worker on Fly.io with a `shared-cpu-1x` 512MB machine in the same region as Upstash Redis (iad / us-east-1).

## Consequences

- **Positive:** Persistent process — long-lived Redis subscriber without re-connection overhead
- **Positive:** Same region as Upstash → < 5ms Redis RTT
- **Positive:** Simple Docker-based deployment, `fly deploy` replaces the machine
- **Negative:** Minimum cost even at zero traffic (shared-cpu-1x ~$1.94/month)
- **Negative:** Fly.io machine can go down — mitigated by DLQ safety net and auto-restart
