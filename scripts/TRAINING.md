# Training BehavioralTransformer

## Overview

### What this does

`scripts/train.py` trains the `BehavioralTransformer` model using **SimCLR**, a self-supervised contrastive learning framework. No labels are needed — the model learns by being asked to recognize that two differently augmented views of the same session should produce similar vectors, while sessions from different users should produce dissimilar vectors.

This approach works especially well for behavioral sequences because:
- Two augmented crops of the same session should encode the same underlying user intent
- The model learns to ignore surface-level variation (which events happened to be included in a flush) and focus on the latent behavioral pattern
- It does not require any ground truth labels, so it works from day one of data collection

### CL4SRec augmentations

CL4SRec (Contrastive Learning for Sequential Recommendation) introduced three augmentations designed specifically for event sequences. Each augmentation produces a different "view" of the same session:

- **Crop**: keep a random contiguous slice of `ratio * real_length` events. Simulates a partial observation of the session — as if the pixel only captured part of the activity.
- **Mask**: randomly zero out a fraction of event rows. Forces the model to reason from incomplete data, which improves robustness to dropped or missing events.
- **Reorder**: shuffle a contiguous window of events. The model must learn that behavioral intent is order-tolerant to some degree — browsing three product pages in a different order carries similar signal.

Two augmentations are sampled at random (with replacement) and applied sequentially to produce each view. Both views share the same categorical features (`cat` tensor) — only the continuous event sequence is augmented.

---

## Prerequisites

Install dependencies (from the repo root or in a virtual environment):

```bash
pip install -r scripts/requirements.txt
```

For CUDA training (optional, CPU works fine for the model size):

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

---

## Setup

The script reads Redis credentials from a `.env` file at the repo root. Create it if it does not exist:

```
UPSTASH_REDIS_URL=https://singular-fawn-58838.upstash.io
UPSTASH_REDIS_TOKEN=<your token>
```

Existing environment variables take precedence over `.env` values, so you can also export them directly.

The model-worker package must be present at `packages/model-worker/` relative to the repo root — the script adds it to `sys.path` automatically.

---

## CLI Usage

Run from the **repo root**:

```bash
python scripts/train.py [OPTIONS]
```

### Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--org ORG_ID` | (all orgs) | Train only this org. Omit to auto-discover and train all orgs that have feature data in Redis. |
| `--epochs N` | `50` | Number of full passes over the dataset. |
| `--batch-size N` | `64` | Number of sessions per gradient step. Must be at least 2. Drop this if you hit OOM. |
| `--lr FLOAT` | `3e-4` | Peak learning rate for AdamW. Cosine decay is applied across all steps. |
| `--temperature FLOAT` | `0.07` | NT-Xent softmax temperature. Lower = sharper, harder negatives. Rarely needs tuning. |
| `--min-sessions N` | `200` | Minimum sessions required to start training. Orgs below this threshold are skipped. |
| `--crop-ratio FLOAT` | `0.7` | Fraction of the sequence kept by the crop augmentation. |
| `--mask-ratio FLOAT` | `0.2` | Fraction of event rows zeroed by the mask augmentation. |
| `--reorder-ratio FLOAT` | `0.2` | Fraction of the sequence window shuffled by the reorder augmentation. |
| `--resume` | `False` | Resume from `{org_id}_checkpoint.pt` if it exists. Restores model, head, optimizer, and scheduler state. |
| `--dry-run` | `False` | Load the dataset, print tensor shapes and value ranges, then exit. No training is run. |

### Example commands

Train a single org for 50 epochs:
```bash
python scripts/train.py --org org_abc123
```

Train all orgs, resuming from checkpoints:
```bash
python scripts/train.py --resume
```

Quick dataset sanity check before training:
```bash
python scripts/train.py --org org_abc123 --dry-run
```

Train with a smaller batch size to fit on limited RAM:
```bash
python scripts/train.py --org org_abc123 --batch-size 32
```

Train with more aggressive augmentations (shorter crops, more masking):
```bash
python scripts/train.py --org org_abc123 --crop-ratio 0.5 --mask-ratio 0.3
```

---

## How augmentations work

### When to tune crop-ratio

`--crop-ratio` controls what fraction of the session is preserved. Default `0.7` keeps 70% of events. If sessions are very short (< 10 events on average), consider raising to `0.8` so the model has enough signal in each view. For very long sessions (100+ events), lowering to `0.5` creates harder positives.

### When to tune mask-ratio

`--mask-ratio` zeros out individual event rows. Default `0.2` masks 20% of events. If your event streams are noisy (many duplicate or near-duplicate events), increasing this forces more robustness. If events are sparse and individually meaningful, keep it low.

### When to tune reorder-ratio

`--reorder-ratio` shuffles a contiguous window. Default `0.2` shuffles 20% of the sequence. Behavioral sequences are partially order-dependent (a page_view before a scroll makes sense; the reverse is less natural), so keep this ratio moderate.

---

## Reading training output

### Per-step output

```
  Epoch 3/50 | Step 12/19 | Loss: 4.231 | Pos: 0.42 | Neg: 0.11 | ETA: 2m 34s
```

