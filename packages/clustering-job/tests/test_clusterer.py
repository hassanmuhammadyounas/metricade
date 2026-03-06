import numpy as np
import pytest
from src.clusterer import cluster_vectors


def make_tight_cluster(center, n=30, noise=0.01):
    """Generate n vectors tightly around a given center."""
    return center + np.random.randn(n, len(center)) * noise


def test_two_distinct_clusters_are_separated():
    """Known well-separated vectors should produce at least 2 distinct clusters."""
    np.random.seed(42)
    center_a = np.array([1.0, 0.0] * 96, dtype=np.float32)
    center_b = np.array([0.0, 1.0] * 96, dtype=np.float32)
    vectors = np.vstack([
        make_tight_cluster(center_a, n=30),
        make_tight_cluster(center_b, n=30),
    ]).astype(np.float32)

    labels = cluster_vectors(vectors, min_cluster_size=5)
    unique = set(l for l in labels if l >= 0)
    assert len(unique) >= 2


def test_noise_points_labeled_minus_one():
    """Isolated outlier points should be labeled -1."""
    np.random.seed(0)
    # One tight cluster + 3 far outliers
    cluster = make_tight_cluster(np.zeros(192, dtype=np.float32), n=20)
    outliers = np.random.randn(3, 192).astype(np.float32) * 10
    vectors = np.vstack([cluster, outliers]).astype(np.float32)

    labels = cluster_vectors(vectors, min_cluster_size=10, min_samples=5)
    assert -1 in labels
