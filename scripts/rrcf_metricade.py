"""
Fast RRCF anomaly detection on all Redis sessions.
- Parallel Redis fetching (10 workers)
- Asks trees/window interactively
- No sample limit

Usage:
    python rrcf_fast.py --org org_XXXX
"""

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ── Auto-install ──────────────────────────────────────────────────────────────
import subprocess
for pkg, imp in [("rrcf", "rrcf"), ("httpx", "httpx"), ("matplotlib", "matplotlib")]:
    try:
        __import__(imp)
    except ImportError:
        print(f"Installing {pkg}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

import httpx
import rrcf
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ── Env ───────────────────────────────────────────────────────────────────────
for candidate in [Path(__file__).resolve().parent / ".env",
                  Path(__file__).resolve().parent.parent / ".env"]:
    if candidate.exists():
        for line in candidate.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
        break

REDIS_URL   = os.environ.get("UPSTASH_REDIS_URL", "").rstrip("/")
REDIS_TOKEN = os.environ.get("UPSTASH_REDIS_TOKEN", "")
OUT_DIR     = Path("scripts/output/rrcf")
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ── Redis ─────────────────────────────────────────────────────────────────────
BATCH_SIZE   = 100   # keys per pipeline call
NUM_WORKERS  = 10    # parallel HTTP threads

def _fetch_batch(keys: list[str]) -> list[tuple[str, str | None]]:
    """Fetch one batch of keys, return [(key, raw_json|None)]."""
    cmds = [["GET", k] for k in keys]
    try:
        r = httpx.post(
            f"{REDIS_URL}/pipeline",
            headers={"Authorization": f"Bearer {REDIS_TOKEN}"},
            json=cmds,
            timeout=30,
        )
        r.raise_for_status()
        results = r.json()
        return [(keys[i], results[i].get("result")) for i in range(len(keys))]
    except Exception as e:
        return [(k, None) for k in keys]


def fetch_all_parallel(keys: list[str]) -> dict[str, str | None]:
    """Fetch all keys in parallel batches. Returns {key: raw_json}."""
    batches = [keys[i:i+BATCH_SIZE] for i in range(0, len(keys), BATCH_SIZE)]
    results: dict[str, str | None] = {}
    done = 0

    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as pool:
        futures = {pool.submit(_fetch_batch, b): b for b in batches}
        for fut in as_completed(futures):
            for key, val in fut.result():
                results[key] = val
            done += len(futures[fut])
            print(f"\r  Fetched {min(done, len(keys))}/{len(keys)}", end="", flush=True)
    print()
    return results


def scan_keys(pattern: str) -> list[str]:
    keys, cursor = [], "0"
    while True:
        r = httpx.post(
            f"{REDIS_URL}/pipeline",
            headers={"Authorization": f"Bearer {REDIS_TOKEN}"},
            json=[["SCAN", cursor, "MATCH", pattern, "COUNT", "500"]],
            timeout=30,
        )
        r.raise_for_status()
        result = r.json()[0]["result"]
        cursor = result[0]
        keys.extend(result[1])
        if cursor == "0":
            break
    return keys


# ── Feature extraction ────────────────────────────────────────────────────────
def extract_scroll_series(events: list[dict]) -> list[float] | None:
    """Extract scroll velocity series. Returns None if < 3 scroll events."""
    series = [
        float(e.get("scroll_velocity_px_s", 0))
        for e in events
        if e.get("event_type") == "scroll"
    ]
    return series if len(series) >= 3 else None


# ── RRCF scoring ──────────────────────────────────────────────────────────────
def score_session(series: list[float], num_trees: int, shingle_size: int) -> tuple[float, float]:
    """
    Returns (mean_score, max_score) using RRCF shingling.
    Shingle = window of `shingle_size` consecutive values treated as one point.
    """
    n = len(series)
    if n < shingle_size:
        shingle_size = n  # fallback for short series

    # Build shingles
    shingles = [
        tuple(series[i:i + shingle_size])
        for i in range(n - shingle_size + 1)
    ]

    forest = []
    for _ in range(num_trees):
        tree = rrcf.RCTree()
        forest.append(tree)

    scores = []
    for idx, point in enumerate(shingles):
        avg_codisp = 0.0
        for tree in forest:
            if len(tree.leaves) > shingle_size:
                tree.forget_point(idx - shingle_size)
            tree.insert_point(point, index=idx)
            avg_codisp += tree.codisp(idx)
        avg_codisp /= num_trees
        scores.append(avg_codisp)

    return (
        round(sum(scores) / len(scores), 2) if scores else 0.0,
        round(max(scores), 2) if scores else 0.0,
    )


# ── Verdicts ──────────────────────────────────────────────────────────────────
def verdict(score: float, borderline_thresh: float, anomalous_thresh: float) -> str:
    if score >= anomalous_thresh:
        return "ANOMALOUS"
    if score >= borderline_thresh:
        return "borderline"
    return "normal"


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--org",        required=True)
    parser.add_argument("--trees",      type=int,   default=None,  help="Number of trees (skip prompt)")
    parser.add_argument("--window",     type=int,   default=None,  help="Shingle/window size (skip prompt)")
    parser.add_argument("--borderline", type=float, default=40.0,  help="Borderline threshold")
    parser.add_argument("--anomalous",  type=float, default=80.0,  help="Anomalous threshold")
    args = parser.parse_args()

    if not REDIS_URL:
        print("ERROR: UPSTASH_REDIS_URL not set"); sys.exit(1)

    # ── Interactive params ────────────────────────────────────────────────────
    if args.trees is None:
        try:
            args.trees = int(input("Number of trees [default 40]: ").strip() or "40")
        except (ValueError, EOFError):
            args.trees = 40

    if args.window is None:
        try:
            args.window = int(input("Window/shingle size [default 256]: ").strip() or "256")
        except (ValueError, EOFError):
            args.window = 256

    print(f"\nOrg    : {args.org}")
    print(f"Trees  : {args.trees}")
    print(f"Window : {args.window}")
    print(f"Thresholds: borderline>={args.borderline}  anomalous>={args.anomalous}\n")

    # ── Scan ──────────────────────────────────────────────────────────────────
    pattern = f"metricade_sess:{args.org}:*"
    print(f"Scanning {pattern} ...")
    t0 = time.time()
    keys = scan_keys(pattern)
    print(f"Found {len(keys):,} session keys  ({time.time()-t0:.1f}s)\n")

    if not keys:
        print("No sessions found."); sys.exit(1)

    # ── Fetch ─────────────────────────────────────────────────────────────────
    print(f"Fetching all sessions (parallel, {NUM_WORKERS} workers, batch={BATCH_SIZE}) ...")
    t1 = time.time()
    raw_map = fetch_all_parallel([f"metricade_sess:{args.org}:{k.split(':')[-1]}" for k in keys])
    print(f"Fetch complete  ({time.time()-t1:.1f}s)\n")

    # ── Process ───────────────────────────────────────────────────────────────
    print("Running RRCF ...")
    t2 = time.time()

    rows = []
    skipped = 0
    for i, (redis_key, raw) in enumerate(raw_map.items()):
        session_id = redis_key.split(":")[-1]

        if raw is None:
            skipped += 1
            rows.append((session_id, None, None, 0, 0, "insufficient_data"))
            continue

        try:
            events = json.loads(raw)
        except Exception:
            skipped += 1
            rows.append((session_id, None, None, 0, 0, "insufficient_data"))
            continue

        series = extract_scroll_series(events)
        n_scroll = sum(1 for e in events if e.get("event_type") == "scroll")
        n_events = len(events)

        if series is None:
            rows.append((session_id, None, None, n_events, n_scroll, "insufficient_data"))
            skipped += 1
            continue

        mean_s, max_s = score_session(series, args.trees, args.window)
        v = verdict(mean_s, args.borderline, args.anomalous)
        rows.append((session_id, mean_s, max_s, n_events, n_scroll, v))

        if (i + 1) % 500 == 0:
            print(f"\r  Scored {i+1:,}/{len(raw_map):,}", end="", flush=True)

    print(f"\r  Scored {len(raw_map):,}/{len(raw_map):,}  ({time.time()-t2:.1f}s)\n")

    # ── Stats ─────────────────────────────────────────────────────────────────
    scored = [r for r in rows if r[1] is not None]
    counts = defaultdict(int)
    for r in rows:
        counts[r[5]] += 1

    if scored:
        scores = [r[1] for r in scored]
        import statistics
        print(f"Score distribution:")
        print(f"  Min    : {min(scores):.2f}")
        print(f"  Median : {statistics.median(scores):.2f}")
        print(f"  Mean   : {statistics.mean(scores):.2f}")
        print(f"  Max    : {max(scores):.2f}")

    print(f"\nVerdicts:")
    total = len(rows)
    for v in ["ANOMALOUS", "borderline", "normal", "insufficient_data"]:
        n = counts[v]
        print(f"  {v:<22} {n:>6}  ({100*n/total:.1f}%)")

    # ── CSV ───────────────────────────────────────────────────────────────────
    csv_path = OUT_DIR / f"scores_{args.org}_full.csv"
    with open(csv_path, "w") as f:
        f.write("session_id,rrcf_score,max_evt_score,n_events,n_scroll,verdict\n")
        for sid, mean_s, max_s, n_ev, n_sc, v in sorted(rows, key=lambda x: (x[1] or -1), reverse=True):
            f.write(f"{sid},{mean_s},{max_s},{n_ev},{n_sc},{v}\n")
    print(f"\nCSV saved: {csv_path}")

    # ── Top 20 most anomalous ─────────────────────────────────────────────────
    top = sorted(scored, key=lambda x: x[1], reverse=True)[:20]
    print(f"\nTop 20 most anomalous:")
    print(f"  {'session_id':<38} {'score':>8}  {'scrolls':>8}  {'max_evt':>8}")
    print(f"  {'-'*70}")
    for sid, mean_s, max_s, n_ev, n_sc, v in top:
        print(f"  {sid:<38} {mean_s:>8.2f}  {n_sc:>8}  {max_s:>8.2f}")

    # ── Plot ──────────────────────────────────────────────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle(f"RRCF Session Anomaly Scores — {args.org} (n={total:,})", fontweight="bold")

    scores_only = [r[1] for r in scored]
    axes[0].hist(scores_only, bins=50, color="#4c78a8", edgecolor="none")
    axes[0].axvline(args.borderline, color="orange", linestyle="--", label=f"borderline ({args.borderline})")
    axes[0].axvline(args.anomalous,  color="red",    linestyle="--", label=f"anomalous ({args.anomalous})")
    axes[0].set_xlabel("RRCF score (higher = more anomalous)")
    axes[0].set_ylabel("Sessions")
    axes[0].set_title("Score distribution")
    axes[0].legend()

    verdict_labels = ["ANOMALOUS", "borderline", "normal", "insufficient_data"]
    verdict_colors = ["#e45756", "#f58518", "#54a24b", "#bab0ac"]
    verdict_counts = [counts[v] for v in verdict_labels]
    bars = axes[1].bar(verdict_labels, verdict_counts, color=verdict_colors)
    for bar, cnt in zip(bars, verdict_counts):
        axes[1].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 5,
                     str(cnt), ha="center", va="bottom", fontsize=10)
    axes[1].set_ylabel("Sessions")
    axes[1].set_title("Session verdicts")

    plt.tight_layout()
    plot_path = OUT_DIR / f"plot_{args.org}_full.png"
    plt.savefig(plot_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Plot saved: {plot_path}")

    total_time = time.time() - t0
    print(f"\nTotal time: {total_time:.1f}s  ({total_time/60:.1f} min)")
    print("Done.")


if __name__ == "__main__":
    main()