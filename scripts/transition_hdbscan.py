"""
Transition Matrix + HDBSCAN Session Clustering
===============================================
Source  : metricade_sess:{org_id}:{session_id} keys in Redis (same as RRCF)
Pipeline: Raw events → 9x9 transition matrix → flatten → UMAP → HDBSCAN → labeled CSV

ADJUSTABLE PARAMETERS (see CONFIG block below):
  NUM_WORKERS       — parallel Redis fetch threads (default 10)
  BATCH_SIZE        — keys per pipeline call (default 100)
  MIN_EVENTS        — skip sessions with fewer events (default 5)
  MIN_TRANSITIONS   — skip sessions with fewer A→B pairs (default 3)
  UMAP_N_COMPONENTS — dimensions before HDBSCAN (default 10)
  UMAP_N_NEIGHBORS  — UMAP local neighborhood size (default 15)
  HDBSCAN_MIN_SIZE  — min sessions to form a cluster (default 10)
  HDBSCAN_MIN_SAMPLES — core point threshold (default 5)
  NORMALIZE_ROWS    — normalize each matrix row to probabilities (default True)
                      False = use raw counts (captures volume differences too)

Usage:
  python transition_hdbscan.py --org org_XXXX
  python transition_hdbscan.py --org org_XXXX --rrcf scripts/output/rrcf/scores_org_XXXX_full.csv
  python transition_hdbscan.py --org org_XXXX --verdict ANOMALOUS borderline   # filter by RRCF verdict
"""

import argparse
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
REQUIRED = [("httpx", "httpx"), ("numpy", "numpy"), ("scikit-learn", "sklearn"),
            ("umap-learn", "umap"), ("hdbscan", "hdbscan"), ("matplotlib", "matplotlib")]
for pkg, imp in REQUIRED:
    try:
        __import__(imp)
    except ImportError:
        print(f"[install] Installing {pkg}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"[install] {pkg} installed.")

import httpx
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.cm as cm

# ══════════════════════════════════════════════════════════════════════════════
# CONFIG — tweak these to change behaviour
# ══════════════════════════════════════════════════════════════════════════════
CONFIG = {
    "NUM_WORKERS":          10,     # parallel HTTP threads for Redis fetch
    "BATCH_SIZE":           100,    # keys per pipeline call
    "MIN_EVENTS":           5,      # skip sessions with fewer total events
    "MIN_TRANSITIONS":      3,      # skip sessions with fewer A→B pairs
    "UMAP_N_COMPONENTS":    10,     # UMAP target dims before HDBSCAN
    "UMAP_N_NEIGHBORS":     15,     # UMAP: larger = more global structure
    "UMAP_MIN_DIST":        0.1,    # UMAP: smaller = tighter clusters
    "HDBSCAN_MIN_SIZE":     10,     # min sessions per cluster (tune this first)
    "HDBSCAN_MIN_SAMPLES":  10,      # core point density requirement
    "NORMALIZE_ROWS":       True,   # True=probabilities, False=raw counts
}

# ── Event type vocabulary (order matters — defines matrix rows/cols) ──────────
EVENT_TYPES = [
    "page_view", "route_change", "scroll", "touch_end", "click",
    "tab_hidden", "tab_visible", "engagement_tick", "idle",
]
N_EVENTS = len(EVENT_TYPES)
ET_IDX   = {e: i for i, e in enumerate(EVENT_TYPES)}  # name → index

# ── Output directory ──────────────────────────────────────────────────────────
OUT_BASE = Path("scripts/output/transition_hdbscan")


# ══════════════════════════════════════════════════════════════════════════════
# LOGGING SETUP
# ══════════════════════════════════════════════════════════════════════════════
def setup_logging(out_dir: Path, org_id: str) -> logging.Logger:
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / f"run_{org_id}.log"

    fmt = logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s",
                            datefmt="%H:%M:%S")

    file_handler = logging.FileHandler(log_path, mode="w")
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(fmt)
    console_handler.setLevel(logging.INFO)

    log = logging.getLogger("tm_hdbscan")
    log.setLevel(logging.DEBUG)
    log.addHandler(file_handler)
    log.addHandler(console_handler)

    log.info("="*70)
    log.info("Transition Matrix + HDBSCAN Session Clustering")
    log.info("="*70)
    log.info(f"Log file : {log_path}")
    return log


