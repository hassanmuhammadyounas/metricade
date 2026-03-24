"""
scripts/generate_sessions.py
============================
Insert synthetic sessions directly into ClickHouse to build a training dataset.

Generates sessions with 5 distinct behavioral profiles so VICReg has enough
inter-class variation to learn from:
  - human_desktop   : steady scrolling, clicks, engagement ticks
  - human_mobile    : touch events, back-navigation, short sessions
  - power_user      : many route_changes, deep scrolls, long sessions
  - bouncer         : page_view only, exits immediately
  - bot             : datacenter IP, perfectly regular deltas, no touch

Usage:
  python scripts/generate_sessions.py \
    --ch-password "hQzYu~_CqZ7gR" \
    --count 200          # total sessions to generate (default 300)
    --org   org_3bq2jCKKsVv6

  # Dry run (no insert):
  python scripts/generate_sessions.py --ch-password "..." --dry-run
"""
import argparse
import json
import math
import os
import random
import sys
import uuid
from datetime import datetime, timezone, timedelta

parser = argparse.ArgumentParser()
parser.add_argument('--ch-host',     default='https://y390vosagc.us-east1.gcp.clickhouse.cloud:8443')
parser.add_argument('--ch-user',     default='default')
parser.add_argument('--ch-password', default=None)
parser.add_argument('--org',         default='org_3bq2jCKKsVv6')
parser.add_argument('--count',       type=int, default=300)
parser.add_argument('--dry-run',     action='store_true')
args = parser.parse_args()

CH_HOST     = args.ch_host
CH_USER     = args.ch_user
CH_PASSWORD = args.ch_password or os.environ.get('CLICKHOUSE_PASSWORD', '')

if not CH_PASSWORD and not args.dry_run:
    print('ERROR: --ch-password required (or set CLICKHOUSE_PASSWORD)')
    sys.exit(1)

try:
    import httpx
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', 'httpx'])
    import httpx

rng = random.Random()  # seeded per session for reproducibility

# ── Behavioral profiles ────────────────────────────────────────────────────

PROFILES = {
    'human_desktop': {
        'weight': 0.30,
        'device_type': 'desktop',
        'os_family': random.choice(['Windows', 'macOS']),
        'browser_family': random.choice(['Chrome', 'Firefox', 'Edge', 'Safari']),
        'ip_type': 'residential',
        'countries': ['US', 'GB', 'CA', 'AU', 'DE', 'FR'],
        'n_pages': (2, 6),
        'events_per_page': (5, 20),
        'delta_ms_range': (800, 4000),
        'scroll_velocity': (100, 600),
        'has_clicks': True,
        'has_touch': False,
        'has_engagement': True,
        'session_duration_s': (30, 300),
        'time_to_first_ms': (500, 5000),
    },
    'human_mobile': {
        'weight': 0.30,
        'device_type': 'mobile',
        'os_family': random.choice(['Android', 'iOS']),
        'browser_family': random.choice(['Chrome Mobile', 'Mobile Safari', 'Samsung Browser']),
        'ip_type': 'residential',
        'countries': ['PK', 'IN', 'ID', 'BR', 'NG', 'PH', 'MX'],
        'n_pages': (1, 4),
        'events_per_page': (4, 15),
        'delta_ms_range': (400, 2500),
        'scroll_velocity': (50, 800),
        'has_clicks': False,
        'has_touch': True,
        'has_engagement': True,
        'session_duration_s': (15, 180),
        'time_to_first_ms': (300, 3000),
    },
    'power_user': {
        'weight': 0.15,
        'device_type': 'desktop',
        'os_family': random.choice(['macOS', 'Linux']),
        'browser_family': 'Chrome',
        'ip_type': 'residential',
        'countries': ['US', 'DE', 'GB', 'NL', 'SE'],
        'n_pages': (6, 15),
        'events_per_page': (10, 35),
        'delta_ms_range': (300, 1500),
        'scroll_velocity': (200, 1200),
        'has_clicks': True,
        'has_touch': False,
        'has_engagement': True,
        'session_duration_s': (120, 900),
        'time_to_first_ms': (200, 1500),
    },
    'bouncer': {
        'weight': 0.10,
        'device_type': random.choice(['desktop', 'mobile']),
        'os_family': 'Windows',
        'browser_family': 'Chrome',
        'ip_type': 'residential',
        'countries': ['US', 'IN', 'RU', 'BR'],
        'n_pages': (1, 1),
        'events_per_page': (1, 3),
        'delta_ms_range': (100, 500),
        'scroll_velocity': (0, 50),
        'has_clicks': False,
        'has_touch': False,
        'has_engagement': False,
        'session_duration_s': (2, 15),
        'time_to_first_ms': (None, None),  # bounce = no interaction
    },
    'bot': {
        'weight': 0.15,
        'device_type': 'desktop',
        'os_family': 'Linux',
        'browser_family': 'Chrome',
        'ip_type': 'datacenter',
        'countries': ['US', 'DE', 'NL', 'SG'],
        'n_pages': (1, 3),
        'events_per_page': (2, 8),
        'delta_ms_range': (50, 200),     # suspiciously fast + regular
        'scroll_velocity': (500, 500),   # perfectly constant
        'has_clicks': False,
        'has_touch': False,
        'has_engagement': False,
        'session_duration_s': (5, 30),
        'time_to_first_ms': (50, 200),
    },
}

