"""
AEGIS Sequence Autoencoder + HDBSCAN
=====================================
Pipeline:
  1. Discover orgs — count sessions in BOUNTY RUNE, OBSERVER WARD, AEGIS
  2. Load AEGIS tensors [256×40] per session
  3. Train sequence autoencoder → bottleneck embeddings (32-dim)
  4. Save embeddings
  5. Run HDBSCAN on embeddings
  6. Save cluster assignments + plot

Data sources (Dota 2 names):
  BOUNTY RUNE  = metricade_stream:{org_id}
  OBSERVER WARD = metricade_sess:{org_id}:{session_id}
  AEGIS        = metricade_features:{org_id}:{session_id}

ADJUSTABLE PARAMETERS (CONFIG block):
  BOTTLENECK_DIM    — autoencoder compressed size (default 32)
  EPOCHS            — training epochs (default 30)
  BATCH_SIZE        — training batch size (default 64)
  LEARNING_RATE     — adam lr (default 1e-3)
  NUM_WORKERS       — parallel Redis fetch threads (default 10)
  FETCH_BATCH_SIZE  — keys per pipeline call (default 100)
  HDBSCAN_MIN_SIZE  — min sessions per cluster (default 50, tune this first)
  HDBSCAN_MIN_SAMPLES — core point density (default 10)
  MAX_SESSIONS      — cap sessions for training (None = all)

Usage:
  python aegis_autoencoder_hdbscan.py --org org_XXXX
  python aegis_autoencoder_hdbscan.py  # auto-discovers all orgs
"""

import argparse
import base64
import io
import json
import logging
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ── Auto-install ──────────────────────────────────────────────────────────────
import subprocess
REQUIRED = [
    ("httpx",         "httpx"),
    ("numpy",         "numpy"),
    ("torch",         "torch"),
    ("scikit-learn",  "sklearn"),
    ("umap-learn",    "umap"),
    ("hdbscan",       "hdbscan"),
    ("matplotlib",    "matplotlib"),
]
for pkg, imp in REQUIRED:
    try:
        __import__(imp)
    except ImportError:
        print(f"[install] {pkg}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

import httpx
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════════════════════
CONFIG = {
    "BOTTLENECK_DIM":    32,    # compressed embedding size — tune: 16/32/64
    "EPOCHS":            50,    # training epochs — LSTM needs more than linear
    "BATCH_SIZE":        64,    # training batch size
    "LEARNING_RATE":     1e-3,  # adam learning rate
    "NUM_WORKERS":       10,    # parallel Redis fetch threads
    "FETCH_BATCH_SIZE":  100,   # keys per pipeline call
    "HDBSCAN_MIN_SIZE":  50,    # min sessions per cluster — tune this first
    "HDBSCAN_MIN_SAMPLES": 10,  # density requirement
    "MAX_SESSIONS":      None,  # None = all sessions; set int to cap
    "UMAP_N_NEIGHBORS":  15,
    "UMAP_MIN_DIST":     0.1,
}

OUT_BASE = Path("scripts/output/aegis_autoencoder")

# AEGIS tensor shape
SEQ_LEN  = 256
N_CONT   = 40
N_CAT    = 8


# ══════════════════════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════════════════════
def setup_logging(out_dir: Path, org_id: str) -> logging.Logger:
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / f"run_{org_id}.log"
    fmt = logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S")

    log = logging.getLogger(f"aegis_{org_id}")
    log.setLevel(logging.DEBUG)
    log.handlers.clear()

    fh = logging.FileHandler(log_path, mode="w")
    fh.setFormatter(fmt); fh.setLevel(logging.DEBUG)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt); ch.setLevel(logging.INFO)

    log.addHandler(fh); log.addHandler(ch)

    log.info("=" * 70)
    log.info("AEGIS Sequence Autoencoder + HDBSCAN")
    log.info("=" * 70)
    log.info(f"Org      : {org_id}")
    log.info(f"Log file : {log_path}")
    log.info("CONFIG:")
    for k, v in CONFIG.items():
        log.info(f"  {k:<25} = {v}")
    return log


