"""
vector-worker — Fly.io Python worker
Polls ClickHouse every 5 minutes, produces 64-dim session vectors,
upserts to Upstash Vector with prefix ev_{session_id}.

Vector layout (64 dims):
  [0:14]  session context
  [14:39] mean-pooled event features (25 dims)
  [39:64] mean-pooled event feature mask (25 dims)
"""
import logging
import os
import time
from datetime import datetime, timedelta, timezone

from .clickhouse import get_all_orgs, get_session_events, get_sessions_updated_since, get_robust_params
from .upstash import build_vector_record, upsert_vectors
from .vectorizer import encode_session

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [vector-worker] %(levelname)s %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%SZ',
)
log = logging.getLogger(__name__)

POLL_INTERVAL_S    = int(os.environ.get('POLL_INTERVAL_S', '300'))  # 5 min
LOOKBACK_OVERLAP_S = 120  # extra 2-min overlap to catch late-arriving rows
WATERMARK_FILE     = os.environ.get('WATERMARK_FILE', '/app/watermark.txt')
EPOCH              = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _load_watermark() -> datetime:
    """Load watermark from disk; return EPOCH on first boot (triggers full backfill)."""
    try:
        with open(WATERMARK_FILE) as f:
            return datetime.fromisoformat(f.read().strip())
    except (FileNotFoundError, ValueError):
        log.info('No watermark found — backfilling all sessions from epoch')
        return EPOCH


def _save_watermark(ts: datetime) -> None:
    with open(WATERMARK_FILE, 'w') as f:
        f.write(ts.isoformat())


def run_once(since: datetime) -> datetime:
    """
    Process all sessions updated since `since`.
    Returns the new watermark (now at start of this run).
    """
    now = datetime.now(tz=timezone.utc)
    since_iso = since.strftime('%Y-%m-%d %H:%M:%S')

    orgs = get_all_orgs()
    if not orgs:
        log.info('No active orgs in last 24h')
        return now

    total_upserted = 0

    for org_id in orgs:
        try:
            robust = get_robust_params(org_id)
        except Exception as e:
            log.warning(f'org={org_id} robust params failed: {e}, using defaults')
            from .constants import DEFAULT_ROBUST
            robust = DEFAULT_ROBUST

        session_ids = get_sessions_updated_since(since_iso, org_id=org_id)
        if not session_ids:
            continue

        log.info(f'org={org_id} processing {len(session_ids)} sessions since {since_iso}')

        records = []
        for sid in session_ids:
            try:
                events = get_session_events(sid)
                if not events:
                    continue

                vec = encode_session(events, robust)
                if vec is None:
                    continue

                first = events[0]
                record = build_vector_record(
                    session_id  = sid,
                    org_id      = org_id,
                    client_id   = first.get('client_id', ''),
                    hostname    = first.get('hostname', ''),
                    ip_country  = first.get('ip_country'),
                    ip_type     = first.get('ip_type'),
                    device_type = first.get('device_type'),
                    is_webview  = first.get('is_webview'),
                    received_at_ms = int(now.timestamp() * 1000),
                    vector      = vec,
                )
                records.append(record)

            except Exception as e:
                log.error(f'session={sid} encode failed: {e}')

        if records:
            upsert_vectors(records)
            total_upserted += len(records)
            log.info(f'org={org_id} upserted {len(records)} vectors')

    log.info(f'Run complete. Total upserted: {total_upserted}')
    _save_watermark(now)
    return now


def main() -> None:
    log.info(f'Starting vector-worker (poll_interval={POLL_INTERVAL_S}s)')

    watermark = _load_watermark()

    while True:
        try:
            # Apply overlap to avoid missing late-arriving rows
            since = watermark - timedelta(seconds=LOOKBACK_OVERLAP_S)
            watermark = run_once(since)
        except Exception as e:
            log.error(f'Poll cycle failed: {e}')

        time.sleep(POLL_INTERVAL_S)


if __name__ == '__main__':
    main()