HOSTNAMES = ['example-store.myshopify.com', 'shop.demostore.com', 'www.testmerchant.io']

BROWSER_VERSIONS = {
    'Chrome': '124.0', 'Firefox': '125.0', 'Edge': '124.0', 'Safari': '17.4',
    'Chrome Mobile': '124.0', 'Mobile Safari': '17.4', 'Samsung Browser': '24.0',
    'Chrome Headless': '124.0', 'Python Requests': '2.31',
}
OS_VERSIONS = {
    'Windows': '10', 'macOS': '14.4', 'Linux': 'unknown',
    'Android': '14', 'iOS': '17.4',
}

PAGE_URLS = [
    '/products/running-shoes', '/collections/all', '/cart', '/checkout',
    '/products/wireless-headphones', '/pages/about', '/blogs/news',
    '/products/yoga-mat', '/collections/sale', '/',
]


def now_dt() -> datetime:
    return datetime.now(tz=timezone.utc)


def iso(dt: datetime) -> str:
    return dt.strftime('%Y-%m-%d %H:%M:%S.') + f'{dt.microsecond // 1000:03d}'


def iso_dt(dt: datetime) -> str:
    return dt.strftime('%Y-%m-%dT%H:%M:%S.') + f'{dt.microsecond // 1000:03d}'


def gen_session(profile_name: str, profile: dict, org_id: str, base_time: datetime) -> list[dict]:
    """Generate all event rows for one synthetic session."""
    session_id = str(uuid.uuid4())
    client_id  = str(uuid.uuid4())
    trace_id   = f'{session_id}_0_{int(base_time.timestamp()*1000)}'
    hostname   = random.choice(HOSTNAMES)
    country    = random.choice(profile['countries'])

    # Device
    device_type     = profile['device_type']
    os_family       = profile['os_family'] if isinstance(profile['os_family'], str) else random.choice(profile['os_family'])
    browser_family  = profile['browser_family'] if isinstance(profile['browser_family'], str) else random.choice(profile['browser_family'])
    browser_version = BROWSER_VERSIONS.get(browser_family, '1.0')
    os_version      = OS_VERSIONS.get(os_family, 'unknown')
    device_vendor   = 'Apple' if os_family in ('macOS', 'iOS') else ('Samsung' if browser_family == 'Samsung Browser' else 'unknown')
    is_webview      = False

    ip_type     = profile['ip_type']
    viewport_w  = round(random.uniform(0.4, 1.0), 3) if device_type == 'desktop' else round(random.uniform(0.14, 0.18), 3)
    viewport_h  = round(random.uniform(0.4, 0.85), 3) if device_type == 'desktop' else round(random.uniform(0.55, 0.95), 3)
    dpr         = random.choice([1.0, 1.5, 2.0, 3.0]) if device_type == 'mobile' else random.choice([1.0, 2.0])

    ttfi_lo, ttfi_hi = profile['time_to_first_ms']
    ttfi = random.randint(ttfi_lo, ttfi_hi) if ttfi_lo is not None else None

    n_pages = random.randint(*profile['n_pages'])
    session_duration = random.randint(*profile['session_duration_s'])
    session_end_ms   = int(base_time.timestamp() * 1000) + session_duration * 1000

    rows: list[dict] = []
    current_ms = int(base_time.timestamp() * 1000)
    page_load_index = 0

    for page_idx in range(n_pages):
        page_url = random.choice(PAGE_URLS)
        n_events = random.randint(*profile['events_per_page'])
        prev_ms  = current_ms

        # Always start page with page_view (page_idx=0) or route_change
        event_type = 'page_view' if page_idx == 0 else 'route_change'
        delta = 0 if page_idx == 0 else random.randint(200, 1500)
        current_ms += delta

        rows.append(_make_row(
            event_type, len(rows), current_ms - prev_ms,
            page_url, page_load_index,
            session_id, client_id, trace_id, org_id, hostname,
            country, ip_type, device_type, os_family, os_version,
            browser_family, browser_version, device_vendor, is_webview,
            viewport_w, viewport_h, dpr, ttfi, base_time, profile, profile_name,
        ))
        prev_ms = current_ms

        for ei in range(1, n_events):
            if current_ms >= session_end_ms:
                break

            # Choose event type based on profile
            etype = _pick_event(profile, device_type)
            delta_ms = _pick_delta(profile, etype)
            current_ms += delta_ms

            rows.append(_make_row(
                etype, len(rows), delta_ms,
                None, page_load_index,
                session_id, client_id, trace_id, org_id, hostname,
                country, ip_type, device_type, os_family, os_version,
                browser_family, browser_version, device_vendor, is_webview,
                viewport_w, viewport_h, dpr, ttfi, base_time, profile, profile_name,
            ))
            prev_ms = current_ms

        page_load_index += 1

    return rows