# ══════════════════════════════════════════════════════════════════════════════
# ENV
# ══════════════════════════════════════════════════════════════════════════════
def load_env(log: logging.Logger):
    for p in [Path(__file__).resolve().parent / ".env",
              Path(__file__).resolve().parent.parent / ".env"]:
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
            log.info(f"Env loaded from: {p}")
            return
    log.warning("No .env found — using environment variables")


# ══════════════════════════════════════════════════════════════════════════════
# REDIS HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def scan_keys(pattern: str, url: str, token: str, log: logging.Logger) -> list[str]:
    keys, cursor, pages = [], "0", 0
    while True:
        r = httpx.post(f"{url}/pipeline",
                       headers={"Authorization": f"Bearer {token}"},
                       json=[["SCAN", cursor, "MATCH", pattern, "COUNT", "500"]],
                       timeout=30)
        r.raise_for_status()
        result = r.json()[0]["result"]
        cursor, batch = result[0], result[1]
        keys.extend(batch); pages += 1
        if cursor == "0":
            break
    log.debug(f"  SCAN '{pattern}': {len(keys):,} keys ({pages} pages)")
    return keys


def xlen(stream_key: str, url: str, token: str) -> int:
    r = httpx.post(f"{url}/pipeline",
                   headers={"Authorization": f"Bearer {token}"},
                   json=[["XLEN", stream_key]], timeout=15)
    r.raise_for_status()
    return r.json()[0].get("result", 0) or 0


def _fetch_batch(args):
    keys, url, token = args
    try:
        r = httpx.post(f"{url}/pipeline",
                       headers={"Authorization": f"Bearer {token}"},
                       json=[["GET", k] for k in keys], timeout=30)
        r.raise_for_status()
        return [(keys[i], r.json()[i].get("result")) for i in range(len(keys))]
    except Exception:
        return [(k, None) for k in keys]


