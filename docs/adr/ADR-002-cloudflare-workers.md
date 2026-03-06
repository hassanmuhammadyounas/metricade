# ADR-002: Use Cloudflare Workers for Event Ingestion

**Status:** Accepted
**Date:** 2024-01-01

## Context

The ingestion endpoint must receive pixel.js payloads with minimal latency. delta_ms timing signals require low RTT variance. The system must handle bursty bot traffic without cold starts.

## Decision

Use a Cloudflare Worker (Hono framework) deployed at the edge. Routes all /api/behavioral/* traffic to the Worker.

## Consequences

- **Positive:** < 20ms RTT from most browsers, preserves sub-100ms delta_ms fidelity
- **Positive:** Zero cold start — V8 isolates always warm
- **Positive:** Automatic DDoS mitigation from Cloudflare network
- **Negative:** CPU time limits (50ms CPU/request on free tier) — adequate for enrichment + Redis write
- **Negative:** No persistent connections — stateless per-request only
