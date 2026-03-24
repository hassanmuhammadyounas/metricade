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
from src.model import HierarchicalGRUEncoder, supervised_nt_xent_loss
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

# ── Pre-validate tensors ───────────────────────────────────────────────────
print(f'[{ts()}] Pre-validating session tensors...')
valid_sessions: list[tuple[list[dict], str]] = []  # (events, label)
for events in all_sessions:
    if build_session_tensors(events, robust) is not None:
        valid_sessions.append((events, session_label(events)))

n_valid = len(valid_sessions)
print(f'[{ts()}] Valid sessions: {n_valid} / {n}')
if n_valid < 4:
    print('ERROR: fewer than 4 valid sessions.')
    sys.exit(1)

# ── Training loop — supervised NT-Xent ────────────────────────────────────
import random
from collections import defaultdict

# Build per-label index for balanced sampling
label_to_sessions: dict[str, list] = defaultdict(list)
for item in valid_sessions:
    label_to_sessions[item[1]].append(item)

labels_present  = sorted(label_to_sessions.keys())
n_labels        = len(labels_present)
per_label       = max(2, min(args.batch // n_labels, 32))  # samples per class per batch
effective_batch = per_label * n_labels
best_loss       = float('inf')
loss_history    = []

print(f'[{ts()}] Training (supervised NT-Xent, balanced)  '
      f'epochs={args.epochs}  per_class={per_label}  effective_batch={effective_batch}')
print(f'[{ts()}] Classes: {labels_present}')
print('─' * 60)

# How many balanced batches per epoch (cover dataset at least once)
batches_per_epoch = max(1, n_valid // effective_batch)

for epoch in range(1, args.epochs + 1):
    model.train()

    epoch_losses = []
    for _ in range(batches_per_epoch):
        # Sample equal number of sessions from each class
        batch: list[tuple] = []
        for lbl in labels_present:
            pool = label_to_sessions[lbl]
            batch.extend(random.choices(pool, k=per_label))
        random.shuffle(batch)

        z_list:     list[torch.Tensor] = []
        label_list: list[str]          = []

        for events, label in batch:
            r = build_session_tensors(events, robust)
            if r is None:
                continue
            pages, ctx = r
            pages = [(e.to(DEVICE), p.to(DEVICE)) for e, p in pages]
            ctx   = ctx.to(DEVICE)
            z_list.append(model(pages, ctx))
            label_list.append(label)

        if len(z_list) < 2 or len(set(label_list)) < 2:
            continue

        z    = torch.stack(z_list)          # (batch, embed_dim)
        loss = supervised_nt_xent_loss(z, label_list, temperature=0.05)

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
    for i, (events, lbl) in enumerate(valid_sessions[:3]):
        result = build_session_tensors(events, robust)
        if result:
            pages, ctx = result
            pages = [(e.to(DEVICE), p.to(DEVICE)) for e, p in pages]
            ctx   = ctx.to(DEVICE)
            vec   = model(pages, ctx)
            norm  = vec.norm().item()
            print(f'  session {i}: norm={norm:.4f}  vec[:5]={vec[:5].tolist()}')
