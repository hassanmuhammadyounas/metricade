"""
HDBSCAN clustering config, noise handling, min_cluster_size tuning.
"""
import numpy as np
import hdbscan


def cluster_vectors(
    vectors: np.ndarray,
    min_cluster_size: int = 15,
    min_samples: int = 5,
    metric: str = "euclidean",
) -> np.ndarray:
    """
    Cluster vectors using HDBSCAN.
    Returns integer label array — label -1 means noise (unassigned).

    min_cluster_size tuning:
    - Too small → many micro-clusters, noisy labels
    - Too large → everything becomes noise
    - 15 is a good starting point for behavioral cohorts

    We use euclidean on already L2-normalized vectors.
    Euclidean distance on unit vectors is monotonically related to cosine distance,
    so cluster geometry is preserved.
    """
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric=metric,
        core_dist_n_jobs=-1,
    )
    labels = clusterer.fit_predict(vectors)
    return labels
