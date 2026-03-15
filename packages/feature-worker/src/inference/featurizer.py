"""
Raw event batch → FeatureOutput(cont=[variable_len, N_CONT], cat=[N_CAT]).
Feature order matches CLAUDE.md Feature Vector section exactly.
"""
import math
import torch
from dataclasses import dataclass
from typing import Any

from ..constants import MAX_RAW_EVENTS

MAX_SEQ_LEN = 256
N_CONT = 40   # continuous features per event row
N_CAT  = 8   # session-level categorical indices

# ── Categorical vocabularies ─────────────────────────────────────────────────
# Index 0 = UNK for any value not in vocab (cold-start / unseen values).
# Keys are lowercased before lookup (see _extract_session).

BROWSER_VOCAB: dict[str, int] = {
    "chrome": 1, "firefox": 2, "safari": 3, "mobile_safari": 4,
    "samsung_internet": 5, "edge": 6, "opera": 7, "opera_mini": 8,
    "instagram": 9, "facebook": 10, "tiktok": 11, "wechat": 12,
    "webview": 13, "ie": 14, "chromium": 15, "brave": 16,
    "yandex": 17, "uc_browser": 18, "miui": 19, "silk": 20,
}  # vocab_size = 21

OS_VOCAB: dict[str, int] = {
    "android": 1, "ios": 2, "windows": 3, "mac_os_x": 4, "macos": 4,
    "linux": 5, "chromeos": 6, "ubuntu": 7, "fedora": 8,
    "windows_phone": 9, "blackberry": 10, "harmony": 11,
    "kaios": 12, "openbsd": 13,
}  # vocab_size = 14

# ISO 3166-1 alpha-2 — top ~110 traffic countries; keys are uppercased before lookup
_COUNTRY_LIST = [
    "US", "GB", "CA", "AU", "DE", "FR", "IN", "PK", "BD", "NG",
    "PH", "ID", "BR", "MX", "AR", "CO", "VN", "TH", "MY", "SG",
    "AE", "SA", "EG", "MA", "ZA", "KE", "GH", "TR", "PL", "NL",
    "SE", "NO", "DK", "FI", "CH", "AT", "BE", "PT", "ES", "IT",
    "RU", "UA", "KZ", "KR", "JP", "TW", "HK", "NZ", "IE", "IL",
    "IQ", "LK", "NP", "MM", "KH", "ET", "TZ", "UG", "RW", "CI",
    "SN", "CM", "MZ", "AO", "MU", "JM", "TT", "HN", "GT", "PE",
    "CL", "EC", "BO", "PY", "UY", "VE", "CU", "DO", "CR", "PA",
    "QA", "KW", "BH", "OM", "JO", "LB", "DZ", "TN", "LY", "SD",
    "YE", "AF", "IR", "UZ", "AZ", "GE", "AM", "MD", "RO", "BG",
    "GR", "HU", "CZ", "SK", "HR", "RS", "BA", "SI", "MK", "AL",
]
COUNTRY_VOCAB: dict[str, int] = {c: i + 1 for i, c in enumerate(_COUNTRY_LIST)}  # vocab_size = 111

CLICK_ID_VOCAB: dict[str, int] = {
    "none": 1, "fbclid": 2, "gclid": 3, "gbraid": 4, "wbraid": 5,
    "gclsrc": 6, "dclid": 7, "ttclid": 8, "msclkid": 9,
    "li_fat_id": 10, "twclid": 11, "sclid": 12, "irclid": 13,
}  # vocab_size = 14

SESSION_SOURCE_VOCAB: dict[str, int] = {
    "direct": 1, "meta": 2, "facebook": 2, "google": 3, "instagram": 4,
    "klaviyo": 5, "tiktok": 6, "bing": 7, "pinterest": 8,
    "twitter": 9, "x": 9, "snapchat": 10, "youtube": 11,
    "email": 12, "sms": 13, "affiliate": 14, "referral": 15,
}  # vocab_size = 16

SESSION_MEDIUM_VOCAB: dict[str, int] = {
    "direct": 1, "paid_social": 2, "organic_social": 3,
    "paid_search": 4, "organic_search": 5, "email": 6,
    "sms": 7, "referral": 8, "display": 9, "video": 10,
    "affiliate": 11, "push": 12,
}  # vocab_size = 13

