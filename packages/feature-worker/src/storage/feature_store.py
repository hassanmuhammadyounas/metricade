"""
Stores featurized session tensors in Redis as npz bytes.
Key: metricade_features:{org_id}:{session_id}  TTL: 24h
Also publishes a lightweight pointer to metricade_features_stream:{org_id} for model worker consumption.

Serialization format: numpy npz
  - "cont": float32 [256, N_CONT]
  - "cat":  int64   [N_CAT]
"""
import io
import logging
import numpy as np
import redis as redis_lib

from ..constants import FEATURE_STORE_KEY_PREFIX, FEATURES_STREAM_NAME, FEATURE_TTL_SECONDS

logger = logging.getLogger(__name__)


def store_features(
    r: redis_lib.Redis,
    org_id: str,
    session_id: str,
    cont,   # [256, N_CONT] float32 torch.Tensor
    cat,    # [N_CAT] int64 torch.Tensor
    metadata: dict,
) -> None:
    """
    Serialize tensors as npz, store in Redis, publish pointer to features stream.
    metadata: lightweight dict stored alongside the pointer in the stream
    """
    buf = io.BytesIO()
    np.savez_compressed(
        buf,
        cont=cont.numpy().astype(np.float32),
        cat=cat.numpy().astype(np.int64),
    )
    buf.seek(0)
    npz_bytes = buf.read()

    feature_key = f"{FEATURE_STORE_KEY_PREFIX}:{org_id}:{session_id}"
    r.setex(feature_key, FEATURE_TTL_SECONDS, npz_bytes)

    stream_key = f"{FEATURES_STREAM_NAME}:{org_id}"
    pointer = {
        "session_id": session_id,
        "org_id": org_id,
        "feature_key": feature_key,
    }
    for k, v in metadata.items():
        if v is not None:
            pointer[k] = str(v)

    r.xadd(stream_key, pointer)
    logger.debug("Stored features and published pointer for session %s org %s", session_id, org_id)


def load_features(r: redis_lib.Redis, feature_key: str):
    """
    Load npz bytes from Redis, return (cont_tensor, cat_tensor) or None if not found.
    Asserts shapes: cont [256, N_CONT], cat [N_CAT].
    """
    import torch
    from ..constants import MAX_SEQ_LEN, N_CONT, N_CAT
    raw = r.get(feature_key)
    if raw is None:
        return None
    buf = io.BytesIO(raw)
    data = np.load(buf)
    cont = torch.from_numpy(data["cont"].astype(np.float32))
    cat = torch.from_numpy(data["cat"].astype(np.int64))
    assert cont.shape == (MAX_SEQ_LEN, N_CONT), f"cont shape mismatch: {cont.shape}"
    assert cat.shape == (N_CAT,), f"cat shape mismatch: {cat.shape}"
    return cont, cat
