"""
Offline contrastive training for BehavioralTransformer.

Uses SimCLR with CL4SRec-style augmentations (crop / mask / reorder) on behavioral
event sequences fetched from Upstash Redis feature keys.

Usage:
    python scripts/train.py --org <org_id> --epochs 50
    python scripts/train.py                          # all orgs
    python scripts/train.py --dry-run --org <org_id> # inspect dataset shapes, no training

Run from repo root. Credentials are read from .env at the repo root.
"""

import argparse
import base64
import io
import math
import os
import random
import subprocess
import sys
import time
from pathlib import Path

import httpx
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import DataLoader, Dataset
from tqdm import tqdm

# ── Paths ─────────────────────────────────────────────────────────────────────

REPO_ROOT    = Path(__file__).resolve().parent.parent
SCRIPTS_DIR  = Path(__file__).resolve().parent
MODELS_DIR   = REPO_ROOT / "packages" / "model-worker" / "models"
LOCAL_OUTPUT = SCRIPTS_DIR / "output" / "training"   # local copies of weights + logs

# Make BehavioralTransformer importable by adding the model-worker package root
sys.path.insert(0, str(REPO_ROOT / "packages" / "model-worker"))

from src.inference.transformer import BehavioralTransformer  # noqa: E402

# ── .env loading ──────────────────────────────────────────────────────────────

_env_path = REPO_ROOT / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


# ── Redis pipeline helper ──────────────────────────────────────────────────────

def _redis_pipeline(cmds: list, url: str, token: str) -> list:
    r = httpx.post(
        url.rstrip("/") + "/pipeline",
        headers={"Authorization": f"Bearer {token}"},
        json=cmds,
        timeout=30,
    )
    r.raise_for_status()
    return [item["result"] for item in r.json()]


# ── Dataset ───────────────────────────────────────────────────────────────────

class MetricadeSessionDataset(Dataset):
    """
    Loads all feature tensors for one org from Redis.
    Each item is a (cont [256, 40] float32, cat [8] int64) tuple.
    """

    def __init__(self, org_id: str, redis_url: str, redis_token: str, min_sessions: int = 200):
        self.sessions: list[tuple[torch.Tensor, torch.Tensor]] = []
        pattern = f"metricade_features:{org_id}:*"

        # Cursor-based SCAN to collect all matching keys
        keys: list[str] = []
        cursor = "0"
        print(f"Scanning keys for {org_id}...")
        while True:
            result = _redis_pipeline(
                [["SCAN", cursor, "MATCH", pattern, "COUNT", "500"]],
                redis_url,
                redis_token,
            )[0]
            cursor = result[0]
            keys.extend(result[1])
            if cursor == "0":
                break

        if not keys:
            raise ValueError(
                f"No feature keys found for org '{org_id}' (pattern: {pattern}). "
                "Run the pipeline first to accumulate sessions."
            )

        # Fetch values in batches of 50 via pipeline GET
        pbar = tqdm(total=len(keys), desc="Loading sessions", unit="session")
        batch_size = 50
        for i in range(0, len(keys), batch_size):
            batch_keys = keys[i : i + batch_size]
            cmds = [["GET", k] for k in batch_keys]
            results = _redis_pipeline(cmds, redis_url, redis_token)

            for raw in results:
                if raw is None:
                    pbar.update(1)
                    continue
                try:
                    blob = base64.b64decode(raw)
                    buf = io.BytesIO(blob)
                    npz = np.load(buf, allow_pickle=False)
                    cont = torch.from_numpy(npz["cont"].astype(np.float32))  # [256, 40]
                    cat  = torch.from_numpy(npz["cat"].astype(np.int64))     # [8]
                    self.sessions.append((cont, cat))
                except Exception:
                    pass
                pbar.update(1)

        pbar.close()

        if len(self.sessions) < min_sessions:
            raise ValueError(
                f"Only {len(self.sessions)} sessions loaded for org '{org_id}', "
                f"need at least {min_sessions}. Collect more data before training."
            )

        print(f"Loaded {len(self.sessions):,} sessions for {org_id}.")

    def __len__(self) -> int:
        return len(self.sessions)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        return self.sessions[idx]