# ══════════════════════════════════════════════════════════════════════════════
# ENV / REDIS
# ══════════════════════════════════════════════════════════════════════════════
def load_env(log: logging.Logger):
    for candidate in [Path(__file__).resolve().parent / ".env",
                      Path(__file__).resolve().parent.parent / ".env"]:
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
            log.info(f"Loaded env from: {candidate}")
            return
    log.warning("No .env file found — relying on environment variables")


def scan_all_keys(pattern: str, redis_url: str, token: str,
                  log: logging.Logger) -> list[str]:
    log.info(f"SCAN pattern: {pattern}")
    keys, cursor = [], "0"
    pages = 0
    while True:
        r = httpx.post(f"{redis_url}/pipeline",
                       headers={"Authorization": f"Bearer {token}"},
                       json=[["SCAN", cursor, "MATCH", pattern, "COUNT", "500"]],
                       timeout=30)
        r.raise_for_status()
        result = r.json()[0]["result"]
        cursor = result[0]
        batch  = result[1]
        keys.extend(batch)
        pages += 1
        log.debug(f"  SCAN page {pages}: cursor={cursor}, got {len(batch)} keys, total={len(keys)}")
        if cursor == "0":
            break
    log.info(f"SCAN complete: {len(keys):,} keys found across {pages} pages")
    return keys


def _fetch_one_batch(args):
    """Worker fn: fetch one batch of Redis keys. Returns [(key, raw|None)]."""
    keys, redis_url, token = args
    cmds = [["GET", k] for k in keys]
    try:
        r = httpx.post(f"{redis_url}/pipeline",
                       headers={"Authorization": f"Bearer {token}"},
                       json=cmds, timeout=30)
        r.raise_for_status()
        data = r.json()
        return [(keys[i], data[i].get("result")) for i in range(len(keys))]
    except Exception as e:
        return [(k, None) for k in keys]


def fetch_all_parallel(keys: list[str], redis_url: str, token: str,
                       log: logging.Logger) -> dict[str, str | None]:
    bs = CONFIG["BATCH_SIZE"]
    nw = CONFIG["NUM_WORKERS"]
    batches = [(keys[i:i+bs], redis_url, token) for i in range(0, len(keys), bs)]
    log.info(f"Fetching {len(keys):,} keys — {len(batches)} batches × batch_size={bs} "
             f"using {nw} parallel workers")

    results: dict[str, str | None] = {}
    done = 0
    null_count = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=nw) as pool:
        futures = {pool.submit(_fetch_one_batch, b): b for b in batches}
        for fut in as_completed(futures):
            for key, val in fut.result():
                results[key] = val
                if val is None:
                    null_count += 1
            done += len(futures[fut])
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0
            print(f"\r  Fetched {min(done, len(keys)):>6,}/{len(keys):,}  "
                  f"({rate:.0f} keys/s)", end="", flush=True)
    print()

    elapsed = time.time() - t0
    log.info(f"Fetch complete: {len(results):,} keys in {elapsed:.1f}s  "
             f"({len(results)/elapsed:.0f} keys/s)")
    log.info(f"  Keys with data : {len(results) - null_count:,}")
    log.info(f"  Keys missing   : {null_count:,}")
    return results


