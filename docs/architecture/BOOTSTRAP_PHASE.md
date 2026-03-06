# Bootstrap Phase

## How the Pipeline Runs Before SimCLR Training Completes

The system is designed to be operational from day one, before any labeled data or trained model exists.

## Phase 1: Bootstrap (Day 0 → ~Week 2)

- `bootstrap_random.pt` is loaded — random linear projection
- Vectors are mathematically valid 192-dim unit vectors
- They are **not semantically meaningful** — similar behaviors produce dissimilar vectors
- Clustering during this phase produces noise
- **Benefit:** The pipeline is running, collecting data, building the corpus for SimCLR training

## Phase 2: SimCLR Training (Week 2 → Week 4)

- Use collected sessions as unlabeled training data
- SimCLR contrastive objective: augmented views of the same session → similar vectors
- Produces `v1_simclr_trained.pt`

## Phase 3: Production (Week 4+)

- Swap model weights (see MODEL_VERSIONING.md)
- Re-encode all historical sessions manually (run `src/main.py` in replay mode)
- Clustering now produces meaningful cohort labels

## What to Tell Stakeholders

During bootstrap, the system is live and collecting. Fraud detection reports are not available until Phase 3. The data collected during bootstrap is what enables training — so starting early is valuable even if the output isn't useful yet.
