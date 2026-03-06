"""
Rule-based label assignment based on cluster behavioral profile.
Labels: FRAUD_BOT, HIGH_INTENT, MEDIUM_INTENT, LOW_INTENT, UNASSIGNED
"""
import numpy as np
from typing import Any

LABELS = {
    "FRAUD_BOT": "FRAUD_BOT",
    "HIGH_INTENT": "HIGH_INTENT",
    "MEDIUM_INTENT": "MEDIUM_INTENT",
    "LOW_INTENT": "LOW_INTENT",
    "UNASSIGNED": "UNASSIGNED",
}

# Feature indices within the 51-feature vector (must match featurizer.py)
FEAT_SCROLL_VELOCITY = 8    # scroll_velocity_px_s (normalized)
FEAT_Y_REVERSAL = 10        # y_reversal (0 or 1)
FEAT_DELTA_MS = 7           # delta_ms (normalized)
FEAT_SCROLL_DEPTH = 11      # scroll_depth_pct (normalized)


def assign_labels(
    vectors: np.ndarray,
    labels: np.ndarray,
    metadata: list[dict[str, Any]],
) -> dict[int, str]:
    """
    For each cluster ID, compute mean raw features and apply rule thresholds.
    Returns mapping of cluster_id → label string.
    """
    unique_clusters = set(labels)
    cluster_label_map: dict[int, str] = {}

    for cluster_id in unique_clusters:
        if cluster_id == -1:
            cluster_label_map[-1] = LABELS["UNASSIGNED"]
            continue

        mask = labels == cluster_id
        cluster_vectors = vectors[mask]
        profile = cluster_vectors.mean(axis=0)

        cluster_label_map[cluster_id] = _apply_rules(profile)

    return cluster_label_map


def _apply_rules(profile: np.ndarray) -> str:
    """
    Rule thresholds derived from behavioral biometrics research.
    Velocity > 180 px/s and zero reversals → FRAUD_BOT.
    """
    velocity = profile[FEAT_SCROLL_VELOCITY] * 1000  # undo normalization
    reversal_rate = profile[FEAT_Y_REVERSAL]
    delta_variance = profile[FEAT_DELTA_MS]
    depth = profile[FEAT_SCROLL_DEPTH] * 100  # undo normalization

    # FRAUD_BOT: constant high velocity, zero reversals, machine-precise timing
    if velocity > 180 and reversal_rate < 0.02:
        return LABELS["FRAUD_BOT"]

    # HIGH_INTENT: deep scroll, high engagement, natural timing variance
    if depth > 60 and reversal_rate > 0.05:
        return LABELS["HIGH_INTENT"]

    # MEDIUM_INTENT: moderate depth, some engagement
    if depth > 30:
        return LABELS["MEDIUM_INTENT"]

    return LABELS["LOW_INTENT"]
