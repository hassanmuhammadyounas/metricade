"""
Write cluster stats to Redis (sizes, label counts, run time).
"""
import os
import json
import time
import logging
import numpy as np
import redis

logger = logging.getLogger(__name__)
STATS_KEY = "clustering_last_run_stats"


def write_stats(
    labels: np.ndarray,
    cluster_label_map: dict[int, str],
    elapsed_s: float,
) -> None:
    unique, counts = np.unique(labels, return_counts=True)
    cluster_sizes = {int(k): int(v) for k, v in zip(unique, counts)}

    label_counts: dict[str, int] = {}
    for cluster_id, count in cluster_sizes.items():
        label = cluster_label_map.get(cluster_id, "UNASSIGNED")
        label_counts[label] = label_counts.get(label, 0) + count

    stats = {
        "run_at": int(time.time() * 1000),
        "total_vectors": int(labels.size),
        "num_clusters": int((unique >= 0).sum()),
        "noise_count": int(cluster_sizes.get(-1, 0)),
        "label_counts": label_counts,
        "cluster_sizes": {str(k): v for k, v in cluster_sizes.items() if k >= 0},
        "elapsed_s": round(elapsed_s, 2),
    }

    r = redis.from_url(
        os.environ["UPSTASH_REDIS_URL"],
        password=os.environ["UPSTASH_REDIS_TOKEN"],
    )
    r.set(STATS_KEY, json.dumps(stats))
    logger.info("Stats written to Redis key %s", STATS_KEY)
