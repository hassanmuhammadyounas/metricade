"""
Fetch all vectors from Upstash Vector → numpy array.
"""
import os
import numpy as np
from upstash_vector import Index


def fetch_all_vectors() -> tuple[np.ndarray, list[str], list[dict]]:
    """Returns (vectors_array, ids, metadata_list)."""
    index = Index(
        url=os.environ["UPSTASH_VECTOR_URL"],
        token=os.environ["UPSTASH_VECTOR_TOKEN"],
    )

    all_vectors = []
    all_ids = []
    all_metadata = []

    # Upstash Vector range with cursor-based pagination
    cursor = ""
    while True:
        result = index.range(cursor=cursor, limit=1000, include_vectors=True, include_metadata=True)
        for item in result.vectors:
            all_ids.append(item.id)
            all_vectors.append(item.vector)
            all_metadata.append(item.metadata or {})
        if not result.next_cursor:
            break
        cursor = result.next_cursor

    return np.array(all_vectors, dtype=np.float32), all_ids, all_metadata
