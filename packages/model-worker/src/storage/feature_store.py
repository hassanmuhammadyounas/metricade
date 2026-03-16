"""
Loads featurized session tensors from Redis (npz bytes).
Key: metricade_features:{org_id}:{session_id}

Serialization format: numpy npz
  - "cont": float32 [256, N_CONT]
  - "cat":  int64   [N_CAT]
"""
import io
import base64
import logging
import numpy as np
import redis as redis_lib

logger = logging.getLogger(__name__)


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
    npz_bytes = base64.b64decode(raw) if isinstance(raw, (str, bytes)) else raw
    buf = io.BytesIO(npz_bytes)
    data = np.load(buf)
    cont = torch.from_numpy(data["cont"].astype(np.float32))
    cat = torch.from_numpy(data["cat"].astype(np.int64))
    assert cont.shape == (MAX_SEQ_LEN, N_CONT), f"cont shape mismatch: {cont.shape}"
    assert cat.shape == (N_CAT,), f"cat shape mismatch: {cat.shape}"
    return cont, cat
