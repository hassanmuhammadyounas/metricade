"""
Offline clustering analysis using freshly re-encoded vectors from local weights.

This script:
1) loads env vars from beta/.env if present, else from repo .env
2) fetches feature tensors from Redis (metricade_features:{org_id}:*)
3) encodes vectors locally with BehavioralTransformer + provided weights
4) fetches session metadata from Upstash Vector (ip_country) for annotations
5) sweeps K=2..8, picks best K by silhouette score
6) saves umap_clusters.png, vectors, assignments, metrics to scripts/output/cluster_v2
"""

import argparse
import base64
import csv
import io
import json
import os
import subprocess
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

# ── Auto-install dependencies ─────────────────────────────────────────────────
def _check_and_install(packages: list[tuple[str, str]]) -> None:
    for pkg, import_name in packages:
        try:
            __import__(import_name)
        except ImportError:
            print(f"  Installing {pkg}...")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", pkg, "-q"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

print("Checking dependencies...")
_check_and_install([
    ("torch",        "torch"),
    ("numpy",        "numpy"),
    ("scikit-learn", "sklearn"),
    ("umap-learn",   "umap"),
    ("matplotlib",   "matplotlib"),
    ("httpx",        "httpx"),
])
print("All dependencies satisfied.\n")

import httpx
import numpy as np
import torch
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.metrics.pairwise import cosine_distances


REPO_ROOT   = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
OUTPUT_DIR  = SCRIPTS_DIR / "output" / "cluster_v2"


def _load_env_candidates() -> Path | None:
    candidates = [REPO_ROOT / "beta" / ".env", REPO_ROOT / ".env"]
    for env_path in candidates:
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())
        return env_path
    return None


def _redis_pipeline(cmds: list, url: str, token: str) -> list:
    r = httpx.post(
        url.rstrip("/") + "/pipeline",
        headers={"Authorization": f"Bearer {token}"},
        json=cmds,
        timeout=60,
    )
    r.raise_for_status()
    return [item["result"] for item in r.json()]


def _scan_feature_keys(redis_url: str, redis_token: str, org_id: str) -> list[str]:
    pattern = f"metricade_features:{org_id}:*"
    keys: list[str] = []
    cursor = "0"
    while True:
        result = _redis_pipeline(
            [["SCAN", cursor, "MATCH", pattern, "COUNT", "1000"]],
            redis_url,
            redis_token,
        )[0]
        cursor = result[0]
        keys.extend(result[1])
        if cursor == "0":
            break
    return keys


def _load_sessions(
    redis_url: str, redis_token: str, keys: list[str]
) -> tuple[list[str], list[np.ndarray], list[np.ndarray]]:
    session_ids: list[str] = []
    cont_list: list[np.ndarray] = []
    cat_list: list[np.ndarray] = []

    batch_size = 100
    total = len(keys)
    for i in range(0, total, batch_size):
        batch_keys = keys[i : i + batch_size]
        cmds = [["GET", k] for k in batch_keys]
        results = _redis_pipeline(cmds, redis_url, redis_token)

        for key, raw in zip(batch_keys, results):
            if raw is None:
                continue
            try:
                blob = base64.b64decode(raw)
                npz = np.load(io.BytesIO(blob), allow_pickle=False)
                cont = npz["cont"].astype(np.float32)  # [256, 40]
                cat  = npz["cat"].astype(np.int64)     # [8]
                session_id = key.split(":", 2)[2]
                session_ids.append(session_id)
                cont_list.append(cont)
                cat_list.append(cat)
            except Exception:
                continue

        print(f"Loaded sessions: {min(i + batch_size, total):,}/{total:,}", end="\r", flush=True)

    print(f"Loaded sessions: {len(session_ids):,}/{total:,} usable entries")
    return session_ids, cont_list, cat_list


def _fetch_countries(
    session_ids: list[str], vector_url: str, vector_token: str
) -> dict[str, str]:
    """Fetch ip_country for each session_id from Upstash Vector metadata."""
    countries: dict[str, str] = {}
    batch_size = 100
    total = len(session_ids)
    for i in range(0, total, batch_size):
        batch = session_ids[i : i + batch_size]
        try:
            r = httpx.post(
                vector_url.rstrip("/") + "/fetch",
                headers={"Authorization": f"Bearer {vector_token}"},
                json={"ids": batch, "includeMetadata": True, "includeVectors": False},
                timeout=60,
            )
            if r.is_success:
                for item in r.json().get("result", []):
                    if item and item.get("metadata"):
                        sid = item["id"]
                        countries[sid] = str(item["metadata"].get("ip_country", "??"))
        except Exception:
            pass
        print(f"Fetched metadata: {min(i + batch_size, total):,}/{total:,}", end="\r", flush=True)
    print(f"Fetched metadata: {len(countries):,}/{total:,} with country")
    return countries


