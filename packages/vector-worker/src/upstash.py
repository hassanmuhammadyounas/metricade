import os
import httpx

BATCH_SIZE = 100  # Upstash Vector upsert batch limit


def _headers() -> dict:
    # Read lazily so env vars set after module import are picked up
    token = os.environ.get('UPSTASH_VECTOR_TOKEN', '')
    return {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}


def _url(path: str) -> str:
    base = os.environ.get('UPSTASH_VECTOR_URL', '').rstrip('/')
    return f'{base}{path}'


def upsert_vectors(vectors: list[dict]) -> None:
    """
    Upsert a list of vectors to Upstash Vector.
    Each item: { 'id': str, 'vector': list[float], 'metadata': dict }
    """
    if not vectors:
        return

    for i in range(0, len(vectors), BATCH_SIZE):
        batch = vectors[i:i + BATCH_SIZE]
        resp = httpx.post(_url('/upsert'), headers=_headers(), json=batch, timeout=30)
        resp.raise_for_status()


def build_vector_record(
    session_id: str,
    org_id: str,
    client_id: str,
    hostname: str,
    ip_country: str | None,
    ip_type: str | None,
    device_type: str | None,
    is_webview: bool | None,
    received_at_ms: int,
    vector: list[float],
) -> dict:
    return {
        'id': f'ev_{session_id}',
        'vector': vector,
        'metadata': {
            'org_id':      org_id,
            'session_id':  session_id,
            'client_id':   client_id,
            'hostname':    hostname,
            'ip_country':  ip_country,
            'ip_type':     ip_type,
            'device_type': device_type,
            'is_webview':  is_webview,
            'received_at': received_at_ms,
        },
    }