def _pick_event(profile: dict, device_type: str) -> str:
    weights = []
    choices = []

    choices.append('scroll');       weights.append(40)
    if profile['has_touch']:
        choices.append('touch_end'); weights.append(25)
    if profile['has_clicks'] and not profile['has_touch']:
        choices.append('click');     weights.append(15)
    if profile['has_engagement']:
        choices.append('engagement_tick'); weights.append(15)
        choices.append('tab_hidden');      weights.append(3)
        choices.append('tab_visible');     weights.append(3)
        choices.append('idle');            weights.append(4)

    total = sum(weights)
    r = random.random() * total
    cumul = 0
    for c, w in zip(choices, weights):
        cumul += w
        if r < cumul:
            return c
    return 'scroll'


def _pick_delta(profile: dict, event_type: str) -> int:
    lo, hi = profile['delta_ms_range']
    if profile['ip_type'] == 'datacenter':  # bot — very regular
        base = (lo + hi) // 2
        return base + random.randint(-20, 20)
    return random.randint(lo, hi)


def _make_row(
    event_type, event_seq, delta_ms, page_url, page_load_index,
    session_id, client_id, trace_id, org_id, hostname,
    country, ip_type, device_type, os_family, os_version,
    browser_family, browser_version, device_vendor, is_webview,
    viewport_w, viewport_h, dpr, ttfi, base_time, profile, profile_name,
) -> dict:
    now = datetime.now(tz=timezone.utc)
    # Spread events across the last 30 days
    age_s   = random.randint(0, 30 * 86400)
    recv_dt = now - timedelta(seconds=age_s)
    evt_dt  = recv_dt

    row = {
        'received_at': recv_dt.strftime('%Y-%m-%d %H:%M:%S.') + f'{recv_dt.microsecond // 1000:03d}',
        'event_ts':    evt_dt.strftime('%Y-%m-%d %H:%M:%S.') + f'{evt_dt.microsecond // 1000:03d}',
        'org_id':      org_id,
        'session_id':  session_id,
        'client_id':   client_id,
        'trace_id':    trace_id,
        'hostname':    hostname,
        'browser_timezone': random.choice(['America/New_York', 'Europe/London', 'Asia/Karachi', 'Asia/Jakarta']),
        'viewport_w_norm':  viewport_w,
        'viewport_h_norm':  viewport_h,
        'device_pixel_ratio': dpr,
        'time_to_first_interaction_ms': ttfi,
        'ip_address':  f'1{random.randint(0,99)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}',
        'ip_country':  country,
        'ip_asn':      str(random.randint(1000, 99999)),
        'ip_org':      'ISP' if ip_type == 'residential' else 'DigitalOcean',
        'ip_type':     ip_type,
        'ip_timezone': 'America/New_York',
        'user_agent':  f'Mozilla/5.0 ({os_family}) {browser_family}/{browser_version}',
        'browser_family':  browser_family,
        'browser_version': browser_version,
        'os_family':   os_family,
        'os_version':  os_version,
        'device_type': device_type,
        'device_vendor': device_vendor,
        'is_webview':  is_webview,
        'hour_utc':    recv_dt.hour,
        'day_of_week': recv_dt.weekday(),
        'event_type':  event_type,
        'event_seq':   event_seq,
        'delta_ms':    delta_ms,
        'is_retry':    False,
        'page_url':    page_url,
        'page_load_index': page_load_index,
        # defaults — filled per event type below
        'scroll_velocity_px_s':     None,
        'scroll_acceleration':      None,
        'scroll_depth_pct':         None,
        'scroll_direction':         None,
        'y_reversal':               None,
        'scroll_pause_duration_ms': None,
        'patch_x':                  None,
        'patch_y':                  None,
        'tap_interval_ms':          None,
        'tap_radius_x':             None,
        'tap_radius_y':             None,
        'tap_pressure':             None,
        'dead_tap':                 None,
        'long_press_duration_ms':   None,
        'backgrounded_ms':          None,
        'active_ms':                None,
        'idle_duration_ms':         None,
    }

    v_lo, v_hi = profile['scroll_velocity']
    is_bot = profile['ip_type'] == 'datacenter'

    if event_type == 'scroll':
        vel = v_lo if is_bot else random.uniform(v_lo, v_hi)
        row['scroll_velocity_px_s']  = round(vel, 2)
        row['scroll_acceleration']   = round(random.uniform(-50, 50) if not is_bot else 0.0, 2)
        row['scroll_depth_pct']      = round(random.uniform(5, 95), 1)
        row['scroll_direction']      = 1 if random.random() > 0.15 else -1
        row['y_reversal']            = random.random() < 0.1
        row['scroll_pause_duration_ms'] = random.randint(0, 3000) if not is_bot else 0
        row['patch_x']               = round(random.uniform(0, 1), 3)
        row['patch_y']               = round(random.uniform(0, 1), 3)

    elif event_type == 'touch_end':
        row['tap_interval_ms']  = random.randint(150, 800)
        row['tap_radius_x']     = round(random.uniform(5, 30), 2)
        row['tap_radius_y']     = round(random.uniform(5, 30), 2)
        row['tap_pressure']     = round(random.uniform(0.1, 0.9), 3)
        row['dead_tap']         = random.random() < 0.05
        row['long_press_duration_ms'] = random.randint(0, 1500) if random.random() < 0.1 else None

    elif event_type == 'click':
        row['patch_x'] = round(random.uniform(0, 1), 3)
        row['patch_y'] = round(random.uniform(0, 1), 3)

    elif event_type == 'tab_hidden':
        row['backgrounded_ms'] = random.randint(500, 30000)

    elif event_type == 'tab_visible':
        row['backgrounded_ms'] = random.randint(500, 30000)

    elif event_type == 'engagement_tick':
        row['active_ms'] = random.randint(2000, 10000)

    elif event_type == 'idle':
        row['idle_duration_ms'] = random.randint(5000, 60000)

    return row


