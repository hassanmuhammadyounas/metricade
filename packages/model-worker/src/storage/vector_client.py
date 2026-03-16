"""
Vector upsert + spot-check fetch (1-in-100).
Backend: Qdrant (local) if QDRANT_URL is set, else Upstash Vector.
"""
import os
import random
import logging

from ..constants import SPOT_CHECK_RATE, VECTOR_DIMS

logger = logging.getLogger(__name__)

_COLLECTION = "sessions"

# ── Qdrant backend ────────────────────────────────────────────────────────────

_qdrant_client = None


def _get_qdrant():
    global _qdrant_client
    if _qdrant_client is None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams
        url = os.environ["QDRANT_URL"]
        _qdrant_client = QdrantClient(url=url)
        # Create collection if it doesn't exist
        existing = [c.name for c in _qdrant_client.get_collections().collections]
        if _COLLECTION not in existing:
            _qdrant_client.create_collection(
                collection_name=_COLLECTION,
                vectors_config=VectorParams(size=VECTOR_DIMS, distance=Distance.COSINE),
            )
            logger.info("Created Qdrant collection '%s' (dim=%d, cosine)", _COLLECTION, VECTOR_DIMS)
    return _qdrant_client


def _upsert_qdrant(vector_id: str, vector: list[float], metadata: dict) -> None:
    from qdrant_client.models import PointStruct
    client = _get_qdrant()
    client.upsert(
        collection_name=_COLLECTION,
        points=[PointStruct(id=_qdrant_id(vector_id), vector=vector, payload={"vector_id": vector_id, **metadata})],
    )
    if random.random() < SPOT_CHECK_RATE:
        result = client.retrieve(collection_name=_COLLECTION, ids=[_qdrant_id(vector_id)])
        if not result:
            logger.error("Spot-check FAILED for vector %s", vector_id)
        else:
            logger.debug("Spot-check OK for vector %s", vector_id)


def _qdrant_id(vector_id: str) -> str:
    """Qdrant requires UUID or unsigned int as point ID — hash the session_id."""
    import hashlib, uuid
    return str(uuid.UUID(hashlib.md5(vector_id.encode()).hexdigest()))


# ── Upstash Vector backend ────────────────────────────────────────────────────

_upstash_index = None


def _get_upstash():
    global _upstash_index
    if _upstash_index is None:
        from upstash_vector import Index
        _upstash_index = Index(
            url=os.environ["UPSTASH_VECTOR_URL"],
            token=os.environ["UPSTASH_VECTOR_TOKEN"],
        )
    return _upstash_index


def _upsert_upstash(vector_id: str, vector: list[float], metadata: dict) -> None:
    index = _get_upstash()
    index.upsert(vectors=[(vector_id, vector, metadata)])
    if random.random() < SPOT_CHECK_RATE:
        result = index.fetch(ids=[vector_id])
        if not result or result[0] is None:
            logger.error("Spot-check FAILED for vector %s", vector_id)
        else:
            logger.debug("Spot-check OK for vector %s", vector_id)


# ── Public API ────────────────────────────────────────────────────────────────

def upsert_vector(vector_id: str, vector: list[float], metadata: dict) -> None:
    assert len(vector) == VECTOR_DIMS, f"Vector dim mismatch: {len(vector)} != {VECTOR_DIMS}"
    if os.environ.get("QDRANT_URL"):
        _upsert_qdrant(vector_id, vector, metadata)
    else:
        _upsert_upstash(vector_id, vector, metadata)