def _encode_vectors(
    weights_path: Path,
    cont_list: list[np.ndarray],
    cat_list: list[np.ndarray],
) -> np.ndarray:
    sys.path.insert(0, str(REPO_ROOT / "packages" / "model-worker"))
    from src.inference.transformer import BehavioralTransformer  # noqa: E402

    model = BehavioralTransformer()
    state = torch.load(weights_path, map_location="cpu", weights_only=True)
    model.load_state_dict(state)
    model.eval()

    vectors: list[np.ndarray] = []
    with torch.no_grad():
        for idx, (cont, cat) in enumerate(zip(cont_list, cat_list), start=1):
            cont_t = torch.from_numpy(cont).unsqueeze(0)  # [1, 256, 40]
            cat_t  = torch.from_numpy(cat).unsqueeze(0)   # [1, 8]
            vec = model(cont_t, cat_t).squeeze(0).cpu().numpy().astype(np.float32)
            vectors.append(vec)
            if idx % 500 == 0:
                print(f"Encoded vectors: {idx:,}/{len(cont_list):,}", end="\r", flush=True)

    print(f"Encoded vectors: {len(vectors):,}/{len(cont_list):,}")
    return np.vstack(vectors) if vectors else np.empty((0, 192), dtype=np.float32)


def _best_cluster(
    vectors_np: np.ndarray, n: int
) -> tuple[np.ndarray, int, float, float, float]:
    """Sweep K=2..min(8, n//5), return labels+metrics for best silhouette K."""
    k_range = list(range(2, min(9, max(3, n // 5 + 1))))
    best_labels, best_k, best_sil = None, k_range[0], -1.0

    print(f"Sweeping K = {k_range[0]}..{k_range[-1]}:")
    for k in k_range:
        km     = KMeans(n_clusters=k, random_state=42, n_init=20)
        labels = km.fit_predict(vectors_np)
        sil    = float(silhouette_score(vectors_np, labels, metric="cosine"))
        print(f"  K={k}  Silhouette={sil:.4f}")
        if sil > best_sil:
            best_sil    = sil
            best_k      = k
            best_labels = labels
            best_km     = km

    print(f"Best K = {best_k}  (Silhouette={best_sil:.4f})")

    centroids = best_km.cluster_centers_
    inter = [
        float(cosine_distances([centroids[i]], [centroids[j]])[0][0])
        for i in range(best_k)
        for j in range(i + 1, best_k)
    ]
    mean_inter = float(np.mean(inter)) if inter else 0.0

    intra = []
    for c in range(best_k):
        mask = best_labels == c
        if mask.sum() > 0:
            intra.extend(cosine_distances(vectors_np[mask], [centroids[c]]).flatten().tolist())
    net_sep = mean_inter - float(np.mean(intra)) if intra else 0.0

    return best_labels, best_k, best_sil, mean_inter, net_sep


def _save_umap_plot(
    org_id: str,
    vectors_np: np.ndarray,
    labels: np.ndarray,
    k: int,
    countries: dict[str, str],
    session_ids: list[str],
    out_path: Path,
) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    try:
        import umap as umap_lib
        proj   = umap_lib.UMAP(n_components=2, random_state=42, metric="cosine").fit_transform(vectors_np)
        method = "UMAP"
    except Exception:
        from sklearn.decomposition import PCA
        proj   = PCA(n_components=2, random_state=42).fit_transform(vectors_np)
        method = "PCA"

    ip_countries = np.array([countries.get(sid, "??") for sid in session_ids])
    cmap = plt.cm.tab10(np.linspace(0, 0.9, k))

    fig, ax = plt.subplots(figsize=(10, 8))
    for cid in range(k):
        mask = labels == cid
        ax.scatter(
            proj[mask, 0], proj[mask, 1],
            color=cmap[cid], marker="o",
            s=100, alpha=0.8, edgecolors="black", linewidths=0.4,
            label=f"Cluster {cid}  (n={int(mask.sum())})",
        )
        for idx in np.where(mask)[0]:
            ax.annotate(
                ip_countries[idx],
                (proj[idx, 0], proj[idx, 1]),
                fontsize=6, ha="center", va="bottom",
                xytext=(0, 4), textcoords="offset points", alpha=0.7,
            )

    ax.set_xlabel(f"{method}-1")
    ax.set_ylabel(f"{method}-2")
    ax.set_title(f"Session Clusters ({method}) — {org_id}\ncolour = cluster, label = country")
    ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=9)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()


def main() -> None:
    p = argparse.ArgumentParser(description="Cluster analysis on freshly encoded vectors from local weights.")
    p.add_argument("--org",     required=True, help="Org id to analyze.")
    p.add_argument("--weights", default=None,  help="Path to .pt weights. Defaults to scripts/output/training/{org}.pt")
    args = p.parse_args()

    loaded_env = _load_env_candidates()
    if loaded_env is None:
        raise RuntimeError("No env file found. Expected beta/.env or .env at repo root.")

    redis_url    = os.environ.get("UPSTASH_REDIS_URL",    "").rstrip("/")
    redis_token  = os.environ.get("UPSTASH_REDIS_TOKEN",  "")
    vector_url   = os.environ.get("UPSTASH_VECTOR_URL",   "").rstrip("/")
    vector_token = os.environ.get("UPSTASH_VECTOR_TOKEN", "")
    if not redis_url or not redis_token:
        raise RuntimeError("UPSTASH_REDIS_URL and UPSTASH_REDIS_TOKEN must be set.")

    weights_path = (
        Path(args.weights).resolve()
        if args.weights
        else (SCRIPTS_DIR / "output" / "training" / f"{args.org}.pt").resolve()
    )
    if not weights_path.exists():
        raise FileNotFoundError(f"Weights not found: {weights_path}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Env loaded from: {loaded_env}")
    print(f"Using weights  : {weights_path}")
    print(f"Output dir     : {OUTPUT_DIR}")
    print(f"Org            : {args.org}\n")

    keys = _scan_feature_keys(redis_url, redis_token, args.org)
    if not keys:
        raise RuntimeError(f"No Redis feature keys found for org: {args.org}")
    print(f"Discovered feature keys: {len(keys):,}")

    session_ids, cont_list, cat_list = _load_sessions(redis_url, redis_token, keys)
    if len(session_ids) < 4:
        raise RuntimeError(f"Not enough valid sessions to cluster: {len(session_ids)}")

    vectors_np = _encode_vectors(weights_path, cont_list, cat_list)
    if len(vectors_np) < 4:
        raise RuntimeError(f"Not enough vectors to cluster: {len(vectors_np)}")

    labels, best_k, sil, mean_inter, net_sep = _best_cluster(vectors_np, len(vectors_np))

    # Fetch country metadata for annotations (best-effort, fallback to "??")
    countries: dict[str, str] = {}
    if vector_url and vector_token:
        countries = _fetch_countries(session_ids, vector_url, vector_token)

    # Save vectors + assignments
    vectors_path = OUTPUT_DIR / f"vectors_{args.org}.npz"
    np.savez_compressed(vectors_path, vectors=vectors_np, session_ids=np.array(session_ids))

    assignments_path = OUTPUT_DIR / f"assignments_{args.org}.csv"
    with assignments_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["session_id", "cluster"])
        for sid, c in zip(session_ids, labels):
            writer.writerow([sid, int(c)])

    metrics = {
        "org_id":                             args.org,
        "k":                                  int(best_k),
        "n_sessions":                         int(len(session_ids)),
        "silhouette_cosine":                  float(sil),
        "mean_inter_cluster_cosine_distance": float(mean_inter),
        "net_separation":                     float(net_sep),
        "weights_path":                       str(weights_path),
        "env_path":                           str(loaded_env),
    }
    metrics_path = OUTPUT_DIR / f"metrics_{args.org}.json"
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    plot_path = OUTPUT_DIR / f"umap_clusters_{args.org}.png"
    _save_umap_plot(args.org, vectors_np, labels, best_k, countries, session_ids, plot_path)

    print("\nDone.")
    print(f"  Best K           : {best_k}")
    print(f"  Silhouette       : {sil:.4f}")
    print(f"  Net separation   : {net_sep:.4f}")
    print(f"  Cluster sizes    : { {c: int((labels == c).sum()) for c in range(best_k)} }")
    print(f"\nSaved vectors    : {vectors_path}")
    print(f"Saved assignments: {assignments_path}")
    print(f"Saved metrics    : {metrics_path}")
    print(f"Saved plot       : {plot_path}")


if __name__ == "__main__":
    main()
