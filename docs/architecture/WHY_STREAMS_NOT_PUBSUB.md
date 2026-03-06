# Why Redis Streams Over Pub/Sub

## The Problem with Pub/Sub

Redis pub/sub is fire-and-forget. If the subscriber (Fly.io inference worker) is down when a message is published, the message is lost permanently. For a fraud detection system, losing sessions during worker restarts or deployments is unacceptable.

## Streams Advantages

| Feature | Pub/Sub | Streams |
|---|---|---|
| Message persistence | No | Yes — messages persist until ACKed |
| Consumer groups | No | Yes — multiple consumers, each message delivered once |
| ACK/NACK | No | Yes — XACK, re-delivery on failure |
| DLQ pattern | No | Yes — LPUSH to DLQ key on consumer absence |
| Replay | No | Yes — XREAD from any offset |
| Consumer lag visibility | No | Yes — XINFO GROUPS |

## The DLQ Safety Net

When the Fly.io worker is down, the Cloudflare Worker detects missing heartbeat and routes to `behavioral_dlq` instead of the stream. When the worker recovers, the DLQ is drained back to the stream. Zero sessions lost.
