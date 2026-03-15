"""
Load .pt weights from /models/, validate output dimension is 192.
Falls back to bootstrap_random.pt if trained model is not found.
"""
import os
import logging
import torch

from .transformer import BehavioralTransformer
from ..constants import MODEL_PATH, BOOTSTRAP_MODEL_PATH, VECTOR_DIMS

logger = logging.getLogger(__name__)


def load_model() -> BehavioralTransformer:
    model = BehavioralTransformer()

    if os.path.exists(MODEL_PATH):
        logger.info("Loading trained model from %s", MODEL_PATH)
        state_dict = torch.load(MODEL_PATH, map_location="cpu", weights_only=True)
        model.load_state_dict(state_dict)
    elif os.path.exists(BOOTSTRAP_MODEL_PATH):
        logger.warning(
            "Trained model not found at %s — loading bootstrap random weights from %s",
            MODEL_PATH, BOOTSTRAP_MODEL_PATH,
        )
        state_dict = torch.load(BOOTSTRAP_MODEL_PATH, map_location="cpu", weights_only=True)
        model.load_state_dict(state_dict)
    else:
        logger.warning("No model weights found — using random initialization (bootstrap phase)")

    # Validate output dimension
    model.eval()
    with torch.no_grad():
        from .featurizer import N_CONT, N_CAT, MAX_SEQ_LEN
        dummy_cont = torch.zeros(1, MAX_SEQ_LEN, N_CONT)
        dummy_cat  = torch.zeros(1, N_CAT, dtype=torch.int64)
        out = model(dummy_cont, dummy_cat)
        assert out.shape == (1, VECTOR_DIMS), f"Model output dim mismatch: expected {VECTOR_DIMS}, got {out.shape[1]}"

    logger.info("Model loaded — output dim validated at %d", VECTOR_DIMS)
    return model
