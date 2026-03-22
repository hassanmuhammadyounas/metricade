"""
Analyzes event type combinations across ANOMALOUS / borderline / normal / insufficient_data sessions.
Reads session IDs from RRCF CSV, fetches raw events from Redis, prints summary.

Usage:
    python analyze_session_events.py \
        --csv scripts/output/rrcf/session_scores_org_3bq2jCKKsVv6.csv \
        --org org_3bq2jCKKsVv6 \
        --n 10
"""

import argparse
import json
import os
import random
from collections import Counter
from pathlib import Path

import httpx

# ── Load .env ─────────────────────────────────────────────────────────────────
_env = Path(__file__).resolve().parent / ".env"
if not _env.exists():
    _env = Path(__file__).resolve().parent.parent / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

REDIS_URL   = os.environ.get("UPSTASH_REDIS_URL", "").rstrip("/")
REDIS_TOKEN = os.environ.get("UPSTASH_REDIS_TOKEN", "")

http = httpx.Client(timeout=30)

CATEGORIES = ["ANOMALOUS", "borderline", "normal", "insufficient_data"]

EVENT_ORDER = [
    "page_view", "route_change", "scroll", "touch_end", "click",
    "tab_hidden", "tab_visible", "engagement_tick", "idle",
]


# ── Redis ─────────────────────────────────────────────────────────────────────
def redis_batch_get(keys: list[str]) -> list[str | None]:
    results = []
    batch = 50
    for i in range(0, len(keys), batch):
        cmds = [["GET", k] for k in keys[i:i+batch]]
        r = http.post(f"{REDIS_URL}/pipeline",
                      headers={"Authorization": f"Bearer {REDIS_TOKEN}"},
                      json=cmds)
        r.raise_for_status()
        results.extend(x["result"] for x in r.json())
    return results


# ── CSV parsing ───────────────────────────────────────────────────────────────
def load_csv(path: str) -> dict[str, list[str]]:
    """Returns {verdict: [session_id, ...]}"""
    buckets: dict[str, list[str]] = {c: [] for c in CATEGORIES}
    with open(path) as f:
        header = f.readline()
        for line in f:
            parts = line.strip().split(",")
            if len(parts) < 6:
                continue
            sid, _, _, _, _, verdict = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]
            verdict = verdict.strip()
            if verdict in buckets:
                buckets[verdict].append(sid)
    return buckets


# ── Analysis ──────────────────────────────────────────────────────────────────
def analyze_events(events: list[dict]) -> dict:
    type_counts = Counter(e.get("event_type", "unknown") for e in events)
    total = len(events)
    scroll_count = type_counts.get("scroll", 0)
    return {
        "total_events":       total,
        "unique_event_types": len(type_counts),
        "scroll_pct":         round(100 * scroll_count / total, 1) if total else 0,
        "counts":             dict(type_counts),
        "y_reversals":        sum(e.get("y_reversal", 0) for e in events if e.get("event_type") == "scroll"),
        "clicks":             type_counts.get("click", 0) + type_counts.get("touch_end", 0),
        "engagement_ticks":   type_counts.get("engagement_tick", 0),
        "pages":              max((e.get("page_load_index", 1) for e in events), default=1),
        "scroll_direction_up": sum(1 for e in events if e.get("event_type") == "scroll" and e.get("scroll_direction", 0) == -1),
    }


def print_session(sid: str, events: list[dict], analysis: dict, rank: int):
    print(f"  [{rank}] {sid[:8]}...  events={analysis['total_events']}  scroll%={analysis['scroll_pct']}%  pages={analysis['pages']}")
    # Event type breakdown
    counts = analysis["counts"]
    line_parts = []
    for et in EVENT_ORDER:
        if et in counts:
            line_parts.append(f"{et}:{counts[et]}")
    others = {k: v for k, v in counts.items() if k not in EVENT_ORDER}
    for k, v in others.items():
        line_parts.append(f"{k}:{v}")
    print(f"      {' | '.join(line_parts)}")
    print(f"      clicks/touch={analysis['clicks']}  eng_ticks={analysis['engagement_ticks']}  y_reversals={analysis['y_reversals']}  scroll_up={analysis['scroll_direction_up']}")


def print_category_summary(label: str, all_analyses: list[dict]):
    if not all_analyses:
        return
    avg_total   = round(sum(a["total_events"] for a in all_analyses) / len(all_analyses), 1)
    avg_scroll  = round(sum(a["scroll_pct"] for a in all_analyses) / len(all_analyses), 1)
    avg_clicks  = round(sum(a["clicks"] for a in all_analyses) / len(all_analyses), 1)
    avg_ticks   = round(sum(a["engagement_ticks"] for a in all_analyses) / len(all_analyses), 1)
    avg_rev     = round(sum(a["y_reversals"] for a in all_analyses) / len(all_analyses), 1)
    avg_pages   = round(sum(a["pages"] for a in all_analyses) / len(all_analyses), 1)
    print(f"  ── AVERAGES: events={avg_total}  scroll%={avg_scroll}%  clicks/touch={avg_clicks}  eng_ticks={avg_ticks}  y_reversals={avg_rev}  pages={avg_pages}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv",  required=True, help="Path to RRCF scores CSV")
    parser.add_argument("--org",  required=True, help="org_id")
    parser.add_argument("--n",    type=int, default=10, help="Sessions per category")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)

    if not REDIS_URL:
        print("ERROR: UPSTASH_REDIS_URL not set"); return

    print(f"\nLoading CSV: {args.csv}")
    buckets = load_csv(args.csv)
    for cat, ids in buckets.items():
        print(f"  {cat}: {len(ids)} sessions")

    for category in CATEGORIES:
        ids = buckets[category]
        if not ids:
            print(f"\n{'='*70}")
            print(f"  {category.upper()} — no sessions found")
            continue

        sample = random.sample(ids, min(args.n, len(ids)))

        print(f"\n{'='*70}")
        print(f"  {category.upper()} — {len(sample)} sessions sampled")
        print(f"{'='*70}")

        redis_keys = [f"metricade_sess:{args.org}:{sid}" for sid in sample]
        raw_values = redis_batch_get(redis_keys)

        all_analyses = []
        for rank, (sid, raw) in enumerate(zip(sample, raw_values), 1):
            if raw is None:
                print(f"  [{rank}] {sid[:8]}...  [NOT FOUND IN REDIS]")
                continue
            try:
                events = json.loads(raw)
            except Exception as e:
                print(f"  [{rank}] {sid[:8]}...  [PARSE ERROR: {e}]")
                continue

            if not events:
                print(f"  [{rank}] {sid[:8]}...  [EMPTY]")
                continue

            analysis = analyze_events(events)
            print_session(sid, events, analysis, rank)
            all_analyses.append(analysis)

        print()
        print_category_summary(category, all_analyses)

    print("\nDone.")


if __name__ == "__main__":
    main()