# ══════════════════════════════════════════════════════════════════════════════
# TRANSITION MATRIX BUILDER
# ══════════════════════════════════════════════════════════════════════════════
def build_transition_matrix(events: list[dict]) -> np.ndarray | None:
    """
    Build a 9×9 transition matrix from a session event list.
    Returns float32 array of shape (N_EVENTS, N_EVENTS) or None if too sparse.
    """
    matrix = np.zeros((N_EVENTS, N_EVENTS), dtype=np.float32)
    n_transitions = 0

    for i in range(len(events) - 1):
        a = events[i].get("event_type", "")
        b = events[i + 1].get("event_type", "")
        if a in ET_IDX and b in ET_IDX:
            matrix[ET_IDX[a], ET_IDX[b]] += 1
            n_transitions += 1

    if n_transitions < CONFIG["MIN_TRANSITIONS"]:
        return None

    if CONFIG["NORMALIZE_ROWS"]:
        row_sums = matrix.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1  # avoid div/0
        matrix = matrix / row_sums

    return matrix


def describe_matrix(matrix: np.ndarray) -> str:
    """Human-readable dominant transition for logging."""
    flat = matrix.flatten()
    idx  = flat.argmax()
    r, c = divmod(idx, N_EVENTS)
    return (f"{EVENT_TYPES[r]}→{EVENT_TYPES[c]} "
            f"({matrix[r, c]:.1%})")


