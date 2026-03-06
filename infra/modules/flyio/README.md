# Fly.io Module

Provisions the Fly.io app and machine for the inference worker.

## What it creates

- `fly_app` — the Fly.io application
- `fly_machine` — a shared-cpu-1x VM running the Python inference worker

## Region selection rationale

The region must match the Upstash Redis region. Colocating the Fly.io machine with the Redis database eliminates cross-region RTT on every XREADGROUP call. For `us-east-1` Upstash, use `iad` (Ashburn, VA) on Fly.io.

## Machine type

`shared-cpu-1x` with 512MB RAM is sufficient for CPU-based Transformer inference at low-to-medium volume. Inference runs at ~40ms per batch on shared CPU. Scale up to `shared-cpu-2x` or `performance-1x` if inference lag exceeds 200ms.