| Field | What it means |
|-------|---------------|
| `Loss` | NT-Xent cross-entropy. Starts near `ln(2N)` (e.g., 4.15 for batch=64) and should decrease. |
| `Pos` | Mean cosine similarity between positive pairs (the two augmented views of the same session). Should increase toward 1.0 as training progresses. |
| `Neg` | Mean cosine similarity between negative pairs (all other session pairs in the batch). Should stay low, ideally below 0.1. |
| `ETA` | Estimated time to completion, computed from the running step pace. |

### What good training looks like

- **Loss** decreases consistently across epochs. A plateau after epoch 20–30 is normal.
- **Pos sim** rises from ~0.0–0.1 (random init) toward 0.5–0.9 by the end.
- **Neg sim** stays near 0.0–0.15. If it rises above 0.3, representations are collapsing — try lowering `--lr` or increasing `--temperature`.
- The script saves a new `.pt` file only when a new best epoch loss is achieved, so the final saved model is always the best seen.

### Representation collapse

If both `Pos` and `Neg` converge to the same value (e.g., both ~0.5), the model is collapsing — all sessions are mapping to nearly the same vector. This is the primary failure mode of contrastive learning. Try:
- Lowering `--lr` (try `1e-4`)
- Increasing `--temperature` (try `0.1` or `0.2`)
- Verifying that augmentations are actually producing diverse views (use `--dry-run` to inspect tensors)

---

## Post-training validation

After training completes, the script runs automatic validation:

```
  Post-Training Validation (1,842 sessions)
  ==============================================
  Metric                         Trained  Bootstrap
  ----------------------------------------------
  Silhouette score (cosine)        0.312      0.021
  Net separation                   0.481      0.008
  Delta (trained - bootstrap)     +0.291     +0.473
  ==============================================
  Silhouette looks healthy (>0.30).
```

### Silhouette score

Silhouette measures how well-separated the clusters are. Computed with K=3 clusters using cosine distance:
- `> 0.30` — good structure; the model has learned meaningful behavioral patterns
- `0.10–0.30` — some structure; more data or epochs may help
- `< 0.10` — no meaningful separation; model needs more training or more data

The score is not meaningful in absolute terms — what matters is that it is significantly higher than the bootstrap (random-weight) baseline.

### Net separation

`Net separation = mean inter-cluster cosine distance - mean intra-cluster cosine distance`

A positive value means clusters are farther apart than they are internally spread. The higher this is, the more distinct the learned behavioral groups are from each other.

### Bootstrap comparison

The script compares against `packages/model-worker/models/bootstrap_random.pt` (random initialization). If this file is missing, the comparison column shows `(n/a)`. A well-trained model should show a substantial positive delta on both metrics.

---

## Workflow

### 1. Collect data

Run the feature worker and model worker in production to accumulate sessions in Redis. Aim for at least 200 sessions before training (`--min-sessions 200`). For reliable embeddings, target 5,000+ sessions per org.

Check how many sessions an org has:
```bash
python scripts/train.py --org org_abc123 --dry-run
```

### 2. Train

```bash
python scripts/train.py --org org_abc123 --epochs 50
```

The best model is saved to `packages/model-worker/models/{org_id}.pt` automatically.

### 3. Validate

Check the validation output printed after training. Confirm silhouette is higher than bootstrap.

### 4. Deploy

At the end of each org's training, the script prompts:
```
Deploy new weights to Fly.io for org_abc123? (y/n):
```

Entering `y` runs `fly deploy --app metricade-model-worker` from the `packages/model-worker/` directory and streams the output live. Entering `n` skips deployment and prints the path to the saved weights.

To deploy manually at any time:
```bash
cd packages/model-worker
fly deploy --app metricade-model-worker
```

---

## Troubleshooting

### Loss is not decreasing

- Check that sessions contain real data (run `--dry-run` and inspect `cont` min/max — should not all be zero)
- Try a lower learning rate: `--lr 1e-4`
- Increase batch size if possible (more negatives per step helps NT-Xent)
- Ensure `drop_last=True` is in effect — NT-Xent is unstable with varying batch sizes

### Silhouette score is low after training

- Not enough data: silhouette is unreliable below ~500 sessions. Collect more.
- Not enough epochs: try `--epochs 100`
- The three-cluster assumption may not fit your data distribution — this is diagnostic only, not a training objective

### Out of memory (OOM)

- Reduce batch size: `--batch-size 32` or `--batch-size 16`
- The model is small (~2M parameters) and runs well on CPU with `batch-size 64`

### Not enough sessions error

```
ValueError: Only 87 sessions loaded for org 'org_abc123', need at least 200.
```

Either collect more data (let the pipeline run longer) or lower the threshold for testing:
```bash
python scripts/train.py --org org_abc123 --min-sessions 50
```

Note: models trained on very few sessions will not generalize well. The 200-session default is already the practical minimum.

### Redis connection error

Verify credentials:
```bash
python -c "
import os; from pathlib import Path
env = Path('.env')
for line in env.read_text().splitlines():
    if 'REDIS' in line: print(line[:60])
"
```

Make sure `UPSTASH_REDIS_URL` starts with `https://` and the token is not truncated.
