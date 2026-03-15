"""
Raw event batch → 51-feature tensor (sequence padding).
Feature order is defined in _event_to_features() below.
"""
import torch
from typing import Any

# Maximum sequence length (pad or truncate to this)
MAX_SEQ_LEN = 64
# 53 features per event (9 one-hot event types + 44 behavioural features)
NUM_FEATURES = 53


def featurize(payload: dict[str, Any], enriched: dict[str, Any] | None = None) -> torch.Tensor:
    """
    Convert a raw event payload to a [MAX_SEQ_LEN, NUM_FEATURES] float32 tensor.
    Events are zero-padded to MAX_SEQ_LEN.
    enriched is the full wrapper written by the edge worker (ip_meta, ua_meta, time_features, etc.).
    """
    events = payload.get("events", [])
    session = _extract_session(payload, events, enriched or {})
    rows = []
    for event in events[:MAX_SEQ_LEN]:
        rows.append(_event_to_features(event, session))

    # Pad with zeros to MAX_SEQ_LEN
    while len(rows) < MAX_SEQ_LEN:
        rows.append([0.0] * NUM_FEATURES)

    return torch.tensor(rows, dtype=torch.float32)


def _djb2(s: str) -> float:
    """32-bit djb2 hash normalised to [0, 1]."""
    h = 5381
    for c in str(s):
        h = ((h << 5) + h + ord(c)) & 0xFFFFFFFF
    return h / 0xFFFFFFFF


def _parse_hash(val) -> float:
    """Parse a hash that may be an int or a hex string (pixel.js .toString(16)), normalised to [0, 1]."""
    if val is None:
        return 0.0
    try:
        if isinstance(val, int):
            return val / 0xFFFFFFFF
        return int(str(val), 16) / 0xFFFFFFFF
    except (ValueError, TypeError):
        return 0.0


def _extract_session(payload: dict, events: list, enriched: dict) -> dict:
    """Pre-scan payload and event list for session fields and merge with enriched wrapper.
    Reads session-level fields from payload first (new format), falls back to init event
    for backwards compatibility with old stream entries.
    """
    init = next((e for e in events if e.get("event_type") == "init"), {})
    ip = enriched.get("ip_meta") or {}
    ua = enriched.get("ua_meta") or {}
    tf = enriched.get("time_features") or {}

    def _pget(key, default=None):
        """Get from payload first, fall back to init event."""
        v = payload.get(key)
        return v if v is not None else init.get(key, default)

    return {
        "page_path_hash":     _parse_hash(init.get("page_path_hash")),
        "is_paid":            float(_pget("is_paid", 0)),
        "click_id_type":      _djb2(_pget("click_id_type", "none")),
        "device_pixel_ratio": min(float(_pget("device_pixel_ratio", 1.0)), 4.0) / 4.0,
        "viewport_w_norm":    float(_pget("viewport_w_norm", 0.0)),
        "viewport_h_norm":    float(_pget("viewport_h_norm", 0.0)),
        "is_webview":         float(ua.get("is_webview", False)),
        "is_touch":           1.0 if ua.get("device_type") in ("mobile", "tablet") else 0.0,
        "ip_type":            {"residential": 0.0, "datacenter": 1.0}.get(ip.get("ip_type", ""), 0.5),
        "ip_country":         _djb2(ip.get("ip_country", "unknown")),
        "browser_family":     _djb2(ua.get("browser_family", "unknown")),
        "os_family":          _djb2(ua.get("os_family", "unknown")),
        "hour_sin":           float(tf.get("hour_sin", 0.0)),
        "hour_cos":           float(tf.get("hour_cos", 0.0)),
        "dow_sin":            float(tf.get("dow_sin", 0.0)),
        "dow_cos":            float(tf.get("dow_cos", 0.0)),
        "is_weekend":         float(tf.get("is_weekend", 0)),
        "timezone_mismatch":  float(enriched.get("timezone_mismatch", False)),
    }


def _event_to_features(event: dict, session: dict) -> list[float]:
    """Map a single event dict to a 51-element float list."""
    event_type_enc = _one_hot_event_type(event.get("event_type", ""))

    # Features 31–33: use per-event value if present (init event), otherwise fall back to session
    dpr = (
        _safe_float(event, "device_pixel_ratio", scale=4.0)
        if event.get("device_pixel_ratio") is not None
        else session["device_pixel_ratio"]
    )
    vp_w = (
        _safe_float(event, "viewport_w_norm")
        if event.get("viewport_w_norm") is not None
        else session["viewport_w_norm"]
    )
    vp_h = (
        _safe_float(event, "viewport_h_norm")
        if event.get("viewport_h_norm") is not None
        else session["viewport_h_norm"]
    )

    return [
        # Tier 1 — Critical Signal (features 0–10)
        *event_type_enc,                                                  # 0–6: 7 one-hot event type dims
        _safe_float(event, "delta_ms", scale=10000),                      # 7
        _safe_float(event, "scroll_velocity_px_s", scale=1000),           # 8
        _safe_float(event, "scroll_acceleration", scale=500),             # 9
        float(event.get("y_reversal", 0)),                                # 10

        # Tier 2 — High Signal (features 11–21)
        _safe_float(event, "scroll_depth_pct", scale=100),                # 11
        _safe_float(event, "tap_interval_ms", scale=5000),                # 12
        _safe_float(event, "tap_radius_x", scale=50),                     # 13
        float(event.get("dead_tap", 0)),                                  # 14
        _safe_float(event, "tap_pressure", scale=1),                      # 15
        _safe_float(event, "patch_x", scale=1),                           # 16 — already 0–1 normalised
        _safe_float(event, "patch_y", scale=1),                           # 17 — already 0–1 normalised
        float(event.get("scroll_direction", 0)),                          # 18 — -1 / 0 / 1
        _safe_float(event, "scroll_pause_duration_ms", scale=10000),      # 19
        float(event.get("page_load_index", 0)),                           # 20
        _safe_float(event, "long_press_duration_ms", scale=5000),         # 21

        # Features 22–41 — session + per-event context
        _parse_hash(event.get("page_path_hash")) if event.get("page_path_hash") is not None else session["page_path_hash"],  # 22
        _djb2(str(event.get("page_id", ""))),                             # 23
        session["is_webview"],                                             # 24
        session["is_touch"],                                               # 25
        session["is_paid"],                                                # 26
        session["click_id_type"],                                          # 27
        session["ip_type"],                                                # 28
        session["ip_country"],                                             # 29
        _safe_float(event, "tap_radius_y", scale=50),                     # 30
        dpr,                                                               # 31
        vp_w,                                                              # 32
        vp_h,                                                              # 33
        session["browser_family"],                                         # 34
        session["os_family"],                                              # 35
        session["hour_sin"],                                               # 36
        session["hour_cos"],                                               # 37
        session["dow_sin"],                                                # 38
        session["dow_cos"],                                                # 39
        session["is_weekend"],                                             # 40
        session["timezone_mismatch"],                                      # 41

        # Indices 42–50 — reserved
        *([0.0] * 9),
    ]


def _one_hot_event_type(event_type: str) -> list[float]:
    # Must match pixel.js event_type values (lowercase)
    types = ["page_view", "route_change", "scroll", "touch_end", "click", "tab_hidden", "tab_visible", "engagement_tick", "idle"]
    return [1.0 if event_type == t else 0.0 for t in types]


def _safe_float(event: dict, key: str, scale: float = 1.0) -> float:
    val = event.get(key, 0)
    try:
        return float(val) / scale
    except (TypeError, ValueError):
        return 0.0
