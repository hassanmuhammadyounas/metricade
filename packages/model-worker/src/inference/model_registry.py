"""
Per-org model registry. Loads and caches BehavioralTransformer instances per org_id.
Model file resolution order:
  1. {MODELS_DIR}/{org_id}.pt          — org-specific trained weights
  2. {MODELS_DIR}/bootstrap_random.pt  — shared bootstrap (random init, validates architecture)
  3. Random initialization              — if no files exist at all

Models are cached in memory after first load. Cache is never evicted during runtime.
"""
import os
import logging
import torch

from .transformer import BehavioralTransformer
from ..constants import MODELS_DIR, VECTOR_DIMS, MAX_SEQ_LEN, N_CONT, N_CAT

logger = logging.getLogger(__name__)

_model_cache: dict[str, BehavioralTransformer] = {}


def get_model(org_id: str) -> BehavioralTransformer:
    """Return cached model for org_id. Load from disk if not cached."""
    if org_id in _model_cache:
        return _model_cache[org_id]
    model = _load_model_for_org(org_id)
    _model_cache[org_id] = model
    return model


def _load_model_for_org(org_id: str) -> BehavioralTransformer:
    model = BehavioralTransformer()

    org_model_path = os.path.join(MODELS_DIR, f"{org_id}.pt")
    bootstrap_path = os.path.join(MODELS_DIR, "bootstrap_random.pt")

    if os.path.exists(org_model_path):
        logger.info("[%s] Loading org-specific model from %s", org_id, org_model_path)
        state_dict = torch.load(org_model_path, map_location="cpu", weights_only=True)
        model.load_state_dict(state_dict)
    elif os.path.exists(bootstrap_path):
        logger.warning("[%s] No org model found — loading bootstrap weights", org_id)
        state_dict = torch.load(bootstrap_path, map_location="cpu", weights_only=True)
        model.load_state_dict(state_dict)
    else:
        logger.warning("[%s] No model weights found anywhere — using random init", org_id)

    model.eval()
    with torch.no_grad():
        dummy_cont = torch.zeros(1, MAX_SEQ_LEN, N_CONT)
        dummy_cat = torch.zeros(1, N_CAT, dtype=torch.int64)
        out = model(dummy_cont, dummy_cat)
        assert out.shape == (1, VECTOR_DIMS), \
            f"[{org_id}] Model output dim mismatch: expected {VECTOR_DIMS}, got {out.shape[1]}"

    logger.info("[%s] Model ready — output dim validated at %d", org_id, VECTOR_DIMS)
    return model


def invalidate_cache(org_id: str) -> None:
    """Force reload of org model on next request."""
    if org_id in _model_cache:
        del _model_cache[org_id]
        logger.info("[%s] Model cache invalidated", org_id)