def insert_rows(rows: list[dict]) -> None:
    ndjson = '\n'.join(json.dumps(r) for r in rows)
    query  = 'INSERT INTO events FORMAT JSONEachRow'
    auth   = (CH_USER, CH_PASSWORD)
    resp   = httpx.post(
        CH_HOST + '/',
        params={'query': query},
        auth=auth,
        content=ndjson.encode(),
        headers={'Content-Type': 'application/octet-stream'},
        timeout=30,
    )
    resp.raise_for_status()


# ── Main ───────────────────────────────────────────────────────────────────
print(f'Generating {args.count} sessions  org={args.org}  dry_run={args.dry_run}')

profile_names  = list(PROFILES.keys())
profile_weights = [PROFILES[p]['weight'] for p in profile_names]

total_rows     = 0
total_sessions = 0
base_time      = datetime.now(tz=timezone.utc)

BATCH_SIZE = 20  # sessions per ClickHouse insert

batch_rows: list[dict] = []

for i in range(args.count):
    pname   = random.choices(profile_names, weights=profile_weights)[0]
    profile = PROFILES[pname]
    rows    = gen_session(pname, profile, args.org, base_time)

    batch_rows.extend(rows)
    total_rows     += len(rows)
    total_sessions += 1

    if len(batch_rows) >= BATCH_SIZE * 10 or i == args.count - 1:
        if not args.dry_run:
            try:
                insert_rows(batch_rows)
            except Exception as e:
                print(f'  ERROR inserting batch: {e}')
                sys.exit(1)
        batch_rows = []
        pct = (i + 1) / args.count * 100
        print(f'  [{pct:5.1f}%] {i+1}/{args.count} sessions  {total_rows} rows', end='\r')

print(f'\nDone. Inserted {total_sessions} sessions  {total_rows} rows  {"(dry run)" if args.dry_run else "→ ClickHouse"}')
print()
print('Next: train the model on the expanded dataset:')
print(f'  python scripts/train_hgru.py --ch-password "$CLICKHOUSE_PASSWORD" --epochs 500 --batch 64')
