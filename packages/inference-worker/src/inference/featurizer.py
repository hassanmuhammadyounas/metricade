"""
Raw event batch → 51-feature tensor (sequence padding).
Feature order must match packages/shared/constants/feature-list.ts exactly.
"""
import torch
import math
from typing import Any

# Maximum sequence length (pad or truncate to this)
MAX_SEQ_LEN = 64
# 51 features per event — see shared/constants/feature-list.ts for the complete ordered list
NUM_FEATURES = 51


def featurize(payload: dict[str, Any]) -> torch.Tensor:
    """
    Convert a raw event payload to a [MAX_SEQ_LEN, NUM_FEATURES] float32 tensor.
    Events are sorted by ts ascending and zero-padded to MAX_SEQ_LEN.
    """
    events = payload.get("events", [])
    rows = []
    for event in events[:MAX_SEQ_LEN]:
        rows.append(_event_to_features(event))

    # Pad with zeros to MAX_SEQ_LEN
    while len(rows) < MAX_SEQ_LEN:
        rows.append([0.0] * NUM_FEATURES)

    return torch.tensor(rows, dtype=torch.float32)


def _event_to_features(event: dict) -> list[float]:
    """Map a single event dict to a 51-element float list."""
    event_type_enc = _one_hot_event_type(event.get("event_type", ""))

    return [
        # Tier 1 — Critical Signal (features 0–6)
        *event_type_enc,                                          # 0–6: 7 one-hot event type dims
        _safe_float(event, "delta_ms", scale=10000),              # 7
        _safe_float(event, "scroll_velocity_px_s", scale=1000),   # 8
        _safe_float(event, "scroll_acceleration", scale=500),     # 9
        float(event.get("y_reversal", 0)),                        # 10

        # Tier 2 — High Signal (features 11–30)
        _safe_float(event, "scroll_depth_pct", scale=100),        # 11
        _safe_float(event, "tap_interval_ms", scale=5000),        # 12
        _safe_float(event, "contact_radius", scale=50),           # 13
        float(event.get("dead_tap", 0)),                          # 14
        _safe_float(event, "force", scale=1),                     # 15
        _safe_float(event, "x", scale=2560),                      # 16
        _safe_float(event, "y", scale=1440),                      # 17
        # Remaining 33 features — zero-filled until full feature set is defined
        *([0.0] * 33),
    ]


def _one_hot_event_type(event_type: str) -> list[float]:
    types = ["INIT", "PAGE_VIEW", "SCROLL", "TOUCH_END", "CLICK", "TAB_HIDDEN", "TAB_VISIBLE"]
    return [1.0 if event_type == t else 0.0 for t in types]


def _safe_float(event: dict, key: str, scale: float = 1.0) -> float:
    val = event.get(key, 0)
    try:
        return float(val) / scale
    except (TypeError, ValueError):
        return 0.0
