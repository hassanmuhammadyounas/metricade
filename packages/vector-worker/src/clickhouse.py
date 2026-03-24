import math
import os
import httpx
from typing import Any

CLICKHOUSE_HOST     = os.environ.get('CLICKHOUSE_HOST', 'https://y390vosagc.us-east1.gcp.clickhouse.cloud:8443')
CLICKHOUSE_USER     = os.environ.get('CLICKHOUSE_USER', 'default')
CLICKHOUSE_PASSWORD = os.environ.get('CLICKHOUSE_PASSWORD', '')

# Fields needed for session context (from most-recent event in session)
SESSION_FIELDS = [
    'viewport_w_norm', 'viewport_h_norm', 'device_pixel_ratio',
    'time_to_first_interaction_ms', 'device_type', 'os_family',
    'browser_family', 'ip_type', 'ip_country',
    'hour_utc', 'day_of_week',
]

# Numeric features we need robust scaling params for
ROBUST_FEATURES = [
    'scroll_velocity_px_s', 'scroll_acceleration',
    'delta_ms', 'scroll_pause_duration_ms',
    'tap_interval_ms', 'tap_radius_x', 'tap_radius_y',
    'long_press_duration_ms', 'backgrounded_ms', 'active_ms',
    'idle_duration_ms', 'time_to_first_interaction_ms',
]


def _auth() -> tuple[str, str]:
    return (CLICKHOUSE_USER, CLICKHOUSE_PASSWORD)


def _query(sql: str, fmt: str = 'JSONEachRow') -> list[dict]:
    """Run a SELECT and return rows as list of dicts."""
    resp = httpx.post(
        CLICKHOUSE_HOST + '/',
        params={'query': sql.strip(), 'default_format': fmt},
        auth=_auth(),
        timeout=60,
    )
    resp.raise_for_status()
    import json
    rows = []
    for line in resp.text.strip().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def get_sessions_updated_since(since_iso: str, org_id: str | None = None) -> list[str]:
    """
    Returns distinct session_ids whose events were received after since_iso.
    Optionally filtered by org_id.
    """
    org_clause = f"AND org_id = '{org_id}'" if org_id else ''
    sql = f"""
        SELECT DISTINCT session_id
        FROM events
        WHERE received_at >= toDateTime64('{since_iso}', 3, 'UTC')
        {org_clause}
    """
    rows = _query(sql)
    return [r['session_id'] for r in rows]


def get_session_events(session_id: str) -> list[dict]:
    """
    Fetch all events for a session, ordered by event_seq.
    Returns list of dicts with all relevant fields.
    """
    sql = f"""
        SELECT
            event_type, event_seq, delta_ms,
            scroll_velocity_px_s, scroll_acceleration, scroll_depth_pct,
            scroll_direction, y_reversal, scroll_pause_duration_ms,
            patch_x, patch_y,
            tap_interval_ms, tap_radius_x, tap_radius_y, tap_pressure,
            dead_tap, long_press_duration_ms,
            backgrounded_ms, active_ms, idle_duration_ms,
            page_load_index,
            -- session-level fields (same for all rows, take from first)
            viewport_w_norm, viewport_h_norm, device_pixel_ratio,
            time_to_first_interaction_ms,
            device_type, os_family, browser_family,
            ip_type, ip_country,
            hour_utc, day_of_week,
            org_id, session_id, client_id, hostname
        FROM events
        WHERE session_id = '{session_id}'
        ORDER BY event_seq ASC
    """
    return _query(sql)


def get_all_session_events(org_id: str, since_iso: str = '2000-01-01 00:00:00') -> dict[str, list[dict]]:
    """
    Fetch ALL events for an org in a single query, grouped by session_id.
    Returns { session_id: [event_dicts ordered by event_seq] }
    Much faster than calling get_session_events() per session.
    """
    sql = f"""
        SELECT
            event_type, event_seq, delta_ms,
            scroll_velocity_px_s, scroll_acceleration, scroll_depth_pct,
            scroll_direction, y_reversal, scroll_pause_duration_ms,
            patch_x, patch_y,
            tap_interval_ms, tap_radius_x, tap_radius_y, tap_pressure,
            dead_tap, long_press_duration_ms,
            backgrounded_ms, active_ms, idle_duration_ms,
            page_load_index,
            viewport_w_norm, viewport_h_norm, device_pixel_ratio,
            time_to_first_interaction_ms,
            device_type, os_family, browser_family,
            ip_type, ip_country,
            hour_utc, day_of_week,
            org_id, session_id, client_id, hostname
        FROM events
        WHERE org_id = '{org_id}'
          AND received_at >= toDateTime64('{since_iso}', 3, 'UTC')
        ORDER BY session_id, event_seq ASC
    """
    rows = _query(sql)
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        sid = row['session_id']
        if sid not in grouped:
            grouped[sid] = []
        grouped[sid].append(row)
    return grouped


def get_robust_params(org_id: str | None = None) -> dict:
    """
    Compute robust scaling params (median, IQR) for all ROBUST_FEATURES
    from the last 7 days. Returns dict keyed by feature name.
    Falls back to DEFAULT_ROBUST if insufficient data.
    """
    from .constants import DEFAULT_ROBUST

    org_clause = f"AND org_id = '{org_id}'" if org_id else ''
    quantile_exprs = []
    for feat in ROBUST_FEATURES:
        quantile_exprs += [
            f"quantileIf(0.25)({feat}, {feat} IS NOT NULL AND received_at >= now() - INTERVAL 7 DAY {org_clause.replace('AND', 'AND')}) AS q25_{feat}",
            f"quantileIf(0.5)({feat},  {feat} IS NOT NULL AND received_at >= now() - INTERVAL 7 DAY {org_clause.replace('AND', 'AND')}) AS q50_{feat}",
            f"quantileIf(0.75)({feat}, {feat} IS NOT NULL AND received_at >= now() - INTERVAL 7 DAY {org_clause.replace('AND', 'AND')}) AS q75_{feat}",
        ]

    sql = f"SELECT {', '.join(quantile_exprs)} FROM events WHERE received_at >= now() - INTERVAL 7 DAY {org_clause}"
    try:
        rows = _query(sql)
    except Exception:
        return DEFAULT_ROBUST

    if not rows:
        return DEFAULT_ROBUST

    row = rows[0]
    result = {}
    for feat in ROBUST_FEATURES:
        q25 = row.get(f'q25_{feat}')
        q50 = row.get(f'q50_{feat}')
        q75 = row.get(f'q75_{feat}')
        if q50 is not None and q25 is not None and q75 is not None:
            iqr = max(float(q75) - float(q25), 1.0)
            result[feat] = {'median': float(q50), 'iqr': iqr}
        else:
            result[feat] = DEFAULT_ROBUST.get(feat, {'median': 0.0, 'iqr': 1.0})
    return result


def get_all_orgs() -> list[str]:
    """Return all distinct org_ids ever seen."""
    sql = "SELECT DISTINCT org_id FROM events"
    return [r['org_id'] for r in _query(sql)]
