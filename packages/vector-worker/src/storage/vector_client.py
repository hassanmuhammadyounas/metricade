"""
Upstash Vector upsert + spot-check fetch (1-in-100).
"""
import os
import random
import logging
from upstash_vector import Index

from ..constants import SPOT_CHECK_RATE, VECTOR_DIMS

logger = logging.getLogger(__name__)

_index: Index | None = None


def _get_index() -> Index:
    global _index
    if _index is None:
        _index = Index(
            url=os.environ["UPSTASH_VECTOR_URL"],
            token=os.environ["UPSTASH_VECTOR_TOKEN"],
        )
    return _index


def upsert_vector(vector_id: str, vector: list[float], metadata: dict) -> None:
    assert len(vector) == VECTOR_DIMS, f"Vector dim mismatch: {len(vector)} != {VECTOR_DIMS}"

    index = _get_index()
    index.upsert(vectors=[(vector_id, vector, metadata)])

    # Spot-check: verify 1 in 100 upserts actually persisted
    if random.random() < SPOT_CHECK_RATE:
        result = index.fetch(ids=[vector_id])
        if not result or result[0] is None:
            logger.error("Spot-check FAILED for vector %s — upsert may not have persisted", vector_id)
        else:
            logger.debug("Spot-check OK for vector %s", vector_id)