def fetch_parallel(keys: list[str], url: str, token: str,
                   log: logging.Logger) -> dict[str, str | None]:
    bs = CONFIG["FETCH_BATCH_SIZE"]
    nw = CONFIG["NUM_WORKERS"]
    batches = [(keys[i:i+bs], url, token) for i in range(0, len(keys), bs)]
    log.info(f"  Fetching {len(keys):,} keys — {len(batches)} batches × {bs} keys, {nw} workers")

    results = {}
    done = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=nw) as pool:
        futures = {pool.submit(_fetch_batch, b): b for b in batches}
        for fut in as_completed(futures):
            for k, v in fut.result():
                results[k] = v
            done += len(futures[fut])
            elapsed = time.time() - t0
            print(f"\r  Fetched {min(done, len(keys)):>6,}/{len(keys):,}  "
                  f"({done/elapsed:.0f} keys/s)", end="", flush=True)
    print()
    null_count = sum(1 for v in results.values() if v is None)
    log.info(f"  Fetch done: {len(results)-null_count:,} with data, {null_count:,} missing  "
             f"({time.time()-t0:.1f}s)")
    return results


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — ORG DISCOVERY
# ══════════════════════════════════════════════════════════════════════════════
def discover_orgs(url: str, token: str, log: logging.Logger) -> list[str]:
    log.info("─" * 70)
    log.info("STEP 1/5 — ORG DISCOVERY")
    log.info("Scanning for all org IDs across BOUNTY RUNE, OBSERVER WARD, AEGIS")

    stream_keys  = scan_keys("metricade_stream:*",   url, token, log)
    sess_keys    = scan_keys("metricade_sess:*",      url, token, log)
    feature_keys = scan_keys("metricade_features:*",  url, token, log)

    # Extract unique org IDs
    def extract_org(keys, prefix):
        orgs = set()
        for k in keys:
            parts = k.split(":")
            if len(parts) >= 2:
                orgs.add(parts[1])
        return orgs

    stream_orgs  = extract_org(stream_keys,  "metricade_stream")
    sess_orgs    = extract_org(sess_keys,    "metricade_sess")
    feature_orgs = extract_org(feature_keys, "metricade_features")
    all_orgs     = sorted(stream_orgs | sess_orgs | feature_orgs)

    log.info(f"")
    log.info(f"{'Org ID':<30} {'BOUNTY RUNE':>14} {'OBSERVER WARD':>15} {'AEGIS':>8}")
    log.info(f"{'─'*30} {'─'*14} {'─'*15} {'─'*8}")

    # Count per org
    sess_by_org    = defaultdict(int)
    feature_by_org = defaultdict(int)
    for k in sess_keys:
        parts = k.split(":")
        if len(parts) >= 2:
            sess_by_org[parts[1]] += 1
    for k in feature_keys:
        parts = k.split(":")
        if len(parts) >= 2:
            feature_by_org[parts[1]] += 1

    for org in all_orgs:
        br_count = xlen(f"metricade_stream:{org}", url, token)
        ow_count = sess_by_org.get(org, 0)
        ae_count = feature_by_org.get(org, 0)
        log.info(f"{org:<30} {br_count:>14,} {ow_count:>15,} {ae_count:>8,}")

    log.info(f"")
    log.info(f"Total orgs found: {len(all_orgs)}")
    return all_orgs


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — LOAD AEGIS TENSORS
# ══════════════════════════════════════════════════════════════════════════════
def load_aegis(org_id: str, url: str, token: str,
               log: logging.Logger) -> tuple[np.ndarray, list[str]]:
    log.info("─" * 70)
    log.info(f"STEP 2/5 — LOADING AEGIS TENSORS  (org={org_id})")

    keys = scan_keys(f"metricade_features:{org_id}:*", url, token, log)
    log.info(f"  AEGIS keys found: {len(keys):,}")

    if CONFIG["MAX_SESSIONS"] and len(keys) > CONFIG["MAX_SESSIONS"]:
        import random; random.seed(42)
        keys = random.sample(keys, CONFIG["MAX_SESSIONS"])
        log.info(f"  Capped to MAX_SESSIONS={CONFIG['MAX_SESSIONS']:,}")

    raw_map = fetch_parallel(keys, url, token, log)

    tensors    = []
    session_ids = []
    skipped    = 0

    for redis_key, raw in raw_map.items():
        sid = redis_key.split(":")[-1]
        if raw is None:
            skipped += 1
            log.debug(f"  SKIP {sid[:8]} — None from Redis")
            continue
        try:
            # Decode base64 → npz → cont tensor
            if isinstance(raw, str):
                npz_bytes = base64.b64decode(raw)
            else:
                npz_bytes = base64.b64decode(raw.encode())
            buf  = io.BytesIO(npz_bytes)
            data = np.load(buf, allow_pickle=False)
            cont = data["cont"].astype(np.float32)  # [256, 40]
            assert cont.shape == (SEQ_LEN, N_CONT), f"Shape mismatch: {cont.shape}"
            tensors.append(cont)
            session_ids.append(sid)
        except Exception as e:
            skipped += 1
            log.debug(f"  SKIP {sid[:8]} — {e}")

    log.info(f"  Loaded:  {len(tensors):,} AEGIS tensors")
    log.info(f"  Skipped: {skipped:,}")

    if not tensors:
        log.error("No AEGIS tensors loaded — aborting")
        sys.exit(1)

    X = np.stack(tensors)  # [N, 256, 40]
    log.info(f"  Matrix shape: {X.shape}  (sessions × seq_len × features)")

    # Quick stats
    log.info(f"  Value range: min={X.min():.4f}  max={X.max():.4f}  "
             f"mean={X.mean():.4f}  std={X.std():.4f}")

    # Check for NaN/Inf
    nan_count = np.isnan(X).sum()
    inf_count = np.isinf(X).sum()
    if nan_count > 0 or inf_count > 0:
        log.warning(f"  NaN={nan_count}  Inf={inf_count} — replacing with 0")
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    return X, session_ids


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — SEQUENCE AUTOENCODER
# ══════════════════════════════════════════════════════════════════════════════
class SequenceAutoencoder(nn.Module):
    """
    Encodes [256, 40] → bottleneck → reconstructs [256, 40].

    Architecture:
      Encoder: LSTM(input=40, hidden=64, layers=2, batch_first=True)
               → final hidden state [B, 64] → Linear(64→bottleneck)
               LSTM reads 256 tokens in order — final hidden state captures
               HOW the session evolved, not just average values.

      Decoder: Linear(bottleneck→64) → ReLU
               → broadcast to seq_len → LSTM(64, hidden=64, layers=2)
               → Linear(64→40) per timestep

    No labels. No assumptions. Pure reconstruction.
    """
    def __init__(self, seq_len=256, n_features=40, bottleneck=32):
        super().__init__()
        self.seq_len    = seq_len
        self.n_features = n_features
        self.bottleneck = bottleneck
        lstm_hidden     = 64
        lstm_layers     = 2

        # Encoder LSTM — reads sequence, final hidden → bottleneck
        self.enc_lstm   = nn.LSTM(n_features, lstm_hidden,
                                  num_layers=lstm_layers,
                                  batch_first=True, dropout=0.1)
        self.enc_bottle = nn.Linear(lstm_hidden, bottleneck)

        # Decoder — broadcast bottleneck back to sequence then reconstruct
        self.dec_expand = nn.Sequential(
            nn.Linear(bottleneck, lstm_hidden), nn.ReLU(),
        )
        self.dec_lstm   = nn.LSTM(lstm_hidden, lstm_hidden,
                                  num_layers=lstm_layers,
                                  batch_first=True, dropout=0.1)
        self.dec_out    = nn.Linear(lstm_hidden, n_features)

    def encode(self, x: torch.Tensor) -> torch.Tensor:
        # x: [B, 256, 40]
        _, (h_n, _) = self.enc_lstm(x)   # h_n: [layers, B, hidden]
        h = h_n[-1]                       # [B, hidden] — last layer final state
        z = self.enc_bottle(h)            # [B, bottleneck]
        return z

    def decode(self, z: torch.Tensor) -> torch.Tensor:
        # z: [B, bottleneck]
        h = self.dec_expand(z)                              # [B, hidden]
        h = h.unsqueeze(1).expand(-1, self.seq_len, -1)     # [B, 256, hidden]
        out_seq, _ = self.dec_lstm(h)                       # [B, 256, hidden]
        out = self.dec_out(out_seq)                         # [B, 256, 40]
        return out

    def forward(self, x: torch.Tensor):
        z   = self.encode(x)
        out = self.decode(z)
        return out, z


