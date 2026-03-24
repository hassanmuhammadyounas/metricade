import math

# ── Session context label encodings ────────────────────────────────────────

DEVICE_LABEL = {
    'mobile':  1.0,
    'tablet':  0.75,
    'desktop': 0.5,
    'unknown': 0.25,
    'bot':     0.0,
}

OS_LABEL = {
    'android': 1.0,
    'ios':     0.9,
    'windows': 0.5,
    'macos':   0.4,
    'linux':   0.3,
    'chrome os': 0.2,
    'unknown': 0.0,
}

BROWSER_LABEL = {
    'chrome':            1.0,
    'chrome mobile':     0.95,
    'mobile safari':     0.9,
    'safari':            0.85,
    'firefox':           0.6,
    'edge':              0.55,
    'samsung browser':   0.4,
    'opera':             0.3,
    'instagram':         0.2,
    'facebook':          0.15,
    'unknown':           0.0,
}

IP_TYPE_LABEL = {
    'residential': 0.0,
    'unknown':     0.5,
    'datacenter':  1.0,
}

# Top countries by web traffic volume — index/len → 0.0–1.0
# Countries not in vocab → 0.5 (mid-range)
COUNTRY_VOCAB = [
    'US', 'CN', 'IN', 'BR', 'GB', 'DE', 'FR', 'RU', 'JP', 'CA',
    'AU', 'KR', 'MX', 'ID', 'IT', 'TR', 'ES', 'PL', 'NL', 'SA',
    'AR', 'TH', 'PK', 'NG', 'VN', 'EG', 'PH', 'MY', 'SE', 'CH',
    'BE', 'AT', 'NO', 'DK', 'FI', 'PT', 'UA', 'IL', 'SG', 'AE',
    'HK', 'NZ', 'ZA', 'CZ', 'RO', 'HU', 'GR', 'CL', 'CO', 'PE',
]
_COUNTRY_INDEX = {c: i / max(len(COUNTRY_VOCAB) - 1, 1) for i, c in enumerate(COUNTRY_VOCAB)}

def country_label(iso: str | None) -> float:
    if not iso:
        return 0.5
    return _COUNTRY_INDEX.get(iso.upper(), 0.5)

# ── Per-event feature mask (25 dims) ───────────────────────────────────────
# 1 = feature is applicable to this event type, 0 = N/A (should not be mean-pooled)
# Order matches EVENT_VECTOR_ORDER in vectorizer.py

#                    [0 pv][1 sc][2 te][3 th][4 et][5 id][6 rc]  # one-hots — always 1
#                    [7  sv][8  sa][9  sd][10 sdir][11 yr][12 sp]  # scroll
#                    [13 dm][14 pp][15 dt][16 ti][17 rx][18 ry][19 lp]  # tap/click + delta
#                    [20 bg][21 ac][22 il]  # tab/engagement/idle
#                    [23 pli][24 esn]  # page-level

EVENT_MASKS = {
    'page_view':      [1,1,1,1,1,1,1,  0,0,0,0,0,0,  1,0,0,0,0,0,0,  0,0,0,  1,1],
    'scroll':         [1,1,1,1,1,1,1,  1,1,1,1,1,1,  1,0,0,0,0,0,0,  0,0,0,  0,1],
    'touch_end':      [1,1,1,1,1,1,1,  0,0,0,0,0,0,  1,1,1,1,1,1,0,  0,0,0,  0,1],
    'click':          [1,1,1,1,1,1,1,  0,0,0,0,0,0,  1,0,0,0,0,0,0,  0,0,0,  0,1],
    'tab_hidden':     [1,1,1,1,1,1,1,  0,0,0,0,0,0,  1,0,0,0,0,0,0,  1,0,0,  0,1],
    'tab_visible':    [1,1,1,1,1,1,1,  0,0,0,0,0,0,  1,0,0,0,0,0,0,  1,0,0,  0,1],
    'engagement_tick':[1,1,1,1,1,1,1,  0,0,0,0,0,0,  1,0,0,0,0,0,0,  0,1,0,  0,1],
    'idle':           [1,1,1,1,1,1,1,  0,0,0,0,0,0,  1,0,0,0,0,0,0,  0,0,1,  0,1],
    'route_change':   [1,1,1,1,1,1,1,  0,0,0,0,0,0,  1,0,0,0,0,0,0,  0,0,0,  1,1],
}
DEFAULT_MASK = [1,1,1,1,1,1,1, 0,0,0,0,0,0, 1,0,0,0,0,0,0, 0,0,0, 0,1]

# ── Default robust scaling params (fallback when ClickHouse has < 100 rows) ─
# Populated from real data; updated dynamically at runtime

DEFAULT_ROBUST = {
    'scroll_velocity_px_s':     {'median': 0.0,   'iqr': 400.0},
    'scroll_acceleration':      {'median': 0.0,   'iqr': 200.0},
    'delta_ms':                 {'median': 1200.0,'iqr': 3000.0},
    'scroll_pause_duration_ms': {'median': 500.0, 'iqr': 2000.0},
    'tap_interval_ms':          {'median': 300.0, 'iqr': 800.0},
    'tap_radius_x':             {'median': 10.0,  'iqr': 20.0},
    'tap_radius_y':             {'median': 10.0,  'iqr': 20.0},
    'long_press_duration_ms':   {'median': 500.0, 'iqr': 1000.0},
    'backgrounded_ms':          {'median': 5000.0,'iqr': 15000.0},
    'active_ms':                {'median': 4000.0,'iqr': 8000.0},
    'idle_duration_ms':         {'median': 8000.0,'iqr': 20000.0},
    'time_to_first_interaction_ms': {'median': 2000.0, 'iqr': 5000.0},
}

EVENT_TYPE_ORDER = [
    'page_view', 'scroll', 'touch_end', 'tab_hidden',
    'engagement_tick', 'idle', 'route_change',
]
