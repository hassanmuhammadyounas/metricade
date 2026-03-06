# Edge Worker Deployment

## Prerequisites

- `wrangler` CLI installed and authenticated (`wrangler login`)
- Secrets set via `wrangler secret put` (see SECRETS.md)
- Zone ID configured in `wrangler.toml` if using custom domain

## Step-by-step

1. Run tests: `npm test`
2. Preview: `wrangler dev`
3. Deploy: `wrangler deploy`
4. Smoke test: verify `GET /health` returns `{"status":"ok"}`
5. Send a test request manually via curl and verify the response

## Rollback

Run `wrangler rollback` directly. This reverts to the previous deployed version instantly.
