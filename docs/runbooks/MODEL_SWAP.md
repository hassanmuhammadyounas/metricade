# Runbook: Hot-Swap Model Weights

**When:** New SimCLR training run complete, want to upgrade to new model without message loss.

## Step 1 — Verify new model

```bash
cd packages/inference-worker
python -c "
from src.inference.model_loader import load_model
import os
os.environ['MODEL_PATH'] = 'models/v2_simclr.pt'
model = load_model()
print('Model loaded OK')
"
```

## Step 2 — Add weights to Docker image

Update `fly.toml`:
```toml
[env]
MODEL_PATH = "/models/v2_simclr.pt"
```

## Step 3 — Deploy (rolling — no message loss)

```bash
fly deploy
```

Fly.io performs a rolling deploy. The old machine ACKs in-flight messages, then the new machine starts consuming. No gap in consumption.

## Step 4 — Verify new model active

```bash
curl https://behavioral-inference.fly.dev/health
# Check version field reflects new deployment
```

## Step 5 — Replay historical sessions (optional)

To re-encode historical sessions with the new model, run `src/main.py` locally with a replay mode. Old cluster labels become stale until the next clustering run.

## Step 6 — Trigger clustering

Trigger manually via Fly.io CLI:
```
fly machine run --app behavioral-clustering --image registry.fly.io/behavioral-clustering:latest --rm
```
