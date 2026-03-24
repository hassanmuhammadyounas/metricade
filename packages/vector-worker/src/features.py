"""
Feature extraction for H-GRU encoder.

Three levels:
  Event  → (EVENT_DIM=20,)   tensor  — one per event, fed to Event GRU
  Page   → (PAGE_DIM=8,)     tensor  — one per page, appended to Event GRU output
  Session→ (SESSION_DIM=14,) tensor  — one per session, used as GRU h_0
"""
import math
from typing import Any

import torch

from .constants import (
    DEVICE_LABEL, OS_LABEL, BROWSER_LABEL, IP_TYPE_LABEL,
    DEFAULT_ROBUST, country_label,
)

# ── Dimensions (exported for model.py) ────────────────────────────────────
EVENT_DIM   = 20
PAGE_DIM    = 8
SESSION_DIM = 14

# Event type → one-hot index
EVENT_TYPE_IDX = {
    'page_view':       0,
    'scroll':          1,
    'touch_end':       2,
    'tab_hidden':      3,
    'engagement_tick': 4,
    'idle':            5,
    'route_change':    6,
}

# ── Normalization helpers ──────────────────────────────────────────────────

def _robust(val: float | None, params: dict) -> float:
    if val is None:
        return 0.0
    x      = math.log1p(abs(val))
    median = math.log1p(abs(params['median']))
    iqr    = math.log1p(params['iqr']) if params['iqr'] > 0 else 1.0
    return max(-3.0, min(3.0, (x - median) / iqr))

def _robust_signed(val: float | None, params: dict) -> float:
    if val is None:
        return 0.0
    sign   = 1.0 if val >= 0 else -1.0
    x      = math.log1p(abs(val))
    median = math.log1p(abs(params['median']))
    iqr    = math.log1p(params['iqr']) if params['iqr'] > 0 else 1.0
    return max(-3.0, min(3.0, sign * (x - median) / iqr))

def _clamp(val: Any, lo: float, hi: float, default: float = 0.0) -> float:
    if val is None:
        return default
    return max(lo, min(hi, float(val)))

def _bool(val: Any) -> float:
    return 1.0 if val else 0.0

# ── Event feature vector (EVENT_DIM = 20) ─────────────────────────────────

def encode_event(row: dict, robust: dict) -> list[float]:
    """
    Returns a 20-dim float list for one event row.

    [0–6]   event_type one-hot (7 dims)
    [7]     delta_ms              log1p robust
    [8]     scroll_velocity       sign×log1p robust
    [9]     scroll_acceleration   sign×log1p robust
    [10]    scroll_depth_pct      /100
    [11]    scroll_direction      -1/0/1
    [12]    y_reversal            bool
    [13]    tap_pressure          0–1
    [14]    dead_tap              bool
    [15]    tap_radius_x          log1p robust
    [16]    backgrounded_ms       log1p robust
    [17]    active_ms             log1p robust
    [18]    idle_duration_ms      log1p robust
    [19]    page_load_index       min(x,20)/20
    """
    et  = (row.get('event_type') or '').lower()
    idx = EVENT_TYPE_IDX.get(et, -1)
    one_hot = [1.0 if i == idx else 0.0 for i in range(7)]

    feats = [
        _robust(row.get('delta_ms'),
                robust.get('delta_ms', DEFAULT_ROBUST['delta_ms'])),
        _robust_signed(row.get('scroll_velocity_px_s'),
                       robust.get('scroll_velocity_px_s', DEFAULT_ROBUST['scroll_velocity_px_s'])),
        _robust_signed(row.get('scroll_acceleration'),
                       robust.get('scroll_acceleration',  DEFAULT_ROBUST['scroll_acceleration'])),
        _clamp(row.get('scroll_depth_pct'), 0.0, 100.0) / 100.0,
        _clamp(row.get('scroll_direction'), -1.0, 1.0, 0.0),
        _bool(row.get('y_reversal')),
        _clamp(row.get('tap_pressure'), 0.0, 1.0),
        _bool(row.get('dead_tap')),
        _robust(row.get('tap_radius_x'),
                robust.get('tap_radius_x', DEFAULT_ROBUST['tap_radius_x'])),
        _robust(row.get('backgrounded_ms'),
                robust.get('backgrounded_ms', DEFAULT_ROBUST['backgrounded_ms'])),
        _robust(row.get('active_ms'),
                robust.get('active_ms',       DEFAULT_ROBUST['active_ms'])),
        _robust(row.get('idle_duration_ms'),
                robust.get('idle_duration_ms', DEFAULT_ROBUST['idle_duration_ms'])),
        min(float(row.get('page_load_index') or 0), 20.0) / 20.0,
    ]

    return one_hot + feats  # 7 + 13 = 20


# ── Page feature vector (PAGE_DIM = 8) ────────────────────────────────────

