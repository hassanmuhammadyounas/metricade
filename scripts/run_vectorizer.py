"""
scripts/run_vectorizer.py
=========================
Local / RunPod inference: read sessions from ClickHouse, encode with
H-GRU, upsert 64-dim vectors to Upstash Vector.

All credentials passed as CLI args or environment variables.

Usage (local):
  python scripts/run_vectorizer.py \
    --ch-password hQzYu~_CqZ7gR \
    --vector-url  https://busy-macaque-12282-us1-vector.upstash.io \
    --vector-token ABYFMGJ1c3kt...

Usage (RunPod — set env vars once then run):
  export CLICKHOUSE_PASSWORD=hQzYu~_CqZ7gR
  export UPSTASH_VECTOR_URL=https://busy-macaque-12282-us1-vector.upstash.io
  export UPSTASH_VECTOR_TOKEN=ABYFMGJ1c3kt...
  python scripts/run_vectorizer.py

Optional flags:
  --org    org_XXXX        process only one org
  --since  "2026-01-01"    only sessions after this date
  --weights path/to/hgru.pt
"""
import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────
REPO_ROOT  = Path(__file__).resolve().parent.parent
WORKER_PKG = REPO_ROOT / 'packages' / 'vector-worker'
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(WORKER_PKG))

# ── CLI ───────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument('--ch-host',      default=None, help='ClickHouse host URL')
parser.add_argument('--ch-user',      default=None, help='ClickHouse user (default: default)')
parser.add_argument('--ch-password',  default=None, help='ClickHouse password')
parser.add_argument('--vector-url',   default=None, help='Upstash Vector REST URL')
parser.add_argument('--vector-token', default=None, help='Upstash Vector REST token')
parser.add_argument('--org',          default=None)
parser.add_argument('--since',        default='2000-01-01 00:00:00')
parser.add_argument('--weights',      default=None, help='Path to hgru.pt weights')
parser.add_argument('--wipe',         action='store_true',
                    help='Delete ALL existing vectors from the index before upserting')
args = parser.parse_args()

# Apply credentials to env (CLI args override env vars)
def _set(env_key, arg_val, fallback=''):
    val = arg_val or os.environ.get(env_key, fallback)
    os.environ[env_key] = val

_set('CLICKHOUSE_HOST',     args.ch_host,
     'https://y390vosagc.us-east1.gcp.clickhouse.cloud:8443')
_set('CLICKHOUSE_USER',     args.ch_user,     'default')
_set('CLICKHOUSE_PASSWORD', args.ch_password, '')
_set('UPSTASH_VECTOR_URL',  args.vector_url,
     'https://busy-macaque-12282-us1-vector.upstash.io')
_set('UPSTASH_VECTOR_TOKEN',args.vector_token,'')

# Validate
if not os.environ['CLICKHOUSE_PASSWORD']:
    print('ERROR: ClickHouse password required. Pass --ch-password or set CLICKHOUSE_PASSWORD.')
    sys.exit(1)
if not os.environ['UPSTASH_VECTOR_TOKEN']:
    print('ERROR: Upstash token required. Pass --vector-token or set UPSTASH_VECTOR_TOKEN.')
    sys.exit(1)

# ── Imports (after env is set) ────────────────────────────────────────────
import httpx as _httpx

from src.vectorizer import load_model, encode_session
from src.clickhouse import (
    get_all_orgs, get_sessions_updated_since, get_session_events, get_robust_params,
)
from src.upstash import build_vector_record, upsert_vectors
from src.constants import DEFAULT_ROBUST

def ts():
    return datetime.now(tz=timezone.utc).strftime('%H:%M:%S')

print(f'[{ts()}] run_vectorizer.py  since={args.since}  org={args.org}  wipe={args.wipe}')

# ── Optional index wipe ────────────────────────────────────────────────────
if args.wipe:
    print(f'[{ts()}] Wiping all vectors from index...')
    _base   = os.environ['UPSTASH_VECTOR_URL'].rstrip('/')
    _hdrs   = {'Authorization': f'Bearer {os.environ["UPSTASH_VECTOR_TOKEN"]}',
               'Content-Type': 'application/json'}

    # Scan all IDs via range then delete in batches
    cursor   = '0'
    all_ids: list[str] = []
    while True:
        r = _httpx.post(f'{_base}/range', headers=_hdrs,
                        json={'cursor': cursor, 'limit': 1000,
                              'includeVectors': False, 'includeMetadata': False},
                        timeout=30)
        r.raise_for_status()
        result  = r.json().get('result', {})
        vectors = result.get('vectors', [])
        all_ids.extend(v['id'] for v in vectors)
        cursor = result.get('nextCursor', '0')
        if not cursor or cursor == '0' or not vectors:
            break

    if all_ids:
        BATCH = 1000
        for i in range(0, len(all_ids), BATCH):
            chunk = all_ids[i:i + BATCH]
            r = _httpx.post(f'{_base}/delete', headers=_hdrs, json=chunk, timeout=30)
            r.raise_for_status()
        print(f'[{ts()}] Deleted {len(all_ids)} existing vectors')
    else:
        print(f'[{ts()}] Index already empty')

# ── Load model ────────────────────────────────────────────────────────────
model, device = load_model(args.weights)

# ── Process ───────────────────────────────────────────────────────────────
orgs = [args.org] if args.org else get_all_orgs()
if not orgs:
    print('No orgs found. Exiting.')
    sys.exit(0)

total_upserted = 0

for org_id in orgs:
    print(f'\n[{ts()}] org={org_id}')

    try:
        robust = get_robust_params(org_id)
    except Exception as e:
        print(f'  WARNING: robust params failed ({e}), using defaults')
        robust = DEFAULT_ROBUST

    session_ids = get_sessions_updated_since(args.since, org_id=org_id)
    print(f'  {len(session_ids)} sessions to process')

    records = []
    skipped = 0

    for sid in session_ids:
        try:
            events = get_session_events(sid)
            if not events:
                skipped += 1
                continue

            vec = encode_session(events, robust, model, device)
            if vec is None:
                skipped += 1
                continue

            first = events[0]
            records.append(build_vector_record(
                session_id     = sid,
                org_id         = org_id,
                client_id      = first.get('client_id', ''),
                hostname       = first.get('hostname', ''),
                ip_country     = first.get('ip_country'),
                ip_type        = first.get('ip_type'),
                device_type    = first.get('device_type'),
                is_webview     = first.get('is_webview'),
                received_at_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000),
                vector         = vec,
            ))
        except Exception as e:
            print(f'  ERROR session={sid}: {e}')
            skipped += 1

    if records:
        upsert_vectors(records)
        total_upserted += len(records)
        print(f'  Upserted {len(records)} vectors  (skipped={skipped})')
    else:
        print(f'  Nothing to upsert  (skipped={skipped})')

print(f'\n[{ts()}] Done. Total upserted: {total_upserted}')