DEVICE_VENDOR_VOCAB: dict[str, int] = {
    "apple": 1, "samsung": 2, "google": 3, "xiaomi": 4, "huawei": 5,
    "motorola": 6, "lg": 7, "oppo": 8, "oneplus": 9, "realme": 10,
    "vivo": 11, "sony": 12, "nokia": 13, "htc": 14, "asus": 15,
    "lenovo": 16, "microsoft": 17,
}  # vocab_size = 18

# page_path_hash: modulo bucketing over fixed vocab size.
# raw hex → int → (int % PAGE_PATH_HASH_VOCAB_SIZE) + 1
# +1 reserves index 0 for UNK (missing hash). Table size = 4097.
PAGE_PATH_HASH_VOCAB_SIZE = 4096


@dataclass
class FeatureOutput:
    cont: torch.Tensor   # [min(len(events), MAX_RAW_EVENTS), N_CONT] float32 — per-event continuous features (variable length)
    cat:  torch.Tensor   # [N_CAT] int64 — session-level categorical vocab indices


def featurize(payload: dict[str, Any], enriched: dict[str, Any] | None = None) -> FeatureOutput:
    """
    Convert a raw event payload to FeatureOutput.
    payload    — the inner flush payload (events list at payload["events"])
    enriched   — the full enrichment wrapper from the edge worker
    """
    events   = payload.get("events", [])
    enriched = enriched or {}
    session  = _extract_session(payload, events, enriched)

    cont_rows = [_event_to_cont(event, session) for event in events[:MAX_RAW_EVENTS]]

    return FeatureOutput(
        cont=torch.tensor(cont_rows, dtype=torch.float32) if cont_rows else torch.zeros(0, N_CONT, dtype=torch.float32),
        cat=torch.tensor(_session_to_cat(session), dtype=torch.int64),
    )


# ── Session extraction ────────────────────────────────────────────────────────

def _extract_session(payload: dict, events: list, enriched: dict) -> dict:
    """
    Build a dict of session-level signals from payload root, enriched wrapper,
    and the first page_view event (backwards-compat fallback for old stream entries).
    """
    page_view = next((e for e in events if e.get("event_type") == "page_view"), {})
    ip = enriched.get("ip_meta") or {}
    ua = enriched.get("ua_meta") or {}
    tf = enriched.get("time_features") or {}

    def _pget(key, default=None):
        """payload root first, fall back to page_view event."""
        v = payload.get(key)
        return v if v is not None else page_view.get(key, default)

    return {
        # ── Continuous session fields ─────────────────────────────────────────
        "is_paid":            float(_pget("is_paid", 0)),
        "device_pixel_ratio": min(float(_pget("device_pixel_ratio", 1.0)), 4.0) / 4.0,
        "viewport_w_norm":    float(_pget("viewport_w_norm", 0.0)),
        "viewport_h_norm":    float(_pget("viewport_h_norm", 0.0)),
        "is_webview":         float(ua.get("is_webview", False)),
        "is_touch":           1.0 if ua.get("device_type") in ("mobile", "tablet") else 0.0,
        "hour_sin":           float(tf.get("hour_sin", 0.0)),
        "hour_cos":           float(tf.get("hour_cos", 0.0)),
        "dow_sin":            float(tf.get("dow_sin", 0.0)),
        "dow_cos":            float(tf.get("dow_cos", 0.0)),
        "is_weekend":         float(tf.get("is_weekend", 0)),
        "timezone_mismatch":  float(enriched.get("timezone_mismatch", False)),
        "prior_session_count": min(
            math.log1p(float(enriched.get("prior_session_count", 0))) / math.log1p(20),
            1.0,
        ),
        # Ordinal encodings (small fixed cardinality — no embedding needed)
        "ip_type": {
            "residential": 0.0, "unknown": 0.5, "datacenter": 1.0,
        }.get(ip.get("ip_type", "unknown"), 0.5),
        "device_type": {
            "mobile": 1.0, "tablet": 0.75, "desktop": 0.5, "unknown": 0.25, "bot": 0.0,
        }.get(ua.get("device_type", "unknown"), 0.25),

        # ── Categorical fields (raw strings for vocab lookup) ─────────────────
        "browser_family":  (ua.get("browser_family")  or "").lower().replace(" ", "_"),
        "os_family":       (ua.get("os_family")       or "").lower().replace(" ", "_"),
        "ip_country":      (ip.get("ip_country")      or "").upper(),
        "click_id_type":   (_pget("click_id_type")    or "none").lower(),
        "session_source":  (_pget("session_source")   or "direct").lower(),
        "session_medium":  (_pget("session_medium")   or "direct").lower(),
        "device_vendor":   (ua.get("device_vendor")   or "").lower().replace(" ", "_"),

        # Landing page path hash (from first page_view event)
        "page_path_hash":  page_view.get("page_path_hash"),
    }


