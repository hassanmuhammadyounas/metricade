"""
Update cluster_label metadata back to Vector for each session.
"""
import os
import logging
import numpy as np
from upstash_vector import Index
from upstash_vector.types import MetadataUpdateMode

logger = logging.getLogger(__name__)

BATCH_SIZE = 100


def write_cluster_labels(
    ids: list[str],
    labels: np.ndarray,
    cluster_label_map: dict[int, str],
) -> None:
    index = Index(
        url=os.environ["UPSTASH_VECTOR_URL"],
        token=os.environ["UPSTASH_VECTOR_TOKEN"],
    )

    # Update metadata in batches to avoid rate limits
    batch: list[tuple[str, dict]] = []
    for vector_id, label_id in zip(ids, labels):
        cluster_label = cluster_label_map.get(int(label_id), "UNASSIGNED")
        batch.append((vector_id, {"cluster_label": cluster_label, "cluster_id": int(label_id)}))

        if len(batch) >= BATCH_SIZE:
            _update_batch(index, batch)
            batch = []

    if batch:
        _update_batch(index, batch)


def _update_batch(index: Index, batch: list[tuple[str, dict]]) -> None:
    for vector_id, metadata in batch:
        try:
            index.update(
                id=vector_id,
                metadata=metadata,
                metadata_update_mode=MetadataUpdateMode.PATCH,
            )
        except Exception as e:
            logger.error("Metadata update failed for %s: %s", vector_id, e)
