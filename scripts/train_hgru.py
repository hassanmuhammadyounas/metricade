"""
scripts/train_hgru.py
=====================
Offline VICReg training for the H-GRU session encoder.

Reads sessions from ClickHouse, trains the model with self-supervised
contrastive loss (VICReg), saves weights to:
  packages/vector-worker/models/hgru.pt

Usage:
  python scripts/train_hgru.py
  python scripts/train_hgru.py --org org_XXXX --epochs 300 --batch 16
  python scripts/train_hgru.py --weights path/to/existing.pt   # resume

Requirements (auto-installed):
  torch, numpy, httpx
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────
REPO_ROOT   = Path(__file__).resolve().parent.parent
WORKER_PKG  = REPO_ROOT / 'packages' / 'vector-worker'
MODELS_DIR  = WORKER_PKG / 'models'
MODELS_DIR.mkdir(exist_ok=True)
OUTPUT_DIR  = REPO_ROOT / 'scripts' / 'output' / 'training'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(WORKER_PKG))

# ── Auto-install ──────────────────────────────────────────────────────────
import subprocess

def _install(*pkgs):
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', *pkgs])

try:
    import torch
    import torch.optim as optim
except ImportError:
    print('Installing torch...')
    _install('torch', '--index-url', 'https://download.pytorch.org/whl/cpu')
    import torch
    import torch.optim as optim

try:
    import numpy as np
except ImportError:
    _install('numpy')
    import numpy as np

try:
    import httpx
except ImportError:
    _install('httpx')
    import httpx

from src.features import build_session_tensors
from src.model import HierarchicalGRUEncoder, augment_tensors, vicreg_loss
from src.clickhouse import (
    get_all_orgs, get_all_session_events, get_robust_params,
)
from src.constants import DEFAULT_ROBUST


def session_label(events: list[dict]) -> str:
    """
    Derive a behavioral label from session metadata.
    Works for both synthetic (generated) and real sessions.
    """
    if not events:
        return 'unknown'
    first      = events[0]
    ip_type    = (first.get('ip_type')    or '').lower()
    device     = (first.get('device_type') or '').lower()
    n_events   = len(events)

    if n_events <= 3:
        return 'bouncer'
    if ip_type == 'datacenter' or device == 'bot':
        return 'bot'
    if device in ('mobile', 'tablet'):
        return 'mobile'
    if device == 'desktop':
        return 'desktop'
    return 'unknown'

# ── CLI ───────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument('--org',          default=None)
parser.add_argument('--epochs',       type=int,   default=200)
parser.add_argument('--batch',        type=int,   default=8)
parser.add_argument('--lr',           type=float, default=3e-4)
parser.add_argument('--weights',      default=None, help='Resume from existing .pt')
parser.add_argument('--out',          default=str(MODELS_DIR / 'hgru.pt'))
parser.add_argument('--ch-host',      default=None)
parser.add_argument('--ch-user',      default=None)
parser.add_argument('--ch-password',  default=None)
args = parser.parse_args()

# Apply credentials
def _set(key, val, fallback=''):
    os.environ[key] = val or os.environ.get(key, fallback)

_set('CLICKHOUSE_HOST',     args.ch_host,
     'https://y390vosagc.us-east1.gcp.clickhouse.cloud:8443')
_set('CLICKHOUSE_USER',     args.ch_user,     'default')
_set('CLICKHOUSE_PASSWORD', args.ch_password, '')

if not os.environ['CLICKHOUSE_PASSWORD']:
    print('ERROR: pass --ch-password or set CLICKHOUSE_PASSWORD')
    sys.exit(1)

def ts():
    return datetime.now(tz=timezone.utc).strftime('%H:%M:%S')

DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f'[{ts()}] train_hgru.py  epochs={args.epochs}  batch={args.batch}  lr={args.lr}  device={DEVICE}')
if DEVICE.type == 'cuda':
    print(f'         GPU: {torch.cuda.get_device_name(0)}  '
          f'VRAM: {torch.cuda.get_device_properties(0).total_memory // 1024**3}GB')

# ── Load sessions ─────────────────────────────────────────────────────────
print(f'[{ts()}] Fetching sessions from ClickHouse...')

orgs = [args.org] if args.org else get_all_orgs()
if not orgs:
    print('ERROR: no orgs found in ClickHouse')
    sys.exit(1)

all_sessions: list[list[dict]] = []
robust = DEFAULT_ROBUST

for org_id in orgs:
    print(f'  org={org_id}')
    try:
        robust = get_robust_params(org_id)
    except Exception as e:
        print(f'  WARNING: robust params failed: {e}')

    # Single batch query — much faster than per-session queries
    all_events = get_all_session_events(org_id)
    print(f'  {len(all_events)} sessions')
    all_sessions.extend(all_events.values())

n = len(all_sessions)
print(f'[{ts()}] Total sessions loaded: {n}')

if n < 2:
    print('ERROR: need at least 2 sessions to train.')
    sys.exit(1)

# Show label distribution
from collections import Counter
label_counts = Counter(session_label(s) for s in all_sessions)
print(f'[{ts()}] Label distribution: {dict(label_counts)}')

# ── Build model ───────────────────────────────────────────────────────────
model = HierarchicalGRUEncoder(event_hidden=64, session_hidden=64, embed_dim=64)

weights_path = Path(args.weights) if args.weights else MODELS_DIR / 'hgru.pt'
if weights_path.exists():
    state = torch.load(weights_path, map_location='cpu', weights_only=True)
    model.load_state_dict(state)
    print(f'[{ts()}] Resumed from {weights_path}')
else:
    print(f'[{ts()}] Starting from random init')

model = model.to(DEVICE)
model.train()
optimizer = optim.Adam(model.parameters(), lr=args.lr, weight_decay=1e-4)
scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

# ── Pre-build and cache all tensors once ──────────────────────────────────
print(f'[{ts()}] Pre-building session tensors (cached for all epochs)...')
# Each entry: (pages_data_cpu, session_ctx_cpu, label)
# Tensors kept on CPU; moved to GPU per batch during training
CachedSession = tuple  # (pages_data, session_ctx, label)
cached: list[CachedSession] = []
for events in all_sessions:
    result = build_session_tensors(events, robust)
    if result is not None:
        pages_data, session_ctx = result
        cached.append((pages_data, session_ctx, session_label(events)))

valid_sessions = cached  # alias used below

n_valid = len(cached)
print(f'[{ts()}] Cached sessions: {n_valid} / {n}')
if n_valid < 4:
    print('ERROR: fewer than 4 valid sessions.')
    sys.exit(1)

# ── Training loop — VICReg with strong augmentation ───────────────────────
import random

batch_size        = min(args.batch, n_valid)
best_loss         = float('inf')
loss_history      = []

print(f'[{ts()}] Training (VICReg + strong augmentation)  '
      f'epochs={args.epochs}  batch={batch_size}')
print('─' * 60)

for epoch in range(1, args.epochs + 1):
    model.train()
    # Shuffle the (events, label) pairs; we only use events here
    random.shuffle(valid_sessions)

    epoch_losses = []
    for batch_start in range(0, n_valid, batch_size):
        batch = cached[batch_start : batch_start + batch_size]
        if len(batch) < 2:
            continue

        z1_list, z2_list = [], []
        for pages_data, session_ctx, _ in batch:
            # Two tensor-level augmented views — no Python feature re-engineering
            r1 = augment_tensors(pages_data, session_ctx)
            r2 = augment_tensors(pages_data, session_ctx)
            if r1 is None or r2 is None:
                continue

            pages1, ctx1 = r1
            pages2, ctx2 = r2
            pages1 = [(e.to(DEVICE), p.to(DEVICE)) for e, p in pages1]
            pages2 = [(e.to(DEVICE), p.to(DEVICE)) for e, p in pages2]
            ctx1, ctx2 = ctx1.to(DEVICE), ctx2.to(DEVICE)

            z1_list.append(model(pages1, ctx1))
            z2_list.append(model(pages2, ctx2))

        if len(z1_list) < 2:
            continue

        z1   = torch.stack(z1_list)
        z2   = torch.stack(z2_list)
        loss = vicreg_loss(z1, z2)

        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()

        epoch_losses.append(loss.item())

    scheduler.step()

    if not epoch_losses:
        continue

    avg_loss = sum(epoch_losses) / len(epoch_losses)
    loss_history.append(avg_loss)

    if epoch % 10 == 0 or epoch == 1:
        lr_now = scheduler.get_last_lr()[0]
        print(f'  epoch {epoch:>4}/{args.epochs}  loss={avg_loss:.4f}  lr={lr_now:.2e}')

    if avg_loss < best_loss:
        best_loss = avg_loss
        torch.save(model.state_dict(), args.out)

print('─' * 60)
print(f'[{ts()}] Training complete. Best loss: {best_loss:.4f}')
print(f'[{ts()}] Weights saved → {args.out}')

# ── Save loss history ─────────────────────────────────────────────────────
log_path = OUTPUT_DIR / 'hgru_loss.json'
with open(log_path, 'w') as f:
    json.dump({'loss_history': loss_history, 'best_loss': best_loss,
               'epochs': args.epochs, 'n_sessions': len(valid_sessions)}, f, indent=2)
print(f'[{ts()}] Loss log    → {log_path}')

# ── Quick sanity check ────────────────────────────────────────────────────
print(f'\n[{ts()}] Sanity check — embedding first 3 sessions:')
model.eval()
with torch.no_grad():
    for i, (pages_data, session_ctx, lbl) in enumerate(cached[:3]):
        pages = [(e.to(DEVICE), p.to(DEVICE)) for e, p in pages_data]
        ctx   = session_ctx.to(DEVICE)
        vec   = torch.nn.functional.normalize(model(pages, ctx), dim=-1)
        norm  = vec.norm().item()
        print(f'  session {i} [{lbl}]: norm={norm:.4f}  vec[:5]={vec[:5].tolist()}')
