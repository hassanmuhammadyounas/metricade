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
from src.model import HierarchicalGRUEncoder, augment_events, vicreg_loss
from src.clickhouse import (
    get_all_orgs, get_sessions_updated_since, get_session_events, get_robust_params,
)
from src.constants import DEFAULT_ROBUST

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

    session_ids = get_sessions_updated_since('2000-01-01 00:00:00', org_id=org_id)
    print(f'  {len(session_ids)} sessions')

    for sid in session_ids:
        try:
            events = get_session_events(sid)
            if events:
                all_sessions.append(events)
        except Exception as e:
            print(f'  WARNING session={sid}: {e}')

n = len(all_sessions)
print(f'[{ts()}] Total sessions loaded: {n}')

if n < 2:
    print('ERROR: need at least 2 sessions to train. Collect more data first.')
    sys.exit(1)

if n < 8:
    print(f'WARNING: only {n} sessions — VICReg covariance term will be weak. '
          f'Results improve significantly with 50+ sessions.')

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

# ── Pre-build tensors (without augmentation) for caching ─────────────────
# We'll apply augmentation on-the-fly each epoch
print(f'[{ts()}] Pre-validating session tensors...')
valid_sessions = []
for events in all_sessions:
    result = build_session_tensors(events, robust)
    if result is not None:
        valid_sessions.append(events)

print(f'[{ts()}] Valid sessions: {len(valid_sessions)} / {n}')
if len(valid_sessions) < 2:
    print('ERROR: fewer than 2 valid sessions after tensor validation.')
    sys.exit(1)

# ── Training loop ─────────────────────────────────────────────────────────
import random

batch_size   = min(args.batch, len(valid_sessions))
best_loss    = float('inf')
loss_history = []

print(f'[{ts()}] Training  epochs={args.epochs}  batch_size={batch_size}')
print('─' * 60)

for epoch in range(1, args.epochs + 1):
    model.train()
    random.shuffle(valid_sessions)

    epoch_losses = []
    for batch_start in range(0, len(valid_sessions), batch_size):
        batch = valid_sessions[batch_start : batch_start + batch_size]
        if len(batch) < 2:
            continue

        z1_list, z2_list = [], []
        for events in batch:
            aug1 = augment_events(events, drop_rate=0.15)
            aug2 = augment_events(events, drop_rate=0.15)

            r1 = build_session_tensors(aug1, robust)
            r2 = build_session_tensors(aug2, robust)
            if r1 is None or r2 is None:
                continue

            pages1, ctx1 = r1
            pages2, ctx2 = r2

            # Move tensors to device
            pages1 = [(e.to(DEVICE), p.to(DEVICE)) for e, p in pages1]
            pages2 = [(e.to(DEVICE), p.to(DEVICE)) for e, p in pages2]
            ctx1, ctx2 = ctx1.to(DEVICE), ctx2.to(DEVICE)

            z1_list.append(model(pages1, ctx1))
            z2_list.append(model(pages2, ctx2))

        if len(z1_list) < 2:
            continue

        z1 = torch.stack(z1_list)  # (batch, embed_dim)
        z2 = torch.stack(z2_list)

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
    for i, events in enumerate(valid_sessions[:3]):
        result = build_session_tensors(events, robust)
        if result:
            pages, ctx = result
            pages = [(e.to(DEVICE), p.to(DEVICE)) for e, p in pages]
            ctx   = ctx.to(DEVICE)
            vec   = model(pages, ctx)
            norm  = vec.norm().item()
            print(f'  session {i}: norm={norm:.4f}  vec[:5]={vec[:5].tolist()}')
