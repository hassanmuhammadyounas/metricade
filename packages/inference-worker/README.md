# inference-worker — Fly.io Python Transformer

Subscribes to Upstash Redis Streams, runs the Behavioral Transformer to encode session feature vectors (192-dim), and upserts to Upstash Vector.

## Local dev

```bash
pip install -r requirements.txt
cp ../../.env.example .env  # fill in Upstash credentials
export $(cat .env | xargs)
python -m src.main
```

## Deploy

All deployment is handled manually. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the full step-by-step checklist.

## Tests

```bash
python -m pytest tests/ -v
```

## Health check

```
GET /health → { status, last_inference_ms, queue_depth, version }
```