# ── Augmentations (CL4SRec style) ─────────────────────────────────────────────

def _real_len(cont: torch.Tensor) -> int:
    """Return index of last non-zero row + 1. Returns 0 if all rows are zero."""
    nonzero_rows = (cont.abs().sum(dim=-1) != 0).nonzero(as_tuple=False)
    if len(nonzero_rows) == 0:
        return 0
    return int(nonzero_rows[-1].item()) + 1


def aug_crop(cont: torch.Tensor, ratio: float = 0.7) -> torch.Tensor:
    """Keep a random contiguous subsequence of length real_len * ratio."""
    real_len = _real_len(cont)
    if real_len == 0:
        return cont
    crop_len = max(1, int(real_len * ratio))
    start = random.randint(0, real_len - crop_len)
    result = torch.zeros_like(cont)
    result[:crop_len] = cont[start : start + crop_len]
    return result


def aug_mask(cont: torch.Tensor, ratio: float = 0.2) -> torch.Tensor:
    """Zero out a random subset of event rows."""
    real_len = _real_len(cont)
    if real_len == 0:
        return cont
    n_mask = max(1, int(real_len * ratio))
    indices = random.sample(range(real_len), k=min(n_mask, real_len))
    result = cont.clone()
    result[indices] = 0.0
    return result


def aug_reorder(cont: torch.Tensor, ratio: float = 0.2) -> torch.Tensor:
    """Shuffle a random contiguous window of event rows."""
    real_len = _real_len(cont)
    if real_len == 0:
        return cont
    window_len = max(2, int(real_len * ratio))
    if window_len > real_len:
        window_len = real_len
    start = random.randint(0, real_len - window_len)
    result = cont.clone()
    perm = torch.randperm(window_len)
    result[start : start + window_len] = cont[start : start + window_len][perm]
    return result


def augment(
    cont: torch.Tensor,
    crop_ratio: float,
    mask_ratio: float,
    reorder_ratio: float,
) -> torch.Tensor:
    """Apply two randomly sampled augmentations sequentially."""
    aug_fns = [
        (aug_crop,    crop_ratio),
        (aug_mask,    mask_ratio),
        (aug_reorder, reorder_ratio),
    ]
    # Uniform weights — sample 2 with replacement
    chosen = random.choices(aug_fns, k=2)
    for fn, ratio in chosen:
        cont = fn(cont, ratio)
    return cont


# ── SimCLR Collator ────────────────────────────────────────────────────────────

class SimCLRCollator(Dataset):
    """
    Wraps MetricadeSessionDataset to produce two augmented views per session.
    Returns (va_cont, cat, vb_cont, cat) — cat is not augmented.
    """

    def __init__(
        self,
        dataset: MetricadeSessionDataset,
        crop_ratio: float,
        mask_ratio: float,
        reorder_ratio: float,
    ):
        self.dataset = dataset
        self.crop_ratio = crop_ratio
        self.mask_ratio = mask_ratio
        self.reorder_ratio = reorder_ratio

    def __len__(self) -> int:
        return len(self.dataset)

    def __getitem__(self, idx: int):
        cont, cat = self.dataset[idx]
        va = augment(cont, self.crop_ratio, self.mask_ratio, self.reorder_ratio)
        vb = augment(cont, self.crop_ratio, self.mask_ratio, self.reorder_ratio)
        return va, cat, vb, cat


# ── Projection head ────────────────────────────────────────────────────────────

class ProjectionHead(nn.Module):
    """
    MLP projection head used during contrastive training only.
    Maps 192-dim encoder output → 64-dim space for NT-Xent loss.
    Not saved with the final model weights.
    """

    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(192, 128),
            nn.BatchNorm1d(128),
            nn.ReLU(inplace=True),
            nn.Linear(128, 64),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


# ── NT-Xent loss ───────────────────────────────────────────────────────────────

