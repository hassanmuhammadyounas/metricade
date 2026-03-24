"""
scripts/evaluate_vectors.py
Evaluate 64-dim session vectors stored in Upstash Vector (busy-macaque-12282).
Outputs:
  scripts/output/vector_eval_report.txt
  scripts/output/vector_eval_data.json
"""
import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

# ── Auto-install dependencies ───────────────────────────────────────────────
def _install(*packages):
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', *packages])

try:
    from upstash_vector import Index
except ImportError:
    print('Installing upstash-vector...')
    _install('upstash-vector')
    from upstash_vector import Index

try:
    import numpy as np
except ImportError:
    print('Installing numpy...')
    _install('numpy')
    import numpy as np

try:
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import normalize
except ImportError:
    print('Installing scikit-learn...')
    _install('scikit-learn')
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import normalize

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
except ImportError:
    print('Installing matplotlib...')
    _install('matplotlib')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

# ── Config ──────────────────────────────────────────────────────────────────
VECTOR_URL   = 'https://busy-macaque-12282-us1-vector.upstash.io'
VECTOR_TOKEN = 'ABYIMGJ1c3ktbWFjYXF1ZS0xMjI4Mi11czFyZWFkb25seU1HRmxNelprTVRVdFlUY3paUzAwWWpCaExUbGxNV1F0TXpZNE5HRTROVEU1WmpRMg=='

OUTPUT_DIR  = os.path.join(os.path.dirname(__file__), 'output')
REPORT_PATH = os.path.join(OUTPUT_DIR, 'vector_eval_report.txt')
JSON_PATH   = os.path.join(OUTPUT_DIR, 'vector_eval_data.json')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Dual-output logger ───────────────────────────────────────────────────────
_log_file = open(REPORT_PATH, 'w')

def log(msg=''):
    print(msg)
    _log_file.write(msg + '\n')
    _log_file.flush()

