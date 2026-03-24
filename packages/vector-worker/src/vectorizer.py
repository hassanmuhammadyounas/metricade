"""
H-GRU inference: load model, encode a session, return 64-dim vector.
Runs on GPU if available, otherwise CPU.
"""
from pathlib import Path

import torch
import torch.nn.functional as F

from .features import build_session_tensors
from .model import HierarchicalGRUEncoder

_DEFAULT_WEIGHTS = Path(__file__).parent.parent / 'models' / 'hgru.pt'


def load_model(
    weights_path: str | Path | None = None,
    device: torch.device | None = None,
) -> tuple[HierarchicalGRUEncoder, torch.device]:
    """
    Load H-GRU encoder. Returns (model, device).
    Falls back to random init if weights file is missing.
    """
    if device is None:
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    path = Path(weights_path) if weights_path else _DEFAULT_WEIGHTS

    model = HierarchicalGRUEncoder(
        event_hidden   = 64,
        session_hidden = 64,
        embed_dim      = 64,
    )

    if path.exists():
        state = torch.load(path, map_location='cpu', weights_only=True)
        model.load_state_dict(state)
        print(f'[vectorizer] Loaded weights from {path}')
    else:
        print(f'[vectorizer] WARNING: {path} not found — using random init. '
              f'Run scripts/bootstrap_hgru.py to generate bootstrap weights.')

    model = model.to(device)
    model.eval()
    print(f'[vectorizer] Device: {device}')
    return model, device


@torch.no_grad()
def encode_session(
    events: list[dict],
    robust: dict,
    model:  HierarchicalGRUEncoder,
    device: torch.device,
) -> list[float] | None:
    """
    Encode a session into a 64-dim L2-normalised vector.
    Returns list of 64 floats, or None if events is empty.
    """
    result = build_session_tensors(events, robust)
    if result is None:
        return None

    pages_data, session_ctx = result

    # Move tensors to device
    pages_data  = [(e.to(device), p.to(device)) for e, p in pages_data]
    session_ctx = session_ctx.to(device)

    vec = model(pages_data, session_ctx)        # (64,) raw
    vec = F.normalize(vec, dim=-1)              # L2-normalise for storage
    return vec.cpu().tolist()