class NTXentLoss(nn.Module):
    """
    Normalized Temperature-scaled Cross Entropy loss (SimCLR).
    Each sample's positive pair is its augmented twin; all others are negatives.
    """

    def __init__(self, temperature: float = 0.07):
        super().__init__()
        self.temperature = temperature

    def forward(
        self, z_a: torch.Tensor, z_b: torch.Tensor
    ) -> tuple[torch.Tensor, float, float]:
        """
        z_a, z_b: [N, 64]
        Returns: (loss, mean_pos_sim, mean_neg_sim)
        """
        n = z_a.shape[0]

        z_a = F.normalize(z_a, dim=-1)
        z_b = F.normalize(z_b, dim=-1)

        z = torch.cat([z_a, z_b], dim=0)          # [2N, 64]

        # Raw cosine similarities (before temperature scaling) for logging
        sim_raw = z @ z.T                           # [2N, 2N]

        # Positive pairs: (i, i+N) and (i+N, i)
        pos_sim = torch.cat([
            sim_raw[:n, n:].diagonal(),
            sim_raw[n:, :n].diagonal(),
        ]).mean().item()

        # Negative similarities: average over off-diagonal, off-positive elements
        mask_diag = torch.eye(2 * n, dtype=torch.bool, device=z.device)
        mask_pos  = torch.zeros(2 * n, 2 * n, dtype=torch.bool, device=z.device)
        mask_pos[:n, n:] = torch.eye(n, dtype=torch.bool, device=z.device)
        mask_pos[n:, :n] = torch.eye(n, dtype=torch.bool, device=z.device)
        mask_neg = ~(mask_diag | mask_pos)
        neg_sim = sim_raw[mask_neg].mean().item()

        # Temperature-scaled logits
        logits = sim_raw / self.temperature
        logits[mask_diag] = float("-inf")          # mask self-similarity

        # Labels: for row i in [0,N) → positive at i+N; for row i in [N,2N) → i-N
        labels = torch.cat([
            torch.arange(n, 2 * n, device=z.device),
            torch.arange(0, n, device=z.device),
        ])

        loss = F.cross_entropy(logits, labels)
        return loss, pos_sim, neg_sim


# ── Validation ─────────────────────────────────────────────────────────────────

