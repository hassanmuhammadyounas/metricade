"""
AEGIS Sequence Autoencoder + HDBSCAN  v4
=========================================
Changes vs v3:
  - Dead-feature filtering: features with per-feature std < DEAD_FEAT_THRESHOLD
    are dropped before training (they give the model a free reconstruction target).
  - VICReg variance term: penalises per-dim bottleneck std < 1.0 across the batch.
    Prevents the model from collapsing all sessions to the same embedding.
  - VIC_WEIGHT hyperparameter (default 0.25) controls the trade-off.
  - Dead-feature mask saved in norm_params so downstream code can realign dims.

Usage:
  python aegis_autoencoder.py [ORG_ID ...]

  If no ORG_IDs are supplied, the script scans Redis for all orgs.
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import io
import json
import logging
import os
import sys
import time
from pathlib import Path

import hdbscan
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
import umap
from torch.utils.data import DataLoader, TensorDataset

# ---------------------------------------------------------------------------
# Redis client (Upstash REST)
# ---------------------------------------------------------------------------
try:
    from upstash_redis import Redis
except ImportError:
    raise SystemExit("pip install upstash-redis")

REDIS_URL   = "https://singular-fawn-58838.upstash.io"
REDIS_TOKEN = "AeXWAAIncDIyYThjM2Y1NTMxNDA0MjQ5YjViNGJhMTE0Y2VkZGNiN3AyNTg4Mzg"

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
CFG = dict(
    BOTTLENECK_DIM       = 32,
    EPOCHS               = 100,       # bumped from 50 — more time to learn variance
    BATCH_SIZE           = 64,
    LEARNING_RATE        = 5e-4,      # slightly lower — more stable with joint loss
    HUBER_DELTA          = 0.5,
    VIC_WEIGHT           = 0.25,      # NEW: weight on variance regularisation term
    LSTM_HIDDEN          = 128,       # NEW: doubled — gives the bottleneck more to work with
    LSTM_LAYERS          = 2,
    DEAD_FEAT_THRESHOLD  = 1e-5,      # NEW: per-feature std below this = dead, drop it
    NUM_WORKERS          = 10,
    FETCH_BATCH_SIZE     = 100,
    HDBSCAN_MIN_SIZE     = 50,
    HDBSCAN_MIN_SAMPLES  = 10,
    MAX_SESSIONS         = None,      # set to int to cap (debug)
    UMAP_N_NEIGHBORS     = 15,
    UMAP_MIN_DIST        = 0.1,
)

OUTPUT_ROOT = Path("scripts/output/aegis_autoencoder")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_FMT = "%(asctime)s  %(levelname)-8s  %(message)s"
DATE_FMT = "%H:%M:%S"

def make_logger(org_id: str, log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(org_id)
    logger.setLevel(logging.DEBUG)
    if logger.handlers:
        logger.handlers.clear()
    fh = logging.FileHandler(log_path)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(LOG_FMT, datefmt=DATE_FMT))
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(LOG_FMT, datefmt=DATE_FMT))
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger

# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------
def get_redis() -> Redis:
    return Redis(url=REDIS_URL, token=REDIS_TOKEN)


def scan_org_keys(r: Redis, org_id: str, log: logging.Logger) -> list[str]:
    pattern = f"metricade_features:{org_id}:*"
    keys: list[str] = []
    cursor = 0
    page = 0
    while True:
        cursor, batch = r.scan(cursor, match=pattern, count=500)
        keys.extend(batch)
        page += 1
        if cursor == 0:
            break
    log.debug(f" SCAN '{pattern}': {len(keys):,} keys ({page} pages)")
    return keys


def _fetch_batch(args):
    url, token, batch_keys = args
    r = Redis(url=url, token=token)
    results = r.mget(*batch_keys)
    return batch_keys, results


def fetch_tensors(
    keys: list[str],
    log: logging.Logger,
) -> dict[str, np.ndarray]:
    """Fetch base64-encoded .npy tensors from Redis in parallel."""
    batch_size = CFG["FETCH_BATCH_SIZE"]
    batches = [keys[i : i + batch_size] for i in range(0, len(keys), batch_size)]
    n_workers = CFG["NUM_WORKERS"]
    log.info(f"  Fetching {len(keys):,} keys — {len(batches)} batches × {batch_size}, {n_workers} workers")

    args = [(REDIS_URL, REDIS_TOKEN, b) for b in batches]
    t0 = time.time()
    out: dict[str, np.ndarray] = {}
    missing = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as ex:
        for batch_keys, results in ex.map(_fetch_batch, args):
            for key, val in zip(batch_keys, results):
                if val is None:
                    missing += 1
                    continue
                try:
                    raw = base64.b64decode(val)
                    loaded = np.load(io.BytesIO(raw), allow_pickle=False)
                    # Feature store saves npz with key 'cont' (shape [256, N_CONT])
                    if hasattr(loaded, 'files'):
                        arr = loaded['cont']
                    else:
                        arr = loaded
                    out[key] = arr
                except Exception:
                    missing += 1

    log.info(f"  Fetch done: {len(out):,} with data, {missing} missing  ({time.time()-t0:.1f}s)")
    return out


def discover_orgs(r: Redis, log: logging.Logger) -> list[str]:
    """Scan Redis for all org_IDs present in metricade_features keys."""
    pattern = "metricade_features:*"
    seen: set[str] = set()
    cursor = 0
    while True:
        cursor, batch = r.scan(cursor, match=pattern, count=500)
        for k in batch:
            parts = k.split(":")
            if len(parts) >= 2:
                seen.add(parts[1])
        if cursor == 0:
            break
    return sorted(seen)

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
class LSTMAutoencoder(nn.Module):
    """
    Encoder: LSTM → linear projection to bottleneck.
    Decoder: repeat bottleneck → LSTM → linear projection to feature dim.
    """

    def __init__(self, feat_dim: int, hidden: int, layers: int, bottleneck: int):
        super().__init__()
        self.feat_dim   = feat_dim
        self.hidden     = hidden
        self.layers     = layers
        self.bottleneck = bottleneck

        # Encoder
        self.enc_lstm  = nn.LSTM(feat_dim, hidden, layers, batch_first=True)
        self.enc_proj  = nn.Linear(hidden, bottleneck)

        # Decoder
        self.dec_expand = nn.Linear(bottleneck, hidden)
        self.dec_lstm   = nn.LSTM(hidden, hidden, layers, batch_first=True)
        self.dec_proj   = nn.Linear(hidden, feat_dim)

    def encode(self, x: torch.Tensor) -> torch.Tensor:
        # x: [B, T, F]
        _, (h, _) = self.enc_lstm(x)       # h: [layers, B, hidden]
        z = self.enc_proj(h[-1])            # [B, bottleneck]
        return z

    def decode(self, z: torch.Tensor, seq_len: int) -> torch.Tensor:
        # z: [B, bottleneck]
        h0 = self.dec_expand(z)             # [B, hidden]
        h0 = h0.unsqueeze(0).repeat(self.layers, 1, 1)  # [layers, B, hidden]
        c0 = torch.zeros_like(h0)

        # Repeat z as input at every timestep
        dec_in = self.dec_expand(z).unsqueeze(1).repeat(1, seq_len, 1)  # [B, T, hidden]
        out, _ = self.dec_lstm(dec_in, (h0, c0))   # [B, T, hidden]
        recon  = self.dec_proj(out)                  # [B, T, F]
        return recon

    def forward(self, x: torch.Tensor):
        z     = self.encode(x)
        recon = self.decode(z, x.size(1))
        return recon, z


def vic_variance_loss(z: torch.Tensor, eps: float = 1e-4) -> torch.Tensor:
    """
    VICReg variance term.
    Penalises each bottleneck dimension whose std across the batch < 1.0.
    Forces the encoder to spread sessions apart in embedding space.
    """
    std = torch.sqrt(z.var(dim=0) + eps)          # [bottleneck]
    loss = F.relu(1.0 - std).pow(2).mean()
    return loss

# ---------------------------------------------------------------------------
# Main per-org pipeline
# ---------------------------------------------------------------------------
def run_org(org_id: str, r: Redis):
    out_dir  = OUTPUT_ROOT / org_id
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / f"run_{org_id}.log"
    log      = make_logger(org_id, log_path)

    SEP = "─" * 70

    log.info("=" * 70)
    log.info("AEGIS Sequence Autoencoder + HDBSCAN  v4")
    log.info("=" * 70)
    log.info(f"Org      : {org_id}")
    log.info(f"Log file : {log_path}")
    log.info("CONFIG:")
    for k, v in CFG.items():
        log.info(f"  {k:<25} = {v}")
    log.info(SEP)

    t_total = time.time()

    # ------------------------------------------------------------------
    # STEP 1 — skipped (config logged above)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # STEP 2 — LOAD AEGIS TENSORS
    # ------------------------------------------------------------------
    log.info(f"STEP 2/5 — LOADING AEGIS TENSORS  (org={org_id})")

    keys = scan_org_keys(r, org_id, log)
    if not keys:
        log.warning("No AEGIS keys found — skipping org.")
        return

    log.info(f"  AEGIS keys found: {len(keys):,}")

    if CFG["MAX_SESSIONS"]:
        keys = keys[: CFG["MAX_SESSIONS"]]
        log.info(f"  Capped to {len(keys):,} sessions (MAX_SESSIONS)")

    raw_data = fetch_tensors(keys, log)
    session_ids: list[str] = []
    tensors:     list[np.ndarray] = []

    n_feat = None  # inferred from first valid tensor
    for key, arr in raw_data.items():
        sid = key.split(":")[-1]
        # Expect shape [T, F] where F = N_CONT (currently 41, previously 40)
        if arr.ndim != 2:
            continue
        if n_feat is None:
            n_feat = arr.shape[1]
        if arr.shape[1] != n_feat:
            continue  # skip tensors from a different schema version
        if arr.shape[0] >= 256:
            arr = arr[:256]
        else:
            pad = np.zeros((256 - arr.shape[0], arr.shape[1]), dtype=np.float32)
            arr = np.vstack([arr, pad])
        session_ids.append(sid)
        tensors.append(arr.astype(np.float32))

    log.info(f"  Loaded:  {len(tensors):,}  Skipped: {len(raw_data)-len(tensors)}  feat_dim={n_feat}")

    if len(tensors) < 2:
        log.warning("Fewer than 2 valid sessions — skipping org.")
        return

    X = np.stack(tensors)  # [N, 256, 40]
    log.info(f"  Raw matrix : {X.shape}")
    log.info(f"  Raw range  : min={X.min():.4f}  max={X.max():.4f}  mean={X.mean():.6f}  std={X.std():.4f}")

    # ------------------------------------------------------------------
    # STEP 2b — NORMALISE + DROP DEAD FEATURES
    # ------------------------------------------------------------------
    log.info("  Applying per-feature z-score normalisation...")

    feat_mean = X.mean(axis=(0, 1))          # [40]
    feat_std  = X.std(axis=(0, 1))           # [40]

    # Identify live features
    threshold     = CFG["DEAD_FEAT_THRESHOLD"]
    live_mask     = feat_std > threshold      # [40] bool
    dead_indices  = np.where(~live_mask)[0]
    live_indices  = np.where(live_mask)[0]
    n_dead        = int((~live_mask).sum())
    n_live        = int(live_mask.sum())

    log.info(f"  Features with near-zero std (dead, dropping): {n_dead}/40")
    if n_dead:
        log.debug(f"  Dead feature indices: {dead_indices.tolist()}")

    # Z-score using live-feature stats
    X_norm = np.zeros_like(X)
    for f in live_indices:
        X_norm[:, :, f] = (X[:, :, f] - feat_mean[f]) / feat_std[f]
    # dead features stay zero — then we slice them out
    X_norm = X_norm[:, :, live_mask]         # [N, 256, n_live]

    log.info(f"  Normalised shape : {X_norm.shape}")
    log.info(f"  Normalised range : min={X_norm.min():.4f}  max={X_norm.max():.4f}  mean={X_norm.mean():.6f}  std={X_norm.std():.4f}")

    # Save norm params (include live_mask so downstream can reconstruct)
    norm_path = out_dir / f"norm_params_{org_id}.npz"
    np.savez(norm_path, feat_mean=feat_mean, feat_std=feat_std,
             live_mask=live_mask, live_indices=live_indices, dead_indices=dead_indices)
    log.info(f"  Norm params saved: {norm_path}")
    log.info(SEP)

    # ------------------------------------------------------------------
    # STEP 3 — LSTM AUTOENCODER TRAINING
    # ------------------------------------------------------------------
    log.info("STEP 3/5 — LSTM AUTOENCODER TRAINING")

    N, T, F = X_norm.shape
    device  = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    log.info(f"  Input shape     : {X_norm.shape}")
    log.info(f"  Live features   : {n_live}/40  (dead={n_dead} dropped)")
    log.info(f"  Bottleneck dim  : {CFG['BOTTLENECK_DIM']}")
    log.info(f"  LSTM hidden     : {CFG['LSTM_HIDDEN']}")
    log.info(f"  LSTM layers     : {CFG['LSTM_LAYERS']}")
    log.info(f"  Epochs          : {CFG['EPOCHS']}")
    log.info(f"  Batch size      : {CFG['BATCH_SIZE']}")
    log.info(f"  Learning rate   : {CFG['LEARNING_RATE']}")
    log.info(f"  Loss            : HuberLoss(delta={CFG['HUBER_DELTA']}) + {CFG['VIC_WEIGHT']}×VICvar")
    log.info(f"  Device          : {device}")

    X_t     = torch.tensor(X_norm, dtype=torch.float32)
    dataset = TensorDataset(X_t)
    loader  = DataLoader(dataset, batch_size=CFG["BATCH_SIZE"], shuffle=True, drop_last=False)

    model = LSTMAutoencoder(
        feat_dim   = F,
        hidden     = CFG["LSTM_HIDDEN"],
        layers     = CFG["LSTM_LAYERS"],
        bottleneck = CFG["BOTTLENECK_DIM"],
    ).to(device)

    n_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    log.info(f"  Model params    : {n_params:,}")
    log.info(f"  Steps/epoch     : {len(loader)}")
    log.info("")

    optimizer   = torch.optim.Adam(model.parameters(), lr=CFG["LEARNING_RATE"])
    huber       = nn.HuberLoss(delta=CFG["HUBER_DELTA"])
    vic_weight  = CFG["VIC_WEIGHT"]
    loss_history: list[float] = []
    recon_history: list[float] = []
    var_history:  list[float] = []

    t_train = time.time()
    first_loss = None

    for epoch in range(1, CFG["EPOCHS"] + 1):
        model.train()
        epoch_recon = 0.0
        epoch_var   = 0.0
        n_batches   = 0

        for (xb,) in loader:
            xb = xb.to(device)
            recon, z = model(xb)

            loss_recon = huber(recon, xb)
            loss_var   = vic_variance_loss(z)
            loss       = loss_recon + vic_weight * loss_var

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

            epoch_recon += loss_recon.item()
            epoch_var   += loss_var.item()
            n_batches   += 1

        avg_recon = epoch_recon / n_batches
        avg_var   = epoch_var   / n_batches
        avg_total = avg_recon + vic_weight * avg_var
        loss_history.append(avg_total)
        recon_history.append(avg_recon)
        var_history.append(avg_var)

        if first_loss is None:
            first_loss = avg_total

        elapsed = time.time() - t_train
        eta     = elapsed / epoch * (CFG["EPOCHS"] - epoch)

        if epoch == 1 or epoch % 5 == 0 or epoch == CFG["EPOCHS"]:
            log.info(
                f"  Epoch {epoch:3d}/{CFG['EPOCHS']}  "
                f"total={avg_total:.6f}  recon={avg_recon:.6f}  var={avg_var:.6f}  "
                f"elapsed={elapsed:.1f}s  ETA={eta:.1f}s"
            )

    elapsed_train = time.time() - t_train
    log.info("")
    log.info(f"  Training complete : {elapsed_train:.1f}s")
    log.info(f"  Final loss (total): {loss_history[-1]:.6f}")
    log.info(f"  Final recon loss  : {recon_history[-1]:.6f}")
    log.info(f"  Final var  loss   : {var_history[-1]:.6f}")
    log.info(f"  Loss reduction    : {first_loss:.6f} → {loss_history[-1]:.6f}  ({(first_loss-loss_history[-1])/first_loss*100:.1f}%)")

    # Loss curve
    loss_curve_path = out_dir / f"loss_curve_{org_id}.png"
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    ax1.plot(loss_history,  label="Total loss", color="steelblue")
    ax1.plot(recon_history, label="Recon loss",  color="coral",     linestyle="--")
    ax1.set_ylabel("Loss"); ax1.legend(); ax1.set_title(f"Training — {org_id}")
    ax2.plot(var_history, label="VIC var loss", color="seagreen")
    ax2.set_ylabel("Var loss"); ax2.set_xlabel("Epoch"); ax2.legend()
    plt.tight_layout()
    plt.savefig(loss_curve_path, dpi=120)
    plt.close()
    log.info(f"  Loss curve saved  : {loss_curve_path}")

    # Extract bottleneck embeddings
    model.eval()
    all_z: list[np.ndarray] = []
    with torch.no_grad():
        for i in range(0, N, CFG["BATCH_SIZE"]):
            xb = X_t[i : i + CFG["BATCH_SIZE"]].to(device)
            z  = model.encode(xb)
            all_z.append(z.cpu().numpy())

    embeddings = np.vstack(all_z)   # [N, bottleneck]
    log.info(f"  Embeddings shape  : {embeddings.shape}")
    log.info(f"  Embedding range   : min={embeddings.min():.4f}  max={embeddings.max():.4f}")

    per_dim_std = embeddings.std(axis=0)
    log.info(f"  Per-dim std       : min={per_dim_std.min():.4f}  max={per_dim_std.max():.4f}  mean={per_dim_std.mean():.4f}")

    collapsed = per_dim_std.max() < 1e-3
    if collapsed:
        log.warning("!! COLLAPSE DETECTED — embedding std still near zero.")
        log.warning("   Try: VIC_WEIGHT=0.5, EPOCHS=150, LSTM_HIDDEN=256")
    else:
        log.info("  Collapse check: PASSED — embeddings have meaningful variance.")

    emb_path = out_dir / f"embeddings_{org_id}.npy"
    np.save(emb_path, embeddings)
    log.info(f"  Embeddings saved  : {emb_path}")
    log.info(SEP)

    # ------------------------------------------------------------------
    # STEP 4 — UMAP + HDBSCAN
    # ------------------------------------------------------------------
    log.info("STEP 4/5 — UMAP + HDBSCAN CLUSTERING")

    if N < 20:
        log.warning(f"Only {N} sessions — need >= 20 for UMAP+HDBSCAN.")
        log.info("SKIPPED clustering — collect more data")
        return

    log.info(f"  Input shape          : {embeddings.shape}")
    log.info(f"  HDBSCAN_MIN_SIZE     : {CFG['HDBSCAN_MIN_SIZE']}")
    log.info(f"  HDBSCAN_MIN_SAMPLES  : {CFG['HDBSCAN_MIN_SAMPLES']}")

    # UMAP 10D for clustering
    log.info("  Running UMAP 10D (clustering input)...")
    t0 = time.time()
    reducer_10d = umap.UMAP(
        n_components  = 10,
        n_neighbors   = CFG["UMAP_N_NEIGHBORS"],
        min_dist      = CFG["UMAP_MIN_DIST"],
        metric        = "euclidean",
        random_state  = 42,
    )
    umap_10d = reducer_10d.fit_transform(embeddings)
    log.info(f"  UMAP 10D done in {time.time()-t0:.1f}s")

    # UMAP 2D for visualisation
    log.info("  Running UMAP 2D (visualisation)...")
    t0 = time.time()
    reducer_2d = umap.UMAP(
        n_components  = 2,
        n_neighbors   = CFG["UMAP_N_NEIGHBORS"],
        min_dist      = CFG["UMAP_MIN_DIST"],
        metric        = "euclidean",
        random_state  = 42,
    )
    umap_2d = reducer_2d.fit_transform(embeddings)
    log.info(f"  UMAP 2D done in {time.time()-t0:.1f}s")

    # HDBSCAN on 10D
    log.info("  Running HDBSCAN...")
    t0 = time.time()
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size  = CFG["HDBSCAN_MIN_SIZE"],
        min_samples       = CFG["HDBSCAN_MIN_SAMPLES"],
        prediction_data   = True,
    )
    labels      = clusterer.fit_predict(umap_10d)
    memb_probs  = clusterer.probabilities_
    outlier_sc  = clusterer.outlier_scores_
    log.info(f"  HDBSCAN done in {time.time()-t0:.1f}s")

    n_clusters   = int(labels.max()) + 1
    n_noise      = int((labels == -1).sum())
    log.info("")
    log.info(f"  Clusters found   : {n_clusters}")
    log.info(f"  Noise sessions   : {n_noise}  ({n_noise/N*100:.1f}%)")
    log.info("")

    # Per-cluster summary
    header = f"  {'Cluster':>10}  {'Count':>8}  {'Avg membership':>16}  {'Avg outlier':>12}"
    log.info(header)
    log.info("  " + "─" * 53)
    unique = sorted(set(labels))
    for lbl in unique:
        mask  = labels == lbl
        name  = "NOISE" if lbl == -1 else f"C{lbl}"
        count = int(mask.sum())
        avg_m = float(memb_probs[mask].mean())
        avg_o = float(outlier_sc[mask].mean()) if outlier_sc is not None else 0.0
        log.info(f"  {name:>10}  {count:>8}  {avg_m:>16.4f}  {avg_o:>12.4f}")

    log.info(SEP)

    # ------------------------------------------------------------------
    # STEP 5 — SAVE OUTPUTS
    # ------------------------------------------------------------------
    log.info("STEP 5/5 — SAVING OUTPUTS")

    # CSV
    df = pd.DataFrame({
        "session_id"      : session_ids,
        "cluster_id"      : labels,
        "membership_prob" : memb_probs,
        "outlier_score"   : outlier_sc if outlier_sc is not None else np.zeros(N),
        "umap_x"          : umap_2d[:, 0],
        "umap_y"          : umap_2d[:, 1],
    })
    csv_path = out_dir / f"clusters_{org_id}.csv"
    df.to_csv(csv_path, index=False)
    log.info(f"  CSV saved: {csv_path}")

    # Plot
    plot_path = out_dir / f"plot_{org_id}.png"
    fig, ax   = plt.subplots(figsize=(14, 10))
    cmap      = plt.get_cmap("tab20")
    noise_mask = labels == -1
    ax.scatter(umap_2d[noise_mask, 0], umap_2d[noise_mask, 1],
               c="lightgray", s=15, alpha=0.5, label=f"NOISE (n={noise_mask.sum()})", zorder=1)
    for lbl in range(n_clusters):
        mask = labels == lbl
        if not mask.any():
            continue
        color = cmap(lbl % 20)
        ax.scatter(umap_2d[mask, 0], umap_2d[mask, 1],
                   c=[color], s=20, alpha=0.7, label=f"C{lbl} (n={mask.sum()})", zorder=2)

    ax.set_title(f"AEGIS Autoencoder Embeddings — {org_id} (n={N:,} clusters={n_clusters})")
    ax.set_xlabel("UMAP-1"); ax.set_ylabel("UMAP-2")
    # Legend: only show if not too many clusters
    if n_clusters <= 30:
        ax.legend(fontsize=7, ncol=2, loc="upper right")
    else:
        ax.text(0.01, 0.99, f"{n_clusters} clusters, {n_noise} noise",
                transform=ax.transAxes, va="top", fontsize=9)
    plt.tight_layout()
    plt.savefig(plot_path, dpi=120)
    plt.close()
    log.info(f"  Plot saved: {plot_path}")

    total_elapsed = time.time() - t_total
    log.info(f"  Output folder: {out_dir.resolve()}")
    log.info("  Files:")
    for f in sorted(out_dir.iterdir()):
        log.info(f"    {f.name}")
    log.info(SEP)
    log.info(f"COMPLETE  {total_elapsed:.1f}s  ({total_elapsed/60:.1f} min)")
    log.info("=" * 70)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="AEGIS Sequence Autoencoder v4")
    parser.add_argument("org_ids", nargs="*", help="Org IDs to process. Omit to auto-discover.")
    parser.add_argument("--epochs",      type=int,   default=None)
    parser.add_argument("--hidden",      type=int,   default=None)
    parser.add_argument("--vic-weight",  type=float, default=None)
    parser.add_argument("--bottleneck",  type=int,   default=None)
    parser.add_argument("--lr",          type=float, default=None)
    parser.add_argument("--max-sessions",type=int,   default=None)
    args = parser.parse_args()

    # CLI overrides
    if args.epochs      is not None: CFG["EPOCHS"]       = args.epochs
    if args.hidden      is not None: CFG["LSTM_HIDDEN"]  = args.hidden
    if args.vic_weight  is not None: CFG["VIC_WEIGHT"]   = args.vic_weight
    if args.bottleneck  is not None: CFG["BOTTLENECK_DIM"] = args.bottleneck
    if args.lr          is not None: CFG["LEARNING_RATE"]  = args.lr
    if args.max_sessions is not None: CFG["MAX_SESSIONS"] = args.max_sessions

    r = get_redis()

    org_ids = args.org_ids
    if not org_ids:
        print("No org IDs supplied — auto-discovering from Redis...")
        org_ids = discover_orgs(r, logging.getLogger("discover"))
        print(f"Found orgs: {org_ids}")

    if not org_ids:
        sys.exit("No orgs found in Redis. Check REDIS credentials and key prefix.")

    for org_id in org_ids:
        run_org(org_id, r)


if __name__ == "__main__":
    main()