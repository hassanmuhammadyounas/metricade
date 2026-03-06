# ADR-001: Use Redis Streams for Event Buffering

**Status:** Accepted
**Date:** 2024-01-01

## Context

We need a buffer between the Cloudflare Edge Worker (event receiver) and the Fly.io inference worker (consumer). The buffer must survive subscriber downtime without losing messages.

## Decision

Use Upstash Redis Streams with a consumer group (`inference_group`). Messages are ACKed only after successful vector upsert. Unacknowledged messages are redelivered. A DLQ key (`behavioral_dlq`) is used when no consumer is active.

## Consequences

- **Positive:** Crash safety, exactly-once delivery semantics, consumer lag visibility
- **Positive:** Serverless — no Redis instance to manage
- **Negative:** Slightly more complex than pub/sub — requires consumer group management
- **Negative:** Upstash Streams has per-command pricing — high volume means higher cost

## Alternatives Considered

- Redis pub/sub: rejected — fire-and-forget, no crash safety
- Kafka: rejected — operational overhead, overkill for this scale
- HTTP queue (BullMQ): rejected — requires a server, another failure point
