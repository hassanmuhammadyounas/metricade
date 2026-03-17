"""
Generate bootstrap_random.pt — shared deterministic random init for all model-worker instances.

Run from repo root:
    python scripts/generate_bootstrap.py

Output: packages/model-worker/models/bootstrap_random.pt
"""
import sys
import os
import hashlib

# Allow importing from model-worker package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "packages", "model-worker"))

import torch
from src.inference.transformer import BehavioralTransformer
from src.constants import MAX_SEQ_LEN, N_CONT, N_CAT, VECTOR_DIMS

OUTPUT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "packages", "model-worker", "models", "bootstrap_random.pt"
)

# Fixed seed — every instance that loads this file gets the same weights
torch.manual_seed(42)

print("Instantiating BehavioralTransformer (seed=42)...")
model = BehavioralTransformer()
model.eval()

# Validate output shape before saving
with torch.no_grad():
    dummy_cont = torch.zeros(1, MAX_SEQ_LEN, N_CONT)
    dummy_cat  = torch.zeros(1, N_CAT, dtype=torch.int64)
    out = model(dummy_cont, dummy_cat)

assert out.shape == (1, VECTOR_DIMS), \
    f"Output shape mismatch: expected (1, {VECTOR_DIMS}), got {out.shape}"
print(f"Output shape validated: {tuple(out.shape)} ✓")

# Save
output_path = os.path.normpath(OUTPUT_PATH)
torch.save(model.state_dict(), output_path)

# Stats
size_bytes = os.path.getsize(output_path)
with open(output_path, "rb") as f:
    sha256 = hashlib.sha256(f.read()).hexdigest()

print(f"Saved to : {output_path}")
print(f"File size: {size_bytes / 1024:.1f} KB")
print(f"SHA-256  : {sha256}")
print()
print("Weight summary:")
total_params = 0
for name, param in model.named_parameters():
    total_params += param.numel()
    print(f"  {name:<45} {str(tuple(param.shape)):<25} {param.numel():>8,} params")
print(f"\nTotal parameters: {total_params:,}")