# ══════════════════════════════════════════════════════════════════════════════
# RRCF CSV LOADER
# ══════════════════════════════════════════════════════════════════════════════
def load_rrcf_csv(path: str, log: logging.Logger) -> dict[str, dict]:
    """Returns {session_id: {rrcf_score, verdict, n_events, n_scroll}}"""
    out = {}
    with open(path) as f:
        header = f.readline()
        for line in f:
            parts = line.strip().split(",")
            if len(parts) < 6:
                continue
            sid     = parts[0]
            score   = parts[1] if parts[1] != "None" else None
            verdict = parts[5].strip()
            out[sid] = {
                "rrcf_score": float(score) if score else None,
                "verdict":    verdict,
                "n_events":   int(parts[3]) if parts[3].isdigit() else 0,
                "n_scroll":   int(parts[4]) if parts[4].isdigit() else 0,
            }
    counts = defaultdict(int)
    for v in out.values():
        counts[v["verdict"]] += 1
    log.info(f"Loaded RRCF CSV: {len(out):,} sessions")
    for verdict, n in sorted(counts.items()):
        log.info(f"  {verdict:<25} {n:>6,}")
    return out


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="Transition Matrix + HDBSCAN clustering")
    parser.add_argument("--org",      required=True,  help="org_id to process")
    parser.add_argument("--rrcf",     default=None,   help="Path to RRCF scores CSV (optional — adds verdict column)")
    parser.add_argument("--verdict",  nargs="*",      help="Filter to these RRCF verdicts only e.g. ANOMALOUS borderline")
    parser.add_argument("--min-cluster-size", type=int, default=None,
                        help=f"Override HDBSCAN min_cluster_size (default {CONFIG['HDBSCAN_MIN_SIZE']})")
    parser.add_argument("--no-umap",  action="store_true",
                        help="Skip UMAP, run HDBSCAN on raw 81-dim matrix (slower, more precise)")
    args = parser.parse_args()

    # Override config from CLI
    if args.min_cluster_size:
        CONFIG["HDBSCAN_MIN_SIZE"] = args.min_cluster_size

    # Setup
    out_dir = OUT_BASE / args.org
    log = setup_logging(out_dir, args.org)
    load_env(log)

    redis_url   = os.environ.get("UPSTASH_REDIS_URL", "").rstrip("/")
    redis_token = os.environ.get("UPSTASH_REDIS_TOKEN", "")
    if not redis_url:
        log.error("UPSTASH_REDIS_URL not set. Aborting.")
        sys.exit(1)

    # Log config
    log.info("─"*70)
    log.info("CONFIG")
    for k, v in CONFIG.items():
        log.info(f"  {k:<25} = {v}")
    log.info(f"  UMAP enabled            = {not args.no_umap}")
    log.info("─"*70)

    # ── Load RRCF data ────────────────────────────────────────────────────────
    rrcf_data: dict[str, dict] = {}
    if args.rrcf:
        log.info(f"STEP 1/7 — Loading RRCF CSV: {args.rrcf}")
        rrcf_data = load_rrcf_csv(args.rrcf, log)
    else:
        log.info("STEP 1/7 — No RRCF CSV provided (all sessions will be processed)")

    # ── Determine which session IDs to process ────────────────────────────────
    log.info("─"*70)
    log.info("STEP 2/7 — Scanning Redis for session keys")
    t0 = time.time()
    all_keys = scan_all_keys(f"metricade_sess:{args.org}:*", redis_url, redis_token, log)

    if args.verdict and rrcf_data:
        filter_set = set(args.verdict)
        before = len(all_keys)
        all_keys = [k for k in all_keys
                    if k.split(":")[-1] in rrcf_data
                    and rrcf_data[k.split(":")[-1]]["verdict"] in filter_set]
        log.info(f"Filtered by verdict {filter_set}: {before:,} → {len(all_keys):,} sessions")
    else:
        log.info(f"No verdict filter applied — processing all {len(all_keys):,} sessions")

    if not all_keys:
        log.error("No sessions to process after filtering. Aborting.")
        sys.exit(1)

    # ── Fetch ─────────────────────────────────────────────────────────────────
    log.info("─"*70)
    log.info("STEP 3/7 — Fetching session data from Redis")
    raw_map = fetch_all_parallel(all_keys, redis_url, redis_token, log)

    # ── Build transition matrices ─────────────────────────────────────────────
    log.info("─"*70)
    log.info("STEP 4/7 — Building transition matrices")
    log.info(f"  Normalize rows : {CONFIG['NORMALIZE_ROWS']}")
    log.info(f"  Min events     : {CONFIG['MIN_EVENTS']}")
    log.info(f"  Min transitions: {CONFIG['MIN_TRANSITIONS']}")

    session_ids  = []
    matrices     = []
    skipped_null = 0
    skipped_short = 0
    skipped_sparse = 0
    event_type_totals = defaultdict(int)

    for redis_key, raw in raw_map.items():
        sid = redis_key.split(":")[-1]

        if raw is None:
            skipped_null += 1
            log.debug(f"  SKIP {sid[:8]} — Redis returned None")
            continue

        try:
            events = json.loads(raw)
        except json.JSONDecodeError as e:
            skipped_null += 1
            log.debug(f"  SKIP {sid[:8]} — JSON parse error: {e}")
            continue

        if len(events) < CONFIG["MIN_EVENTS"]:
            skipped_short += 1
            log.debug(f"  SKIP {sid[:8]} — only {len(events)} events < MIN_EVENTS={CONFIG['MIN_EVENTS']}")
            continue

        # Count event types for global stats
        for e in events:
            et = e.get("event_type", "unknown")
            event_type_totals[et] += 1

        matrix = build_transition_matrix(events)
        if matrix is None:
            skipped_sparse += 1
            log.debug(f"  SKIP {sid[:8]} — transition count < MIN_TRANSITIONS={CONFIG['MIN_TRANSITIONS']}")
            continue

        session_ids.append(sid)
        matrices.append(matrix.flatten())  # 9×9 → 81-dim vector

    log.info(f"Matrix building complete:")
    log.info(f"  Sessions processed : {len(session_ids):,}")
    log.info(f"  Skipped (null/err) : {skipped_null:,}")
    log.info(f"  Skipped (too short): {skipped_short:,}")
    log.info(f"  Skipped (sparse)   : {skipped_sparse:,}")
    log.info(f"Global event type distribution across all processed sessions:")
    total_events = sum(event_type_totals.values())
    for et in EVENT_TYPES:
        n = event_type_totals.get(et, 0)
        log.info(f"  {et:<20} {n:>8,}  ({100*n/total_events:.1f}%)")

    if len(session_ids) < 10:
        log.error(f"Only {len(session_ids)} sessions — need at least 10 to cluster. Aborting.")
        sys.exit(1)

    X = np.array(matrices, dtype=np.float32)
    log.info(f"Feature matrix shape: {X.shape}  (sessions × 81 transition probs)")

    # Log a sample of dominant transitions per first 5 sessions
    log.debug("Sample dominant transitions (first 5 sessions):")
    for i in range(min(5, len(session_ids))):
        m = X[i].reshape(N_EVENTS, N_EVENTS)
        log.debug(f"  {session_ids[i][:8]}  dominant: {describe_matrix(m)}")

    # ── UMAP dimensionality reduction ─────────────────────────────────────────
    if not args.no_umap:
        log.info("─"*70)
        log.info("STEP 5/7 — UMAP dimensionality reduction")
        log.info(f"  Input dims      : {X.shape[1]}")
        log.info(f"  Target dims     : {CONFIG['UMAP_N_COMPONENTS']}")
        log.info(f"  n_neighbors     : {CONFIG['UMAP_N_NEIGHBORS']}")
        log.info(f"  min_dist        : {CONFIG['UMAP_MIN_DIST']}")

        import umap as umap_lib
        t_umap = time.time()
        reducer = umap_lib.UMAP(
            n_components = CONFIG["UMAP_N_COMPONENTS"],
            n_neighbors  = CONFIG["UMAP_N_NEIGHBORS"],
            min_dist     = CONFIG["UMAP_MIN_DIST"],
            metric       = "euclidean",
            random_state = 42,
            verbose      = False,
        )
        X_reduced = reducer.fit_transform(X)
        log.info(f"  UMAP complete in {time.time()-t_umap:.1f}s  "
                 f"output shape: {X_reduced.shape}")

        # Also get 2D for plotting
        log.info("  Computing 2D UMAP for visualisation...")
        reducer_2d = umap_lib.UMAP(
            n_components=2, n_neighbors=CONFIG["UMAP_N_NEIGHBORS"],
            min_dist=CONFIG["UMAP_MIN_DIST"], metric="euclidean",
            random_state=42, verbose=False)
        X_2d = reducer_2d.fit_transform(X)
        log.info(f"  2D UMAP complete")
    else:
        log.info("STEP 5/7 — UMAP skipped (--no-umap flag set)")
        log.info(f"  Running HDBSCAN on raw {X.shape[1]}-dim matrix")
        X_reduced = X
        # Still need 2D for plotting — use PCA
        from sklearn.decomposition import PCA
        X_2d = PCA(n_components=2, random_state=42).fit_transform(X)
        log.info("  2D PCA computed for visualisation")

    # ── HDBSCAN ───────────────────────────────────────────────────────────────
    log.info("─"*70)
    log.info("STEP 6/7 — HDBSCAN clustering")
    log.info(f"  min_cluster_size  : {CONFIG['HDBSCAN_MIN_SIZE']}")
    log.info(f"  min_samples       : {CONFIG['HDBSCAN_MIN_SAMPLES']}")
    log.info(f"  Input shape       : {X_reduced.shape}")

    import hdbscan as hdbscan_lib
    t_hdb = time.time()
    clusterer = hdbscan_lib.HDBSCAN(
        min_cluster_size  = CONFIG["HDBSCAN_MIN_SIZE"],
        min_samples       = CONFIG["HDBSCAN_MIN_SAMPLES"],
        metric            = "euclidean",
        cluster_selection_method = "eom",
    )
    labels      = clusterer.fit_predict(X_reduced)
    probs       = clusterer.probabilities_
    outlier_scores = clusterer.outlier_scores_

    elapsed_hdb = time.time() - t_hdb
    n_clusters  = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise     = (labels == -1).sum()

    log.info(f"  HDBSCAN complete in {elapsed_hdb:.1f}s")
    log.info(f"  Clusters found  : {n_clusters}")
    log.info(f"  Noise sessions  : {n_noise:,} ({100*n_noise/len(labels):.1f}%)")

    # Per-cluster stats
    log.info("─"*70)
    log.info("Per-cluster breakdown:")
    log.info(f"  {'Cluster':<10} {'Count':>7}  {'scroll→scroll':>14}  "
             f"{'scroll→idle':>12}  {'scroll→tick':>12}  dominant_transition")
    log.info("  " + "─"*80)

    cluster_profiles = {}
    for cid in sorted(set(labels)):
        mask    = labels == cid
        count   = mask.sum()
        tag     = "NOISE" if cid == -1 else f"C{cid}"
        sub_X   = X[mask].reshape(-1, N_EVENTS, N_EVENTS)
        mean_m  = sub_X.mean(axis=0)

        ss_rate  = mean_m[ET_IDX["scroll"],        ET_IDX["scroll"]]
        si_rate  = mean_m[ET_IDX["scroll"],        ET_IDX["idle"]]
        set_rate = mean_m[ET_IDX["scroll"],        ET_IDX["engagement_tick"]]
        dominant = describe_matrix(mean_m)

        cluster_profiles[cid] = {
            "count":    int(count),
            "ss_rate":  float(ss_rate),
            "si_rate":  float(si_rate),
            "set_rate": float(set_rate),
            "dominant": dominant,
        }

        log.info(f"  {tag:<10} {count:>7,}  {ss_rate:>13.1%}  "
                 f"{si_rate:>11.1%}  {set_rate:>11.1%}  {dominant}")

    # Interpret clusters
    log.info("─"*70)
    log.info("Cluster interpretation (auto-labelled):")
    cluster_labels_named = {}
    for cid, prof in cluster_profiles.items():
        if cid == -1:
            name = "NOISE (no cluster)"
        elif prof["ss_rate"] > 0.85:
            name = "BOT_PATTERN (scroll→scroll dominant)"
        elif prof["si_rate"] > 0.15 or prof["set_rate"] > 0.10:
            name = "HUMAN_READER (natural pauses)"
        elif prof["ss_rate"] > 0.60:
            name = "HEAVY_SCROLLER (human or borderline)"
        else:
            name = f"MIXED_BEHAVIOR"
        cluster_labels_named[cid] = name
        log.info(f"  C{cid if cid >= 0 else 'NOISE':<4} → {name}  (n={prof['count']:,})")

    # ── Save outputs ──────────────────────────────────────────────────────────
    log.info("─"*70)
    log.info("STEP 7/7 — Saving outputs")

    # CSV
    csv_path = out_dir / f"clusters_{args.org}.csv"
    with open(csv_path, "w") as f:
        f.write("session_id,cluster_id,cluster_name,membership_prob,"
                "outlier_score,scroll_scroll,scroll_idle,scroll_tick,"
                "rrcf_score,rrcf_verdict\n")
        for i, sid in enumerate(session_ids):
            cid   = int(labels[i])
            cname = cluster_labels_named.get(cid, "unknown")
            prob  = float(probs[i])
            oscore = float(outlier_scores[i])
            m     = X[i].reshape(N_EVENTS, N_EVENTS)
            ss    = float(m[ET_IDX["scroll"], ET_IDX["scroll"]])
            si    = float(m[ET_IDX["scroll"], ET_IDX["idle"]])
            st    = float(m[ET_IDX["scroll"], ET_IDX["engagement_tick"]])
            rrcf  = rrcf_data.get(sid, {})
            f.write(f"{sid},{cid},{cname},{prob:.4f},{oscore:.4f},"
                    f"{ss:.4f},{si:.4f},{st:.4f},"
                    f"{rrcf.get('rrcf_score','')},{rrcf.get('verdict','')}\n")
    log.info(f"  CSV saved: {csv_path}")

    # Transition matrix averages per cluster
    matrix_path = out_dir / f"mean_matrices_{args.org}.txt"
    with open(matrix_path, "w") as f:
        for cid in sorted(set(labels)):
            tag  = "NOISE" if cid == -1 else f"Cluster {cid}"
            name = cluster_labels_named[cid]
            f.write(f"\n{'='*60}\n{tag}  —  {name}  (n={cluster_profiles[cid]['count']:,})\n")
            f.write(f"{'='*60}\n")
            mask = labels == cid
            mean_m = X[mask].reshape(-1, N_EVENTS, N_EVENTS).mean(axis=0)
            header = f"{'':>18}" + "".join(f"{et[:8]:>10}" for et in EVENT_TYPES)
            f.write(header + "\n")
            for r, et_from in enumerate(EVENT_TYPES):
                row_str = f"{et_from:<18}" + "".join(f"{mean_m[r,c]:>10.3f}" for c in range(N_EVENTS))
                f.write(row_str + "\n")
    log.info(f"  Mean matrices saved: {matrix_path}")

    # Plot: 2D UMAP coloured by cluster
    n_unique = len(set(labels))
    cmap     = cm.get_cmap("tab20", n_unique)
    color_map = {cid: cmap(i) for i, cid in enumerate(sorted(set(labels)))}

    fig, axes = plt.subplots(1, 2, figsize=(16, 7))
    fig.suptitle(f"Transition Matrix Clustering — {args.org}  (n={len(session_ids):,})",
                 fontsize=13, fontweight="bold")

    # Left: UMAP coloured by cluster
    ax = axes[0]
    for cid in sorted(set(labels)):
        mask  = labels == cid
        tag   = "NOISE" if cid == -1 else f"C{cid}"
        name  = cluster_labels_named[cid]
        alpha = 0.3 if cid == -1 else 0.7
        size  = 8  if cid == -1 else 15
        ax.scatter(X_2d[mask, 0], X_2d[mask, 1],
                   color=color_map[cid], s=size, alpha=alpha,
                   label=f"{tag}: {name} (n={mask.sum():,})")
    ax.set_title("2D Projection — coloured by cluster")
    ax.set_xlabel("UMAP-1"); ax.set_ylabel("UMAP-2")
    ax.legend(fontsize=7, loc="upper right")

    # Right: mean scroll→scroll rate per cluster (bar)
    ax2 = axes[1]
    cids   = [c for c in sorted(set(labels)) if c != -1]
    tags   = [f"C{c}" for c in cids]
    rates  = [cluster_profiles[c]["ss_rate"] for c in cids]
    colors = [color_map[c] for c in cids]
    bars   = ax2.bar(tags, rates, color=colors)
    ax2.axhline(0.85, color="red",    linestyle="--", alpha=0.7, label="bot threshold (0.85)")
    ax2.axhline(0.60, color="orange", linestyle="--", alpha=0.7, label="heavy scroller (0.60)")
    ax2.set_ylim(0, 1.05)
    ax2.set_ylabel("Mean scroll→scroll probability")
    ax2.set_title("Scroll→Scroll rate per cluster (bot indicator)")
    ax2.legend(fontsize=8)
    for bar, rate in zip(bars, rates):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                 f"{rate:.1%}", ha="center", va="bottom", fontsize=8)

    plt.tight_layout()
    plot_path = out_dir / f"plot_{args.org}.png"
    plt.savefig(plot_path, dpi=150, bbox_inches="tight")
    plt.close()
    log.info(f"  Plot saved: {plot_path}")

    total_time = time.time() - t0
    log.info("─"*70)
    log.info(f"COMPLETE — total time: {total_time:.1f}s  ({total_time/60:.1f} min)")
    log.info(f"Output folder: {out_dir.resolve()}")
    log.info(f"  {csv_path.name}")
    log.info(f"  {matrix_path.name}")
    log.info(f"  {plot_path.name}")
    log.info(f"  run_{args.org}.log")
    log.info("="*70)


if __name__ == "__main__":
    main()