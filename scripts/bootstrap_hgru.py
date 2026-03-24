"""
scripts/bootstrap_hgru.py
=========================
Generate random-init weights for the H-GRU encoder.
Run this once before first training or deployment.

Usage:
  python scripts/bootstrap_hgru.py

Saves to:
  packages/vector-worker/models/hgru.pt
"""
import sys
from pathlib import Path

REPO_ROOT  = Path(__file__).resolve().parent.parent
WORKER_PKG = REPO_ROOT / 'packages' / 'vector-worker'
MODELS_DIR = WORKER_PKG / 'models'
MODELS_DIR.mkdir(exist_ok=True)
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(WORKER_PKG))

import torch
from src.model import HierarchicalGRUEncoder

torch.manual_seed(42)
model = HierarchicalGRUEncoder(event_hidden=64, session_hidden=64, embed_dim=64)
model.eval()

out = MODELS_DIR / 'hgru.pt'
torch.save(model.state_dict(), out)
print(f'Bootstrap weights saved → {out}')
print(f'Total params: {sum(p.numel() for p in model.parameters()):,}')