def _session_to_cat(session: dict) -> list[int]:
    """Convert session dict → [N_CAT] list of vocabulary indices (int64)."""
    ph = session["page_path_hash"]
    if ph is None:
        page_hash_idx = 0
    else:
        try:
            raw = int(str(ph), 16)
            page_hash_idx = (raw % PAGE_PATH_HASH_VOCAB_SIZE) + 1  # 0 reserved for UNK
        except (ValueError, TypeError):
            page_hash_idx = 0

    return [
        BROWSER_VOCAB.get(session["browser_family"], 0),        # 0
        OS_VOCAB.get(session["os_family"], 0),                  # 1
        COUNTRY_VOCAB.get(session["ip_country"], 0),            # 2
        CLICK_ID_VOCAB.get(session["click_id_type"], 0),        # 3
        SESSION_SOURCE_VOCAB.get(session["session_source"], 0), # 4
        SESSION_MEDIUM_VOCAB.get(session["session_medium"], 0), # 5
        DEVICE_VENDOR_VOCAB.get(session["device_vendor"], 0),   # 6
        page_hash_idx,                                          # 7
    ]


# ── Per-event continuous features ────────────────────────────────────────────

def _event_to_cont(event: dict, session: dict) -> list[float]:
    """Map a single event dict → [N_CONT] float list."""
    dpr = (
        min(float(event["device_pixel_ratio"]), 4.0) / 4.0
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
        # 0–8: one-hot event type (9 classes)
        *_one_hot_event_type(event.get("event_type", "")),
        # 9–23: per-event behavioural signals
        _safe_float(event, "delta_ms", scale=10000),                           # 9
        _log1p_signed(event.get("scroll_velocity_px_s", 0), scale=10),        # 10
        _log1p_signed(event.get("scroll_acceleration", 0), scale=15),         # 11
        float(event.get("y_reversal", 0)),                                     # 12
        _safe_float(event, "scroll_depth_pct", scale=100),                    # 13
        _safe_float(event, "tap_interval_ms", scale=5000),                    # 14
        _safe_float(event, "tap_radius_x", scale=50),                         # 15
        float(event.get("dead_tap", 0)),                                      # 16
        _safe_float(event, "tap_pressure"),                                   # 17
        _safe_float(event, "patch_x"),                                        # 18
        _safe_float(event, "patch_y"),                                        # 19
        float(event.get("scroll_direction", 0)),                              # 20
        _safe_float(event, "scroll_pause_duration_ms", scale=10000),          # 21
        min(float(event.get("page_load_index", 1)), 20.0) / 20.0,            # 22
        _safe_float(event, "long_press_duration_ms", scale=5000),             # 23
        _safe_float(event, "tap_radius_y", scale=50),                         # 24
        # 25–39: session-level context (broadcast to every event row)
        session["is_webview"],                                                 # 25
        session["is_touch"],                                                   # 26
        session["is_paid"],                                                    # 27
        dpr,                                                                   # 28
        vp_w,                                                                  # 29
        vp_h,                                                                  # 30
        session["hour_sin"],                                                   # 31
        session["hour_cos"],                                                   # 32
        session["dow_sin"],                                                    # 33
        session["dow_cos"],                                                    # 34
        session["is_weekend"],                                                 # 35
        session["timezone_mismatch"],                                          # 36
        session["prior_session_count"],                                        # 37
        session["ip_type"],                                                    # 38
        session["device_type"],                                                # 39
    ]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _one_hot_event_type(event_type: str) -> list[float]:
    types = [
        "page_view", "route_change", "scroll", "touch_end", "click",
        "tab_hidden", "tab_visible", "engagement_tick", "idle",
    ]
    return [1.0 if event_type == t else 0.0 for t in types]


def _log1p_signed(val: Any, scale: float) -> float:
    """sign(v) * log1p(|v|) / scale — compresses large values symmetrically around 0."""
    try:
        v = float(val)
        return math.copysign(math.log1p(abs(v)), v) / scale
    except (TypeError, ValueError):
        return 0.0


def _safe_float(event: dict, key: str, scale: float = 1.0) -> float:
    val = event.get(key, 0)
    try:
        return float(val) / scale
    except (TypeError, ValueError):
        return 0.0
