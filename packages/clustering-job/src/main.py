"""
Clustering job entry point.
Fetch all vectors → cluster → assign labels → write back to Vector metadata → report stats.
"""
import logging
import time

from .fetcher import fetch_all_vectors
from .clusterer import cluster_vectors
from .labeler import assign_labels
from .writer import write_cluster_labels
from .reporter import write_stats

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main():
    t0 = time.time()
    logger.info("Clustering job started")

    vectors, ids, metadata = fetch_all_vectors()
    logger.info("Fetched %d vectors", len(vectors))

    if len(vectors) < 10:
        logger.warning("Too few vectors (%d) for meaningful clustering — skipping", len(vectors))
        return

    labels = cluster_vectors(vectors)
    logger.info("Clustering complete — %d unique clusters", len(set(l for l in labels if l >= 0)))

    cluster_labels = assign_labels(vectors, labels, metadata)
    logger.info("Labels assigned: %s", dict(zip(*zip(*[(l, c) for l, c in cluster_labels.items()][:5]))))

    write_cluster_labels(ids, labels, cluster_labels)
    logger.info("Cluster labels written back to vector store")

    elapsed = time.time() - t0
    write_stats(labels, cluster_labels, elapsed)
    logger.info("Stats written — run complete in %.1fs", elapsed)


if __name__ == "__main__":
    main()