def validate(
    transformer: BehavioralTransformer,
    org_id: str,
    dataset: MetricadeSessionDataset,
    device: torch.device,
) -> None:
    """
    Run K-Means on all encoded sessions and report silhouette score.
    Compares against bootstrap (random) weights if bootstrap_random.pt exists.
    """
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    from sklearn.metrics.pairwise import cosine_distances

    def _encode_all(model: BehavioralTransformer) -> np.ndarray:
        model.eval()
        model.to(device)
        all_vecs = []
        loader = DataLoader(dataset, batch_size=256, shuffle=False, num_workers=0)
        with torch.no_grad():
            for cont, cat in loader:
                cont = cont.to(device)
                cat  = cat.to(device)
                vecs = model(cont, cat)                # [B, 192]
                all_vecs.append(vecs.cpu().numpy())
        return np.concatenate(all_vecs, axis=0)

    def _cluster_score(vecs: np.ndarray) -> tuple[float, float]:
        km = KMeans(n_clusters=3, random_state=42, n_init=10)
        labels = km.fit_predict(vecs)
        sil = silhouette_score(vecs, labels, metric="cosine")

        centroids = km.cluster_centers_
        # Inter-cluster: mean cosine distance between all centroid pairs
        inter_dists = []
        for i in range(3):
            for j in range(i + 1, 3):
                d = cosine_distances([centroids[i]], [centroids[j]])[0][0]
                inter_dists.append(d)
        mean_inter = float(np.mean(inter_dists))

        # Intra-cluster: mean cosine distance from each point to its centroid
        intra_dists = []
        for c in range(3):
            mask = labels == c
            if mask.sum() > 0:
                d = cosine_distances(vecs[mask], [centroids[c]])
                intra_dists.extend(d.flatten().tolist())
        mean_intra = float(np.mean(intra_dists)) if intra_dists else 0.0

        net_sep = mean_inter - mean_intra
        return float(sil), net_sep

    print("\n  Running post-training validation...")
    trained_vecs = _encode_all(transformer)
    trained_sil, trained_sep = _cluster_score(trained_vecs)

    bootstrap_path = MODELS_DIR / "bootstrap_random.pt"
    has_bootstrap = bootstrap_path.exists()

    if has_bootstrap:
        bootstrap_model = BehavioralTransformer()
        bootstrap_model.load_state_dict(
            torch.load(bootstrap_path, map_location="cpu", weights_only=True)
        )
        bootstrap_vecs = _encode_all(bootstrap_model)
        boot_sil, boot_sep = _cluster_score(bootstrap_vecs)
    else:
        boot_sil, boot_sep = None, None

    n = len(trained_vecs)
    print(f"\n  Post-Training Validation ({n:,} sessions)")
    print("  " + "=" * 46)
    print(f"  {'Metric':<28} {'Trained':>8}  {'Bootstrap':>9}")
    print("  " + "-" * 46)
    boot_sil_str  = f"{boot_sil:.3f}"  if boot_sil  is not None else "  (n/a)"
    boot_sep_str  = f"{boot_sep:.3f}"  if boot_sep  is not None else "  (n/a)"
    print(f"  {'Silhouette score (cosine)':<28} {trained_sil:>8.3f}  {boot_sil_str:>9}")
    print(f"  {'Net separation':<28} {trained_sep:>8.3f}  {boot_sep_str:>9}")
    if has_bootstrap:
        sil_delta = trained_sil - boot_sil
        sep_delta = trained_sep - boot_sep
        print(f"  {'Delta (trained - bootstrap)':<28} {sil_delta:>+8.3f}  {sep_delta:>+9.3f}")
    print("  " + "=" * 46)

    if trained_sil > 0.3:
        print("  Silhouette looks healthy (>0.30).")
    elif trained_sil > 0.1:
        print("  Silhouette is modest (0.10–0.30) — more data or longer training may help.")
    else:
        print("  Silhouette is low (<0.10) — embeddings not well separated yet.")


# ── Discover orgs ──────────────────────────────────────────────────────────────

def discover_orgs(redis_url: str, redis_token: str) -> list[str]:
    """SCAN metricade_features:* and return unique org_ids sorted."""
    keys: list[str] = []
    cursor = "0"
    while True:
        result = _redis_pipeline(
            [["SCAN", cursor, "MATCH", "metricade_features:*", "COUNT", "500"]],
            redis_url,
            redis_token,
        )[0]
        cursor = result[0]
        keys.extend(result[1])
        if cursor == "0":
            break

    org_ids: set[str] = set()
    for key in keys:
        # key format: metricade_features:{org_id}:{session_id}
        parts = key.split(":", 2)
        if len(parts) == 3:
            org_ids.add(parts[1])

    return sorted(org_ids)


# ── Training loop ──────────────────────────────────────────────────────────────

