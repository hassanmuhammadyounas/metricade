# Model Weights

## Files

| File | Description |
|---|---|
| `bootstrap_random.pt` | Untrained random projection weights — used before SimCLR training completes. Vectors are not semantically meaningful but the pipeline runs end-to-end. |
| `v1_simclr_trained.pt` | First SimCLR-trained model. Add after training completes. |

## How to train and export

```bash
# Training produces a state_dict — save it with:
torch.save(model.state_dict(), "models/v1_simclr_trained.pt")
```

## How to generate bootstrap weights

```python
import torch
from src.inference.transformer import BehavioralTransformer

model = BehavioralTransformer()
torch.save(model.state_dict(), "models/bootstrap_random.pt")
```

## Hot-swap procedure

See [docs/MODEL_VERSIONING.md](../docs/MODEL_VERSIONING.md).

## Version history

| Version | File | Date | Notes |
|---|---|---|---|
| bootstrap | `bootstrap_random.pt` | initial | Random projection |