def encode_page(events: list[dict], robust: dict, is_exit: bool = False) -> list[float]:
    """
    Returns an 8-dim float list summarising one page's events.

    [0]  n_events          log1p / log1p(200)
    [1]  time_on_page_ms   log1p robust (sum of delta_ms)
    [2]  max_scroll_depth  /100
    [3]  had_interaction   bool (any tap/click)
    [4]  scroll_rate       n_scroll / n_events
    [5]  dead_tap_rate     n_dead_tap / max(n_touch,1)
    [6]  page_load_index   min(x,20)/20  (from first event)
    [7]  is_exit_page      bool
    """
    n = len(events)
    if n == 0:
        return [0.0] * PAGE_DIM

    time_on_page = sum(float(e.get('delta_ms') or 0) for e in events)
    max_depth    = max((float(e.get('scroll_depth_pct') or 0) for e in events), default=0.0)
    had_interact = any(e.get('event_type') in ('touch_end', 'click') for e in events)
    n_scroll     = sum(1 for e in events if e.get('event_type') == 'scroll')
    n_touch      = sum(1 for e in events if e.get('event_type') == 'touch_end')
    n_dead       = sum(1 for e in events if e.get('dead_tap'))
    pli          = float(events[0].get('page_load_index') or 0)

    tp_params = robust.get('delta_ms', DEFAULT_ROBUST['delta_ms'])
    # Scale time_on_page with same robust params as delta_ms
    time_norm = _robust(time_on_page, tp_params)

    return [
        math.log1p(n) / math.log1p(200),
        time_norm,
        max_depth / 100.0,
        _bool(had_interact),
        n_scroll / n,
        n_dead / max(n_touch, 1),
        min(pli, 20.0) / 20.0,
        _bool(is_exit),
    ]


# ── Session context vector (SESSION_DIM = 14) ─────────────────────────────

def encode_session_context(session_row: dict, robust: dict) -> list[float]:
    """
    Returns a 14-dim float list from session-level fields.
    session_row is any event row from the session (they share these fields).

    [0]  viewport_w_norm
    [1]  viewport_h_norm
    [2]  pixel_ratio_norm   (dpr-1)/3
    [3]  ttfi_log_robust
    [4]  device_label
    [5]  os_label
    [6]  browser_label
    [7]  ip_type_label
    [8]  country_label
    [9]  hour_sin
    [10] hour_cos
    [11] dow_sin
    [12] dow_cos
    [13] is_returning       1 if n_prior_sessions > 0
    """
    vw  = _clamp(session_row.get('viewport_w_norm'), 0.0, 1.0)
    vh  = _clamp(session_row.get('viewport_h_norm'), 0.0, 1.0)
    dpr = _clamp(((session_row.get('device_pixel_ratio') or 1.0) - 1.0) / 3.0, 0.0, 1.0)

    ttfi = _robust(session_row.get('time_to_first_interaction_ms'),
                   robust.get('time_to_first_interaction_ms',
                               DEFAULT_ROBUST['time_to_first_interaction_ms']))

    dev    = DEVICE_LABEL.get((session_row.get('device_type')   or 'unknown').lower(), 0.25)
    os_v   = OS_LABEL.get(    (session_row.get('os_family')     or 'unknown').lower(), 0.0)
    br_v   = BROWSER_LABEL.get((session_row.get('browser_family') or 'unknown').lower(), 0.0)
    ip_v   = IP_TYPE_LABEL.get((session_row.get('ip_type')      or 'unknown').lower(), 0.5)
    cn_v   = country_label(session_row.get('ip_country'))

    hour   = float(session_row.get('hour_utc')    or 0)
    dow    = float(session_row.get('day_of_week') or 0)
    h_sin  = math.sin(2 * math.pi * hour / 24)
    h_cos  = math.cos(2 * math.pi * hour / 24)
    d_sin  = math.sin(2 * math.pi * dow  / 7)
    d_cos  = math.cos(2 * math.pi * dow  / 7)

    ret    = 1.0 if (session_row.get('prior_session_count') or 0) > 0 else 0.0

    return [vw, vh, dpr, ttfi, dev, os_v, br_v, ip_v, cn_v,
            h_sin, h_cos, d_sin, d_cos, ret]


# ── Group events into pages ────────────────────────────────────────────────

def group_into_pages(events: list[dict]) -> list[list[dict]]:
    """
    Split a flat event list into pages.
    A new page begins on every page_view or route_change event.
    Events are assumed to be sorted by event_seq ASC.
    """
    if not events:
        return []

    pages: list[list[dict]] = []
    current: list[dict] = []

    for ev in events:
        et = (ev.get('event_type') or '').lower()
        if et in ('page_view', 'route_change') and current:
            pages.append(current)
            current = []
        current.append(ev)

    if current:
        pages.append(current)

    return pages


# ── Build tensor inputs for one session ───────────────────────────────────

def build_session_tensors(
    events: list[dict],
    robust: dict,
) -> tuple[list[tuple[torch.Tensor, torch.Tensor]], torch.Tensor] | None:
    """
    Returns (pages_data, session_ctx_tensor) or None if events is empty.

    pages_data: list of (event_seq_tensor, page_feat_tensor) — one per page
      event_seq_tensor : (n_events, EVENT_DIM)
      page_feat_tensor : (PAGE_DIM,)

    session_ctx_tensor: (SESSION_DIM,)
    """
    if not events:
        return None

    pages = group_into_pages(events)
    if not pages:
        return None

    n_pages = len(pages)
    pages_data = []
    for i, page_events in enumerate(pages):
        event_vecs = [encode_event(e, robust) for e in page_events]
        event_tensor = torch.tensor(event_vecs, dtype=torch.float32)  # (n, EVENT_DIM)
        page_feat    = encode_page(page_events, robust, is_exit=(i == n_pages - 1))
        page_tensor  = torch.tensor(page_feat,  dtype=torch.float32)  # (PAGE_DIM,)
        pages_data.append((event_tensor, page_tensor))

    session_ctx = encode_session_context(events[0], robust)
    ctx_tensor  = torch.tensor(session_ctx, dtype=torch.float32)  # (SESSION_DIM,)

    return pages_data, ctx_tensor