def train_org(
    org_id: str,
    args: argparse.Namespace,
    redis_url: str,
    redis_token: str,
) -> BehavioralTransformer:

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_OUTPUT.mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"  Device: {device}")

    # Dataset and collator
    dataset  = MetricadeSessionDataset(org_id, redis_url, redis_token, args.min_sessions)
    collator = SimCLRCollator(dataset, args.crop_ratio, args.mask_ratio, args.reorder_ratio)
    loader   = DataLoader(
        collator,
        batch_size=256,
        shuffle=True,
        drop_last=True,
        num_workers=0,
    )

    steps_per_epoch = len(loader)
    if steps_per_epoch == 0:
        raise ValueError(
            f"Dataset has fewer than 256 sessions — not enough for one full batch."
        )

    # Models
    transformer = BehavioralTransformer().to(device)
    head        = ProjectionHead().to(device)
    criterion   = NTXentLoss(temperature=args.temperature)

    # Optionally resume from checkpoint
    checkpoint_path = MODELS_DIR / f"{org_id}_checkpoint.pt"
    start_epoch = 0
    best_loss   = math.inf

    if args.resume and checkpoint_path.exists():
        ckpt = torch.load(checkpoint_path, map_location=device, weights_only=False)
        transformer.load_state_dict(ckpt["model"])
        head.load_state_dict(ckpt["head"])
        start_epoch = ckpt.get("epoch", 0)
        best_loss   = ckpt.get("best_loss", math.inf)
        print(f"  Resuming from epoch {start_epoch}/{100} (loss: {best_loss:.3f})")

    optimizer = AdamW(
        list(transformer.parameters()) + list(head.parameters()),
        lr=args.lr,
        weight_decay=1e-4,
    )
    scheduler = CosineAnnealingLR(optimizer, T_max=100 * steps_per_epoch)

    if args.resume and checkpoint_path.exists():
        ckpt = torch.load(checkpoint_path, map_location=device, weights_only=False)
        optimizer.load_state_dict(ckpt["optimizer"])
        scheduler.load_state_dict(ckpt["scheduler"])

    use_cuda = device.type == "cuda"

    for epoch in range(start_epoch, 100):
        transformer.train()
        head.train()

        epoch_losses: list[float] = []
        t_epoch_start = time.time()

        for step, (va_cont, cat, vb_cont, _) in enumerate(loader):
            t_step_start = time.time()

            va_cont = va_cont.to(device)
            vb_cont = vb_cont.to(device)
            cat     = cat.to(device)

            if use_cuda:
                with torch.autocast("cuda"):
                    z_a = head(transformer(va_cont, cat))
                    z_b = head(transformer(vb_cont, cat))
                    loss, pos_sim, neg_sim = criterion(z_a, z_b)
            else:
                z_a = head(transformer(va_cont, cat))
                z_b = head(transformer(vb_cont, cat))
                loss, pos_sim, neg_sim = criterion(z_a, z_b)

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(
                list(transformer.parameters()) + list(head.parameters()), max_norm=1.0
            )
            optimizer.step()
            scheduler.step()

            epoch_losses.append(loss.item())

            # ETA estimate based on step timing
            elapsed = time.time() - t_epoch_start
            steps_done = step + 1
            steps_remaining = (100 - epoch - 1) * steps_per_epoch + (steps_per_epoch - steps_done)
            time_per_step = elapsed / steps_done
            eta_s = int(steps_remaining * time_per_step)
            eta_str = f"{eta_s // 60}m {eta_s % 60}s"

            print(
                f"\r  Epoch {epoch + 1}/{100} | "
                f"Step {steps_done}/{steps_per_epoch} | "
                f"Loss: {loss.item():.3f} | "
                f"Pos: {pos_sim:.2f} | "
                f"Neg: {neg_sim:.2f} | "
                f"ETA: {eta_str}",
                end="",
                flush=True,
            )

        epoch_loss = float(np.mean(epoch_losses))
        print(
            f"\r  Epoch {epoch + 1}/{100} complete | "
            f"Avg loss: {epoch_loss:.3f} | "
            f"Steps: {steps_per_epoch}"
        )

        if epoch_loss < best_loss:
            best_loss = epoch_loss

            # Save production weights (transformer only)
            model_path = MODELS_DIR / f"{org_id}.pt"
            torch.save(transformer.state_dict(), model_path)

            # Save local copy in scripts/output/training/
            local_model_path = LOCAL_OUTPUT / f"{org_id}.pt"
            torch.save(transformer.state_dict(), local_model_path)

            # Save full checkpoint for resuming
            torch.save(
                {
                    "epoch":      epoch + 1,
                    "model":      transformer.state_dict(),
                    "head":       head.state_dict(),
                    "optimizer":  optimizer.state_dict(),
                    "scheduler":  scheduler.state_dict(),
                    "best_loss":  best_loss,
                },
                checkpoint_path,
            )
            print(
                f"  New best model saved (loss: {best_loss:.3f})\n"
                f"    → {model_path}\n"
                f"    → {local_model_path}"
            )

    return transformer


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Contrastive training for BehavioralTransformer.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--org",           type=str,   default=None,  help="Specific org_id to train (omit for all orgs)")
    p.add_argument("--lr",            type=float, default=3e-4,  help="Peak learning rate (AdamW)")
    p.add_argument("--temperature",   type=float, default=0.07,  help="NT-Xent temperature")
    p.add_argument("--min-sessions",  type=int,   default=200,   help="Minimum sessions required to train")
    p.add_argument("--crop-ratio",    type=float, default=0.7,   help="Fraction of sequence kept by crop augmentation")
    p.add_argument("--mask-ratio",    type=float, default=0.2,   help="Fraction of events zeroed by mask augmentation")
    p.add_argument("--reorder-ratio", type=float, default=0.2,   help="Fraction of sequence shuffled by reorder augmentation")
    p.add_argument("--resume",        action="store_true",       help="Resume from checkpoint if available")
    p.add_argument("--dry-run",       action="store_true",       help="Load dataset and print shapes, then exit")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    redis_url   = os.environ.get("UPSTASH_REDIS_URL", "").rstrip("/")
    redis_token = os.environ.get("UPSTASH_REDIS_TOKEN", "")

    if not redis_url:
        print("ERROR: UPSTASH_REDIS_URL is not set. Add it to .env or export it.")
        sys.exit(1)
    if not redis_token:
        print("ERROR: UPSTASH_REDIS_TOKEN is not set. Add it to .env or export it.")
        sys.exit(1)

    # ── Dry run ───────────────────────────────────────────────────────────────
    if args.dry_run:
        org = args.org
        if not org:
            orgs = discover_orgs(redis_url, redis_token)
            if not orgs:
                print("No orgs found in Redis.")
                sys.exit(1)
            org = orgs[0]
            print(f"Dry run: using first discovered org '{org}'")

        dataset = MetricadeSessionDataset(org, redis_url, redis_token, min_sessions=1)
        cont, cat = dataset[0]
        print(f"\nDataset size : {len(dataset):,} sessions")
        print(f"cont shape   : {list(cont.shape)}  (dtype: {cont.dtype})")
        print(f"cat shape    : {list(cat.shape)}   (dtype: {cat.dtype})")
        print(f"cont min/max : {cont.min().item():.4f} / {cont.max().item():.4f}")
        print(f"cat values   : {cat.tolist()}")
        return

    # ── Org list ──────────────────────────────────────────────────────────────
    if args.org:
        orgs = [args.org]
    else:
        orgs = discover_orgs(redis_url, redis_token)
        if not orgs:
            print("No feature keys found in Redis. Run the pipeline first.")
            sys.exit(1)
        print(f"Discovered {len(orgs)} org(s): {', '.join(orgs)}")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    for org_id in orgs:
        print(f"\n{'=' * 60}")
        print(f"  Training org: {org_id}")
        print(f"{'=' * 60}")

        try:
            transformer = train_org(org_id, args, redis_url, redis_token)
        except ValueError as exc:
            print(f"  Skipping {org_id}: {exc}")
            continue

        # Load dataset again for validation (no augmentation)
        try:
            dataset = MetricadeSessionDataset(
                org_id, redis_url, redis_token, min_sessions=1
            )
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            validate(transformer, org_id, dataset, device)
        except Exception as exc:
            print(f"  Validation failed: {exc}")

        # Offer to deploy
        print(f"\nDeploy new weights to Fly.io for {org_id}? (y/n): ", end="", flush=True)
        try:
            answer = input().strip().lower()
        except EOFError:
            answer = "n"

        if answer == "y":
            worker_dir = REPO_ROOT / "packages" / "model-worker"
            print(f"  Running: fly deploy --app metricade-model-worker (cwd: {worker_dir})")
            result = subprocess.run(
                ["fly", "deploy", "--app", "metricade-model-worker"],
                cwd=str(worker_dir),
            )
            if result.returncode != 0:
                print(f"  fly deploy exited with code {result.returncode}.")
            else:
                print("  Deployment complete.")
        else:
            print(
                f"  Skipping deploy. Weights saved at:\n"
                f"    {MODELS_DIR / (org_id + '.pt')}"
            )

    print("\nDone.")


if __name__ == "__main__":
    main()
