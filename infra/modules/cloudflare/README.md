# Cloudflare Module

Provisions the Behavioral Edge Worker, its routes, and the cron trigger.

## What it creates

- `cloudflare_worker_script` — the compiled edge worker bundle
- `cloudflare_worker_route` — routes `/api/behavioral/*` to the worker
- `cloudflare_worker_cron_trigger` — fires every 1 minute for heartbeat checks and DLQ drain

## Required permissions

The API token needs:
- `Workers Scripts: Edit`
- `Workers Routes: Edit`
- `Zone: Read` (if using zone-based routing)