def ts():
    return datetime.now(tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def divider(title=''):
    line = '─' * 60
    if title:
        log(f'\n{line}')
        log(f'  {title}')
        log(line)
    else:
        log(line)

# ── SETUP ───────────────────────────────────────────────────────────────────
log(f'[{ts()}] evaluate_vectors.py starting')
log(f'URL: {VECTOR_URL}')
divider()

index = Index(url=VECTOR_URL, token=VECTOR_TOKEN)

# ── STEP 1 — Fetch all vectors ───────────────────────────────────────────────
divider('STEP 1 — Fetch all vectors')
log(f'[{ts()}] Starting cursor pagination...')

all_vectors = []
cursor = '0'
while True:
    result = index.range(cursor=cursor, limit=100, include_vectors=True, include_metadata=True)
    batch = result.vectors
    all_vectors.extend(batch)
    next_cursor = result.next_cursor
    log(f'  fetched {len(batch)} vectors (cursor={cursor}) → next={next_cursor!r}')
    if not next_cursor or next_cursor == '0' or next_cursor == cursor:
        break
    cursor = next_cursor

total = len(all_vectors)
log(f'\n[{ts()}] Total vectors fetched: {total}')

if total == 0:
    log('ERROR: No vectors found. Exiting.')
    _log_file.close()
    sys.exit(1)

if total < 5:
    log(f'WARNING: Only {total} vectors found — results will have limited statistical meaning.')

ids      = [v.id for v in all_vectors]
matrix   = np.array([v.vector for v in all_vectors], dtype=np.float32)  # (N, 64)
metas    = [v.metadata or {} for v in all_vectors]
N, DIMS  = matrix.shape
log(f'Matrix shape: {N} × {DIMS}')

# ── STEP 2 — Per-vector stats ─────────────────────────────────────────────
divider('STEP 2 — Per-vector stats')
log(f'[{ts()}] Computing per-vector statistics...\n')
log(f'{"ID":<45} {"L2norm":>7} {"min":>8} {"max":>8} {"mean":>8} {"std":>8} {"NaN":>4} {"Inf":>4}')
log('-' * 100)

per_vector_stats = []
for i, vid in enumerate(ids):
    vec  = matrix[i]
    norm = float(np.linalg.norm(vec))
    vmin = float(np.min(vec))
    vmax = float(np.max(vec))
    vmean= float(np.mean(vec))
    vstd = float(np.std(vec))
    nans = int(np.sum(np.isnan(vec)))
    infs = int(np.sum(np.isinf(vec)))
    flag = ' *** NaN/Inf ***' if (nans or infs) else ''
    log(f'{vid:<45} {norm:>7.4f} {vmin:>8.4f} {vmax:>8.4f} {vmean:>8.4f} {vstd:>8.4f} {nans:>4} {infs:>4}{flag}')
    per_vector_stats.append({
        'id': vid, 'l2_norm': norm,
        'min': vmin, 'max': vmax, 'mean': vmean, 'std': vstd,
        'nan_count': nans, 'inf_count': infs,
    })

log(f'\n[{ts()}] Per-vector stats complete.')

# ── STEP 3 — Pairwise similarity matrix ───────────────────────────────────
divider('STEP 3 — Pairwise cosine similarity')
log(f'[{ts()}] Computing {N}×{N} cosine similarity matrix...')

normed   = normalize(matrix, norm='l2')
sim_mat  = normed @ normed.T  # (N, N)

# Extract upper triangle (excluding diagonal)
upper    = sim_mat[np.triu_indices(N, k=1)]
sim_mean = float(np.mean(upper))
sim_min  = float(np.min(upper))
sim_max  = float(np.max(upper))
sim_std  = float(np.std(upper))
n_high   = int(np.sum(upper > 0.95))
n_low    = int(np.sum(upper < 0.10))
n_pairs  = len(upper)

log(f'\n  Total pairs:          {n_pairs}')
log(f'  Mean similarity:      {sim_mean:.4f}')
log(f'  Min  similarity:      {sim_min:.4f}')
log(f'  Max  similarity:      {sim_max:.4f}')
log(f'  Std  similarity:      {sim_std:.4f}')
log(f'  Pairs > 0.95 (near-duplicate): {n_high}  ({100*n_high/max(n_pairs,1):.1f}%)')
log(f'  Pairs < 0.10 (well-separated): {n_low}   ({100*n_low/max(n_pairs,1):.1f}%)')
log(f'\n[{ts()}] Similarity matrix complete.')

sim_stats = {
    'n_pairs': n_pairs, 'mean': sim_mean, 'min': sim_min,
    'max': sim_max, 'std': sim_std,
    'pairs_gt_095': n_high, 'pairs_lt_010': n_low,
}

# ── STEP 4 — Clustering ───────────────────────────────────────────────────
divider('STEP 4 — KMeans clustering (k = 2, 3, 4, 5)')
log(f'[{ts()}] Running KMeans...')

clustering_results = {}
best_k, best_sil = 2, -1.0

for k in [2, 3, 4, 5]:
    if N < k:
        log(f'  k={k}: skipped (N={N} < k)')
        clustering_results[f'k{k}'] = {'skipped': True, 'reason': f'N={N} < k'}
        continue

    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = km.fit_predict(matrix)
    inertia = float(km.inertia_)

    if N > k:
        sil = float(silhouette_score(matrix, labels))
    else:
        sil = 0.0

    cluster_sizes = {int(c): int(np.sum(labels == c)) for c in range(k)}
    assignments   = {vid: int(labels[i]) for i, vid in enumerate(ids)}

    log(f'\n  k={k}:')
    log(f'    Inertia:           {inertia:.4f}')
    log(f'    Silhouette score:  {sil:.4f}')
    log(f'    Cluster sizes:     {cluster_sizes}')
    for vid, cl in assignments.items():
        log(f'      {vid}  →  cluster {cl}')

    clustering_results[f'k{k}'] = {
        'inertia': inertia, 'silhouette': sil,
        'cluster_sizes': cluster_sizes,
        'assignments': assignments,
    }
    if sil > best_sil:
        best_sil, best_k = sil, k

log(f'\n  Best k by silhouette: k={best_k} (score={best_sil:.4f})')
log(f'[{ts()}] Clustering complete.')

# ── STEP 5 — Metadata breakdown ───────────────────────────────────────────
divider('STEP 5 — Metadata breakdown')
log(f'[{ts()}] Analyzing metadata...\n')

groups_org    = {}
groups_device = {}

for i, vid in enumerate(ids):
    meta = metas[i]
    log(f'  {vid}')
    for k, v in meta.items():
        log(f'    {k}: {v}')
    log('')

    org    = meta.get('org_id',     'unknown')
    device = meta.get('device_type','unknown')
    groups_org.setdefault(org, []).append(vid)
    groups_device.setdefault(device, []).append(vid)

log('  By org_id:')
for org, vids in groups_org.items():
    log(f'    {org}: {len(vids)} vectors')

log('\n  By device_type:')
for dev, vids in groups_device.items():
    log(f'    {dev}: {len(vids)} vectors')

log(f'\n[{ts()}] Metadata breakdown complete.')

metadata_groups = {
    'by_org_id':     {k: len(v) for k, v in groups_org.items()},
    'by_device_type':{k: len(v) for k, v in groups_device.items()},
}

# ── STEP 6 — Dimension variance analysis ──────────────────────────────────
divider('STEP 6 — Per-dimension variance analysis')
log(f'[{ts()}] Computing per-dimension variance across {N} vectors...\n')

dim_var  = np.var(matrix, axis=0)       # (64,)
dim_mean = np.mean(matrix, axis=0)      # (64,)

top10_high = np.argsort(dim_var)[::-1][:10]
top10_low  = np.argsort(dim_var)[:10]
n_dead     = int(np.sum(dim_var < 0.001))

log('  Top 10 HIGHEST variance dims (most informative):')
log(f'  {"dim":>4}  {"variance":>10}  {"mean":>8}')
for d in top10_high:
    log(f'  {d:>4}  {dim_var[d]:>10.6f}  {dim_mean[d]:>8.4f}')

log('\n  Top 10 LOWEST variance dims (potentially dead/useless):')
log(f'  {"dim":>4}  {"variance":>10}  {"mean":>8}')
for d in top10_low:
    log(f'  {d:>4}  {dim_var[d]:>10.6f}  {dim_mean[d]:>8.4f}')

log(f'\n  Dims with variance < 0.001 (near-dead): {n_dead} / {DIMS}')
log(f'\n[{ts()}] Variance analysis complete.')

# ── OUTPUT ─────────────────────────────────────────────────────────────────
divider('SUMMARY')
log(f'  Total vectors:        {total}')
log(f'  Dimensions:           {DIMS}')
log(f'  Near-dead dims (<0.001 var): {n_dead}')
log(f'  Mean pairwise similarity:    {sim_mean:.4f}')
log(f'  Best clustering k:    {best_k}  (silhouette={best_sil:.4f})')
log(f'\n[{ts()}] Report written to: {REPORT_PATH}')
log(f'[{ts()}] JSON written to:   {JSON_PATH}')

_log_file.close()

# ── Write JSON ──────────────────────────────────────────────────────────────
output_json = {
    'total_vectors': total,
    'dimensions': DIMS,
    'per_vector_stats': per_vector_stats,
    'similarity_matrix_stats': sim_stats,
    'clustering': clustering_results,
    'best_k': best_k,
    'dimension_variance': dim_var.tolist(),
    'dimension_mean': dim_mean.tolist(),
    'near_dead_dims': n_dead,
    'metadata_groups': metadata_groups,
}

with open(JSON_PATH, 'w') as f:
    json.dump(output_json, f, indent=2)

print(f'\nDone. Report: {REPORT_PATH}')
print(f'       JSON:  {JSON_PATH}')
