# Inference Worker Deployment

## Prerequisites

- Fly.io CLI installed and authenticated (`fly auth login`)
- Secrets set (`fly secrets set UPSTASH_REDIS_URL=... UPSTASH_REDIS_TOKEN=... UPSTASH_VECTOR_URL=... UPSTASH_VECTOR_TOKEN=...`)
- `bootstrap_random.pt` exists in `models/` (or trained weights)

## Step-by-step

1. Run tests: `python -m pytest tests/`
2. Deploy: `fly deploy`
3. Check health: `curl https://behavioral-inference.fly.dev/health`
4. Verify heartbeat: check `fly_worker_heartbeat` key in Redis
5. Send a test event manually via curl to the Worker `/ingest` endpoint and verify the vector appears in Upstash

## Rollback

Run `fly releases` to list versions, then `fly deploy --image <previous-image-ref>` to roll back to a specific release.