def train_autoencoder(X: np.ndarray, org_id: str, out_dir: Path,
                      log: logging.Logger) -> np.ndarray:
    log.info("─" * 70)
    log.info("STEP 3/5 — SEQUENCE AUTOENCODER TRAINING")
    log.info(f"  Input shape     : {X.shape}")
    log.info(f"  Bottleneck dim  : {CONFIG['BOTTLENECK_DIM']}")
    log.info(f"  Epochs          : {CONFIG['EPOCHS']}")
    log.info(f"  Batch size      : {CONFIG['BATCH_SIZE']}")
    log.info(f"  Learning rate   : {CONFIG['LEARNING_RATE']}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log.info(f"  Device          : {device}")

    X_tensor = torch.from_numpy(X)
    dataset  = TensorDataset(X_tensor)
    loader   = DataLoader(dataset, batch_size=CONFIG["BATCH_SIZE"],
                          shuffle=True, drop_last=False)

    model     = SequenceAutoencoder(SEQ_LEN, N_CONT, CONFIG["BOTTLENECK_DIM"]).to(device)
    optimizer = optim.Adam(model.parameters(), lr=CONFIG["LEARNING_RATE"])
    criterion = nn.MSELoss()

    n_params = sum(p.numel() for p in model.parameters())
    log.info(f"  Model params    : {n_params:,}")
    log.info(f"  Steps per epoch : {len(loader)}")
    log.info("")

    train_losses = []
    t0 = time.time()

    for epoch in range(1, CONFIG["EPOCHS"] + 1):
        model.train()
        epoch_loss = 0.0
        for (batch,) in loader:
            batch = batch.to(device)
            optimizer.zero_grad()
            recon, _ = model(batch)
            loss = criterion(recon, batch)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()

        avg_loss = epoch_loss / len(loader)
        train_losses.append(avg_loss)

        if epoch % 5 == 0 or epoch == 1 or epoch == CONFIG["EPOCHS"]:
            elapsed = time.time() - t0
            eta = (elapsed / epoch) * (CONFIG["EPOCHS"] - epoch)
            log.info(f"  Epoch {epoch:>3}/{CONFIG['EPOCHS']}  "
                     f"loss={avg_loss:.6f}  "
                     f"elapsed={elapsed:.1f}s  ETA={eta:.1f}s")

    total_time = time.time() - t0
    log.info(f"")
    log.info(f"  Training complete in {total_time:.1f}s")
    log.info(f"  Final loss: {train_losses[-1]:.6f}")
    log.info(f"  Loss drop : {train_losses[0]:.6f} → {train_losses[-1]:.6f} "
             f"({100*(1 - train_losses[-1]/train_losses[0]):.1f}% reduction)")

    # Save loss curve
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(range(1, len(train_losses)+1), train_losses, color="#4c78a8", linewidth=2)
    ax.set_xlabel("Epoch"); ax.set_ylabel("MSE Loss")
    ax.set_title(f"Autoencoder Training Loss — {org_id}")
    ax.grid(alpha=0.3)
    loss_path = out_dir / f"loss_curve_{org_id}.png"
    plt.tight_layout(); plt.savefig(loss_path, dpi=150); plt.close()
    log.info(f"  Loss curve saved: {loss_path}")

    # Extract embeddings
    log.info("  Extracting bottleneck embeddings for all sessions...")
    model.eval()
    all_embeddings = []
    with torch.no_grad():
        for i in range(0, len(X), CONFIG["BATCH_SIZE"]):
            batch = torch.from_numpy(X[i:i+CONFIG["BATCH_SIZE"]]).to(device)
            z = model.encode(batch)
            all_embeddings.append(z.cpu().numpy())

    embeddings = np.vstack(all_embeddings)
    log.info(f"  Embeddings shape: {embeddings.shape}")
    log.info(f"  Embedding range : min={embeddings.min():.4f}  max={embeddings.max():.4f}")

    # Save embeddings
    emb_path = out_dir / f"embeddings_{org_id}.npy"
    np.save(emb_path, embeddings)
    log.info(f"  Embeddings saved: {emb_path}")

    return embeddings


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — UMAP + HDBSCAN
# ══════════════════════════════════════════════════════════════════════════════
def run_hdbscan(embeddings: np.ndarray, session_ids: list[str],
                org_id: str, out_dir: Path, log: logging.Logger) -> np.ndarray:
    log.info("─" * 70)
    log.info("STEP 4/5 — UMAP + HDBSCAN CLUSTERING")
    log.info(f"  Input shape        : {embeddings.shape}")
    log.info(f"  HDBSCAN_MIN_SIZE   : {CONFIG['HDBSCAN_MIN_SIZE']}")
    log.info(f"  HDBSCAN_MIN_SAMPLES: {CONFIG['HDBSCAN_MIN_SAMPLES']}")

    # UMAP for visualisation (2D) and pre-clustering (10D)
    import umap as umap_lib
    import hdbscan as hdbscan_lib

    log.info("  Running UMAP 10D for clustering input...")
    t0 = time.time()
    reducer_nd = umap_lib.UMAP(n_components=10,
                                n_neighbors=CONFIG["UMAP_N_NEIGHBORS"],
                                min_dist=CONFIG["UMAP_MIN_DIST"],
                                metric="euclidean", random_state=42, verbose=False)
    X_10d = reducer_nd.fit_transform(embeddings)
    log.info(f"  UMAP 10D done in {time.time()-t0:.1f}s  shape={X_10d.shape}")

    log.info("  Running UMAP 2D for visualisation...")
    t0 = time.time()
    reducer_2d = umap_lib.UMAP(n_components=2,
                                n_neighbors=CONFIG["UMAP_N_NEIGHBORS"],
                                min_dist=CONFIG["UMAP_MIN_DIST"],
                                metric="euclidean", random_state=42, verbose=False)
    X_2d = reducer_2d.fit_transform(embeddings)
    log.info(f"  UMAP 2D done in {time.time()-t0:.1f}s")

    log.info("  Running HDBSCAN...")
    t0 = time.time()
    clusterer = hdbscan_lib.HDBSCAN(
        min_cluster_size   = CONFIG["HDBSCAN_MIN_SIZE"],
        min_samples        = CONFIG["HDBSCAN_MIN_SAMPLES"],
        metric             = "euclidean",
        cluster_selection_method = "eom",
    )
    labels      = clusterer.fit_predict(X_10d)
    probs       = clusterer.probabilities_
    outlier_scores = clusterer.outlier_scores_
    log.info(f"  HDBSCAN done in {time.time()-t0:.1f}s")

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise    = (labels == -1).sum()
    log.info(f"")
    log.info(f"  Clusters found : {n_clusters}")
    log.info(f"  Noise sessions : {n_noise:,}  ({100*n_noise/len(labels):.1f}%)")
    log.info(f"")

    # Per-cluster stats
    log.info(f"  {'Cluster':<10} {'Count':>8}  {'Avg membership':>16}  {'Avg outlier':>13}")
    log.info(f"  {'─'*55}")
    for cid in sorted(set(labels)):
        mask  = labels == cid
        tag   = "NOISE" if cid == -1 else f"C{cid}"
        count = int(mask.sum())
        avg_prob  = float(probs[mask].mean())
        avg_out   = float(outlier_scores[mask].mean())
        log.info(f"  {tag:<10} {count:>8,}  {avg_prob:>16.4f}  {avg_out:>13.4f}")

    return labels, probs, outlier_scores, X_2d


# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — SAVE OUTPUTS
# ══════════════════════════════════════════════════════════════════════════════
def save_outputs(session_ids, labels, probs, outlier_scores, X_2d,
                 org_id, out_dir, log):
    log.info("─" * 70)
    log.info("STEP 5/5 — SAVING OUTPUTS")

    # CSV
    csv_path = out_dir / f"clusters_{org_id}.csv"
    with open(csv_path, "w") as f:
        f.write("session_id,cluster_id,membership_prob,outlier_score\n")
        for i, sid in enumerate(session_ids):
            f.write(f"{sid},{int(labels[i])},{float(probs[i]):.4f},"
                    f"{float(outlier_scores[i]):.4f}\n")
    log.info(f"  CSV saved      : {csv_path}")

    # 2D UMAP plot coloured by cluster
    import matplotlib.cm as cm
    n_unique  = len(set(labels))
    cmap      = cm.get_cmap("tab20", n_unique)
    color_map = {cid: cmap(i) for i, cid in enumerate(sorted(set(labels)))}

    fig, ax = plt.subplots(figsize=(12, 8))
    for cid in sorted(set(labels)):
        mask  = labels == cid
        tag   = "NOISE" if cid == -1 else f"C{cid}"
        alpha = 0.25 if cid == -1 else 0.7
        size  = 5    if cid == -1 else 15
        ax.scatter(X_2d[mask, 0], X_2d[mask, 1],
                   color=color_map[cid], s=size, alpha=alpha,
                   label=f"{tag} (n={int(mask.sum()):,})")
    ax.set_title(f"AEGIS Autoencoder Embeddings — {org_id}  "
                 f"(n={len(session_ids):,}  clusters={n_unique-1})",
                 fontsize=12, fontweight="bold")
    ax.set_xlabel("UMAP-1"); ax.set_ylabel("UMAP-2")
    ax.legend(fontsize=8, bbox_to_anchor=(1.02, 1), loc="upper left")
    plt.tight_layout()
    plot_path = out_dir / f"plot_{org_id}.png"
    plt.savefig(plot_path, dpi=150, bbox_inches="tight"); plt.close()
    log.info(f"  Plot saved     : {plot_path}")

    log.info(f"")
    log.info(f"  Output folder  : {out_dir.resolve()}")
    log.info(f"  Files:")
    for p in sorted(out_dir.iterdir()):
        log.info(f"    {p.name}")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
def run_org(org_id: str, url: str, token: str):
    out_dir = OUT_BASE / org_id
    log     = setup_logging(out_dir, org_id)
    t_total = time.time()

    # Step 2: Load AEGIS
    X, session_ids = load_aegis(org_id, url, token, log)

    MIN_FOR_CLUSTERING = 20
    if len(session_ids) < MIN_FOR_CLUSTERING:
        log.warning(f"Only {len(session_ids)} sessions — need at least {MIN_FOR_CLUSTERING} "
                    f"for UMAP+HDBSCAN. Skipping clustering, embeddings saved only.")
        train_autoencoder(X, org_id, out_dir, log)
        log.info("─" * 70)
        log.info(f"SKIPPED clustering — collect more data for org={org_id}")
        log.info("=" * 70)
        return

    if len(session_ids) < CONFIG["HDBSCAN_MIN_SIZE"] * 2:
        log.warning(f"Only {len(session_ids)} sessions — "
                    f"consider lowering HDBSCAN_MIN_SIZE (currently {CONFIG['HDBSCAN_MIN_SIZE']})")

    # Step 3: Autoencoder
    embeddings = train_autoencoder(X, org_id, out_dir, log)

    # Step 4: HDBSCAN
    labels, probs, outlier_scores, X_2d = run_hdbscan(
        embeddings, session_ids, org_id, out_dir, log)

    # Step 5: Save
    save_outputs(session_ids, labels, probs, outlier_scores, X_2d,
                 org_id, out_dir, log)

    log.info("─" * 70)
    log.info(f"COMPLETE  total time: {time.time()-t_total:.1f}s  "
             f"({(time.time()-t_total)/60:.1f} min)")
    log.info("=" * 70)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--org", default=None,
                        help="Specific org to process (omit = all orgs)")
    parser.add_argument("--skip-discovery", action="store_true",
                        help="Skip org discovery step (faster if org is known)")
    args = parser.parse_args()

    # Bootstrap logging for discovery step
    OUT_BASE.mkdir(parents=True, exist_ok=True)
    disc_log = logging.getLogger("discovery")
    disc_log.setLevel(logging.INFO)
    if not disc_log.handlers:
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s",
                                          datefmt="%H:%M:%S"))
        disc_log.addHandler(ch)

    load_env(disc_log)
    url   = os.environ.get("UPSTASH_REDIS_URL", "").rstrip("/")
    token = os.environ.get("UPSTASH_REDIS_TOKEN", "")
    if not url:
        disc_log.error("UPSTASH_REDIS_URL not set"); sys.exit(1)

    if args.org:
        orgs = [args.org]
        if not args.skip_discovery:
            discover_orgs(url, token, disc_log)
    else:
        orgs = discover_orgs(url, token, disc_log)
        if not orgs:
            disc_log.error("No orgs found"); sys.exit(1)
        disc_log.info(f"\nWill process: {orgs}")

    for org_id in orgs:
        run_org(org_id, url, token)


if __name__ == "__main__":
    main()