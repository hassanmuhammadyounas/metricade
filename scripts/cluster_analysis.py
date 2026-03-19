"""
Offline K-Means clustering analysis on session vectors from Upstash Vector.

Usage:
    python scripts/cluster_analysis.py

Reads credentials from .env at the repo root (or from environment variables):
    UPSTASH_REDIS_URL, UPSTASH_REDIS_TOKEN
    UPSTASH_VECTOR_URL, UPSTASH_VECTOR_TOKEN

Dependencies:
    pip install scikit-learn umap-learn matplotlib numpy httpx python-dotenv
"""

import os
import sys
import random
import httpx
import numpy as np
from collections import Counter
from pathlib import Path

# Load .env from repo root (two levels up from scripts/)
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_path)
    except ImportError:
        # Fallback: manual parse if python-dotenv not installed
        for line in _env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

# ── Config ────────────────────────────────────────────────────────────────────

REDIS_URL    = os.environ.get("UPSTASH_REDIS_URL", "").rstrip("/")
REDIS_TOKEN  = os.environ.get("UPSTASH_REDIS_TOKEN", "")
VECTOR_URL   = os.environ.get("UPSTASH_VECTOR_URL", "").rstrip("/")
VECTOR_TOKEN = os.environ.get("UPSTASH_VECTOR_TOKEN", "")

for var, val in [("UPSTASH_REDIS_URL", REDIS_URL), ("UPSTASH_REDIS_TOKEN", REDIS_TOKEN),
                 ("UPSTASH_VECTOR_URL", VECTOR_URL), ("UPSTASH_VECTOR_TOKEN", VECTOR_TOKEN)]:
    if not val:
        print(f"ERROR: {var} is not set.")
        sys.exit(1)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

http = httpx.Client(timeout=30)

# ── Redis helpers ─────────────────────────────────────────────────────────────

def redis_cmd(cmd):
    r = http.post(f"{REDIS_URL}/pipeline",
                  headers={"Authorization": f"Bearer {REDIS_TOKEN}"},
                  json=[cmd])
    r.raise_for_status()
    return r.json()[0]["result"]


def scan_keys(pattern):
    keys, cursor = [], "0"
    while True:
        result = redis_cmd(["SCAN", cursor, "MATCH", pattern, "COUNT", "1000"])
        cursor = result[0]
        keys.extend(result[1])
        if cursor == "0":
            break
    return keys


# ── Vector helpers ────────────────────────────────────────────────────────────

def fetch_vectors_for_org(org_id):
    """Fetch all vectors for an org from Upstash Vector, filtering by org_id in metadata."""
    vectors, session_ids, cursor = [], [], "0"
    total_fetched = 0

    print(f"\nFetching vectors for {org_id}...")
    while True:
        r = http.post(f"{VECTOR_URL}/range",
                      headers={"Authorization": f"Bearer {VECTOR_TOKEN}"},
                      json={"cursor": cursor, "limit": 1000,
                            "includeMetadata": True, "includeVectors": True},
                      timeout=60)
        r.raise_for_status()
        data = r.json().get("result", {})
        batch = data.get("vectors", [])

        for v in batch:
            meta = v.get("metadata") or {}
            if meta.get("org_id") == org_id:
                vec = v.get("vector")
                if vec:
                    vectors.append(vec)
                    session_ids.append(v.get("id", ""))

        total_fetched += len(batch)
        cursor = data.get("nextCursor", "")
        print(f"  Scanned {total_fetched} vectors, matched {len(vectors)} for {org_id}...", end="\r")

        if not cursor:
            break

    print(f"  Scanned {total_fetched} vectors total, {len(vectors)} matched for {org_id}.    ")
    return vectors, session_ids


# ── Step 1: Org selection ─────────────────────────────────────────────────────

def discover_orgs():
    stream_keys = scan_keys("metricade_stream:*")
    orgs = sorted(set(k.split(":", 1)[1] for k in stream_keys if ":" in k))
    if not orgs:
        print("No org streams found in Redis.")
        sys.exit(1)

    print("\nAvailable organizations:")
    session_counts = {}
    for org in orgs:
        feature_keys = scan_keys(f"metricade_features:{org}:*")
        session_counts[org] = len(feature_keys)

    for i, org in enumerate(orgs, 1):
        print(f"  [{i}] {org}   —  {session_counts[org]:>6,} sessions")

    print(f"\nSelect organization (1-{len(orgs)}): ", end="")
    while True:
        try:
            choice = int(input().strip())
            if 1 <= choice <= len(orgs):
                return orgs[choice - 1]
        except (ValueError, EOFError):
            pass
        print(f"Please enter a number between 1 and {len(orgs)}: ", end="")


# ── Step 3: K-Means clustering ────────────────────────────────────────────────

