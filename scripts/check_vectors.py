"""
scripts/check_vectors.py
========================
Quick sanity check on the vectors currently in Upstash.
Prints: count, norm stats, pairwise similarity spread, pass/fail verdict.

Usage:
  python scripts/check_vectors.py \
    --vector-url  "https://busy-macaque-12282-us1-vector.upstash.io" \
    --vector-token "ABYFM..."

Or via env vars:
  export UPSTASH_VECTOR_URL=...
  export UPSTASH_VECTOR_TOKEN=...
  python scripts/check_vectors.py
"""
import argparse
import math
import os
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--vector-url',   default=None)
parser.add_argument('--vector-token', default=None)
parser.add_argument('--limit',        type=int, default=200)
args = parser.parse_args()

VECTOR_URL   = args.vector_url   or os.environ.get('UPSTASH_VECTOR_URL', '')
VECTOR_TOKEN = args.vector_token or os.environ.get('UPSTASH_VECTOR_TOKEN', '')

if not VECTOR_URL or not VECTOR_TOKEN:
    print('ERROR: --vector-url and --vector-token required (or set env vars)')
    sys.exit(1)

try:
    import httpx
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', 'httpx'])
    import httpx

headers = {'Authorization': f'Bearer {VECTOR_TOKEN}', 'Content-Type': 'application/json'}
base    = VECTOR_URL.rstrip('/')

# ── Fetch vectors ──────────────────────────────────────────────────────────
print('Fetching vectors from Upstash...')
resp = httpx.post(
    f'{base}/range',
    headers=headers,
    json={'cursor': '0', 'limit': args.limit,
          'includeMetadata': True, 'includeVectors': True},
    timeout=30,
)
resp.raise_for_status()
data    = resp.json()
vectors = data.get('result', {}).get('vectors', [])

n = len(vectors)
print(f'  Vectors fetched: {n}')
if n == 0:
    print('FAIL: no vectors found.')
    sys.exit(1)

# ── Check 1: norms (should all be ~1.0 for L2-normalised) ─────────────────
norms = []
for v in vectors:
    vec = v.get('vector') or []
    norm = math.sqrt(sum(x * x for x in vec))
    norms.append(norm)

min_norm = min(norms)
max_norm = max(norms)
print(f'\n[1] Norm check  (expect ~1.0 for all)')
print(f'    min={min_norm:.4f}  max={max_norm:.4f}')
norm_ok = min_norm > 0.99 and max_norm < 1.01
print(f'    {"PASS" if norm_ok else "FAIL — vectors are not L2-normalised"}')

# ── Check 2: dimension ─────────────────────────────────────────────────────
dims = set(len(v.get('vector') or []) for v in vectors)
print(f'\n[2] Dimension check  (expect 64)')
print(f'    dims found: {dims}')
dim_ok = dims == {64}
print(f'    {"PASS" if dim_ok else "FAIL — wrong dimension"}')

# ── Check 3: pairwise cosine similarity (should NOT all be ~1.0) ───────────
def dot(a, b):
    return sum(x * y for x, y in zip(a, b))

vecs = [v.get('vector') or [] for v in vectors]
sims = []
for i in range(min(n, 20)):
    for j in range(i + 1, min(n, 20)):
        if vecs[i] and vecs[j]:
            sims.append(dot(vecs[i], vecs[j]))  # L2-norm = 1 so dot = cosine

if sims:
    min_sim  = min(sims)
    max_sim  = max(sims)
    mean_sim = sum(sims) / len(sims)
    print(f'\n[3] Pairwise cosine similarity (first {min(n,20)} vectors)')
    print(f'    min={min_sim:.4f}  mean={mean_sim:.4f}  max={max_sim:.4f}')
    # Collapse: all sims > 0.99 means the model output is identical for all
    collapse = mean_sim > 0.97
    spread   = max_sim - min_sim
    if collapse:
        print('    FAIL — all vectors nearly identical (model collapsed or random init with no spread)')
    elif spread < 0.05:
        print('    WARN — low spread, vectors weakly differentiated')
    else:
        print(f'    PASS — vectors are differentiated (spread={spread:.4f})')

# ── Check 4: metadata presence ─────────────────────────────────────────────
meta_fields = ['org_id', 'session_id', 'device_type', 'ip_country']
print(f'\n[4] Metadata check')
missing_any = False
for v in vectors[:3]:
    m = v.get('metadata') or {}
    present = [f for f in meta_fields if m.get(f)]
    missing = [f for f in meta_fields if not m.get(f)]
    print(f'    {v["id"][:30]}...  present={present}  missing={missing}')
    if missing:
        missing_any = True

# ── Summary ────────────────────────────────────────────────────────────────
print('\n' + '─' * 50)
checks = [norm_ok, dim_ok, not collapse if sims else True]
passed = sum(checks)
total  = len(checks)
print(f'Result: {passed}/{total} checks passed')
if passed == total:
    print('Vectors look correct. Run generate_sessions.py to add more data, then retrain.')
else:
    print('Some checks failed — review above.')