def run_clustering(vectors_np, k=3):
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    from sklearn.metrics.pairwise import cosine_distances

    print(f"\nRunning K-Means (k={k}) on {len(vectors_np):,} vectors...")
    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = km.fit_predict(vectors_np)

    sil = silhouette_score(vectors_np, labels, metric="cosine")
    centroids = km.cluster_centers_

    # Per-cluster stats
    cluster_stats = []
    for c in range(k):
        mask = labels == c
        cluster_vecs = vectors_np[mask]
        centroid = centroids[c]
        dists = np.linalg.norm(cluster_vecs - centroid, axis=1)
        cluster_stats.append({
            "count": int(mask.sum()),
            "intra_spread": float(dists.mean()),
        })

    # Inter-cluster distances (cosine)
    inter = {}
    for i in range(k):
        for j in range(i + 1, k):
            d = cosine_distances([centroids[i]], [centroids[j]])[0][0]
            inter[(i, j)] = float(d)

    return labels, sil, cluster_stats, inter


# ── Step 4: Display results ───────────────────────────────────────────────────

def print_results(org_id, labels, sil, cluster_stats, inter):
    total = len(labels)
    k = len(cluster_stats)

    print(f"\nCluster Analysis Results — {org_id}")
    print("=" * 44)
    print(f"Total sessions clustered: {total:,}")
    print(f"Silhouette score: {sil:.3f}  (0=random, 1=perfect)\n")

    header = f"{'Cluster':<8} {'Sessions':<10} {'% of Total':<12} {'Intra-spread':<14}"
    print(header)
    print("-" * len(header))
    for c, stats in enumerate(cluster_stats):
        pct = 100 * stats["count"] / total
        print(f"{c:<8} {stats['count']:<10,} {pct:<12.1f} {stats['intra_spread']:<14.3f}")

    print("\nInter-cluster distances (cosine):")
    for (i, j), d in sorted(inter.items()):
        print(f"  Cluster {i} ↔ {j}: {d:.3f}")


# ── Step 4b: Plots ────────────────────────────────────────────────────────────

def make_plots(org_id, vectors_np, labels, cluster_stats):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    k = len(cluster_stats)
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle(f"Cluster Analysis — {org_id}", fontsize=14, fontweight="bold")

    # 2D projection
    try:
        import umap
        print("\nReducing dimensions with UMAP...")
        reducer = umap.UMAP(n_components=2, random_state=42, metric="cosine")
        proj = reducer.fit_transform(vectors_np)
        method = "UMAP"
    except ImportError:
        print("\numap-learn not installed, falling back to PCA...")
        from sklearn.decomposition import PCA
        proj = PCA(n_components=2, random_state=42).fit_transform(vectors_np)
        method = "PCA"

    colors = plt.cm.tab10.colors
    ax1 = axes[0]
    for c in range(k):
        mask = labels == c
        ax1.scatter(proj[mask, 0], proj[mask, 1],
                    s=5, alpha=0.5, color=colors[c % len(colors)], label=f"Cluster {c}")
    ax1.set_title(f"2D Projection ({method})")
    ax1.set_xlabel("Component 1")
    ax1.set_ylabel("Component 2")
    ax1.legend(markerscale=3)

    # Bar chart
    ax2 = axes[1]
    counts = [s["count"] for s in cluster_stats]
    bars = ax2.bar(range(k), counts, color=[colors[c % len(colors)] for c in range(k)])
    ax2.set_xticks(range(k))
    ax2.set_xticklabels([f"Cluster {c}" for c in range(k)])
    ax2.set_ylabel("Session count")
    ax2.set_title("Sessions per Cluster")
    for bar, count in zip(bars, counts):
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                 str(count), ha="center", va="bottom", fontsize=10)

    plt.tight_layout()
    out_path = os.path.join(OUTPUT_DIR, f"cluster_analysis_{org_id}.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Plot saved to: {out_path}")
    return out_path


# ── Step 5: Sample session IDs ────────────────────────────────────────────────

def print_samples(labels, session_ids, k=3, n=5):
    print("\nSample session IDs per cluster:")
    for c in range(k):
        idxs = [i for i, l in enumerate(labels) if l == c]
        sample = random.sample(idxs, min(n, len(idxs)))
        print(f"\nCluster {c} sample session IDs:")
        for i in sample:
            print(f"  - {session_ids[i]}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    org_id = discover_orgs()
    print(f"\nSelected: {org_id}")

    vectors, session_ids = fetch_vectors_for_org(org_id)

    if len(vectors) < 3:
        print(f"Not enough vectors to cluster ({len(vectors)} found, need at least 3).")
        sys.exit(1)

    vectors_np = np.array(vectors, dtype=np.float32)
    print(f"Total vectors fetched: {len(vectors_np):,}")

    k = 3
    labels, sil, cluster_stats, inter = run_clustering(vectors_np, k=k)

    print_results(org_id, labels, sil, cluster_stats, inter)
    make_plots(org_id, vectors_np, labels, cluster_stats)
    print_samples(labels, session_ids, k=k)

    print("\nDone.")


if __name__ == "__main__":
    main()
