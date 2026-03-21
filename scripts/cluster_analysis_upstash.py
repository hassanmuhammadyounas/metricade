#!/usr/bin/env python3
"""
Behavioral Transformer — Embedding Analysis
Fetches pre-computed 192-dim session embeddings directly from Upstash Vector,
runs UMAP + K-Means clustering, and produces fraud/anomaly analysis outputs.
"""

import os, sys, random, warnings, subprocess
warnings.filterwarnings('ignore')
import numpy as np
import pandas as pd

def check_and_install(packages):
    for pkg, import_name in packages:
        try:
            __import__(import_name)
        except ImportError:
            print(f"  Installing {pkg}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

print("Checking dependencies...")
check_and_install([("torch","torch"),("numpy","numpy"),("pandas","pandas"),
    ("scikit-learn","sklearn"),("umap-learn","umap"),("matplotlib","matplotlib"),
    ("seaborn","seaborn"),("upstash-vector","upstash_vector")])
print("All dependencies satisfied.\n")

import torch
if torch.cuda.is_available():
    device = torch.device("cuda")
elif torch.backends.mps.is_available():
    device = torch.device("mps")
else:
    device = torch.device("cpu")

from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score, davies_bouldin_score
from sklearn.preprocessing import normalize
import umap as umap_lib
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns

SEED = 42
np.random.seed(SEED); random.seed(SEED)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output", "cluster_upstash")
os.makedirs(OUTPUT_DIR, exist_ok=True)

CSV_FILE    = os.path.join(OUTPUT_DIR, "ml_pixel_raw_events.csv")
OUTPUT_PNGS = [os.path.join(OUTPUT_DIR, f) for f in
    ["umap_clusters.png", "cluster_feature_heatmap.png", "clustering_scores.png"]]

print("=" * 80)
print("STEP 0: CLEANUP + FETCH VECTORS FROM UPSTASH")
print("=" * 80)
for f in [CSV_FILE] + OUTPUT_PNGS:
    if os.path.exists(f): os.remove(f)

import csv as _csv, json as _json
from upstash_vector import Index as _Index

UPSTASH_VECTOR_REST_URL   = "https://bright-tiger-54944-us1-vector.upstash.io"
UPSTASH_VECTOR_REST_TOKEN = "ABYIMGJyaWdodC10aWdlci01NDk0NC11czFyZWFkb25seU9EVm1PREptWkRrdFlqWm1PQzAwTVdRNUxXSXhPRGd0TXpoaFpXTTROVEprWm1abA=="
BATCH_SIZE = 1000

print("[0.2] Connecting to Upstash Vector...")
_index = _Index(url=UPSTASH_VECTOR_REST_URL, token=UPSTASH_VECTOR_REST_TOKEN)
_info  = _index.info()
print(f"      Total vectors : {_info.vector_count}")
print(f"      Dimension     : {_info.dimension}")

_org_counts = {}; _country_counts = {}; _hostname_counts = {}
_cursor = ""
while True:
    _result = _index.range(cursor=_cursor, limit=BATCH_SIZE,
        include_vectors=False, include_metadata=True, include_data=False)
    for _v in _result.vectors:
        if not _v.metadata: continue
        _oid  = str(_v.metadata.get("org_id", ""))
        _cty  = str(_v.metadata.get("ip_country", "(unknown)"))
        _host = str(_v.metadata.get("hostname", "(unknown)"))
        if _oid:
            _org_counts[_oid] = _org_counts.get(_oid, 0) + 1
            _country_counts.setdefault(_oid, {})
            _country_counts[_oid][_cty] = _country_counts[_oid].get(_cty, 0) + 1
            _hostname_counts.setdefault(_oid, {})
            _hostname_counts[_oid].setdefault(_cty, {})
            _hostname_counts[_oid][_cty][_host] = _hostname_counts[_oid][_cty].get(_host, 0) + 1
    if _result.next_cursor == "": break
    _cursor = _result.next_cursor

def _pick(label, counts):
    _items = sorted(counts.items())
    print(f"\n  {'#':<4} {label:<30} sessions")
    print("  " + "-" * 48)
    for _i, (_val, _cnt) in enumerate(_items, 1):
        print(f"  {_i:<4} {_val:<30} {_cnt}")
    print()
    while True:
        try:
            _c = int(input(f"  Select {label} [1–{len(_items)}]: ").strip())
            if 1 <= _c <= len(_items): return _items[_c - 1][0]
        except ValueError:
            pass
        print(f"  Please enter a number between 1 and {len(_items)}.")

_selected_org      = _pick("org_id", _org_counts)
_selected_country  = _pick("ip_country", _country_counts.get(_selected_org, {}))
_selected_hostname = _pick("hostname", _hostname_counts.get(_selected_org, {}).get(_selected_country, {}))

print(f"\n  Fetching: org={_selected_org}, country={_selected_country}, hostname={_selected_hostname}")
_all_vectors = []; _cursor = ""; _page = 0
while True:
    _page += 1
    _result = _index.range(cursor=_cursor, limit=BATCH_SIZE,
        include_vectors=True, include_metadata=True, include_data=True)
    for _v in _result.vectors:
        if not _v.metadata: continue
        if str(_v.metadata.get("org_id",""))      != _selected_org:      continue
        if str(_v.metadata.get("ip_country",""))   != _selected_country:  continue
        if str(_v.metadata.get("hostname",""))     != _selected_hostname: continue
        _all_vectors.append(_v)
    print(f"      Page {_page}: {len(_all_vectors)} matching so far")
    if _result.next_cursor == "": break
    _cursor = _result.next_cursor
print(f"      Done. {len(_all_vectors)} vectors retrieved.")

_meta_keys = []; _seen_keys = set()
for _v in _all_vectors:
    if _v.metadata:
        for _k in _v.metadata:
            if _k not in _seen_keys: _meta_keys.append(_k); _seen_keys.add(_k)

_dim = len(_all_vectors[0].vector) if _all_vectors[0].vector else 0
_vec_cols = [f"vec_{i}" for i in range(_dim)]
_has_data = any(_v.data for _v in _all_vectors)
_fieldnames = ["id"] + _meta_keys + (["data"] if _has_data else []) + _vec_cols

with open(CSV_FILE, "w", newline="", encoding="utf-8") as _f:
    _writer = _csv.DictWriter(_f, fieldnames=_fieldnames)
    _writer.writeheader()
    for _v in _all_vectors:
        _row = {"id": _v.id}
        if _v.metadata:
            for _k in _meta_keys:
                _val = _v.metadata.get(_k, "")
                _row[_k] = _json.dumps(_val) if isinstance(_val,(dict,list)) else _val
        if _has_data: _row["data"] = _v.data or ""
        if _v.vector:
            for _i, _val in enumerate(_v.vector): _row[f"vec_{_i}"] = _val
        _writer.writerow(_row)
print(f"      Saved: {CSV_FILE}")

print("\n" + "=" * 80)
print("STEP 1: LOAD EMBEDDINGS")
print("=" * 80)
df = pd.read_csv(CSV_FILE)
vec_cols = [c for c in df.columns if c.startswith("vec_")]
X_raw = df[vec_cols].values.astype(np.float32)
X = normalize(X_raw, norm="l2")
print(f"      Embeddings shape : {X.shape}")

def col(name, default="unknown"):
    return df[name].fillna(default).astype(str).values if name in df.columns \
           else np.array([default] * len(df))

session_ids  = col("session_id","?")
ip_types     = col("ip_type","unknown")
device_types = col("device_type","unknown")
ip_countries = col("ip_country","??")
is_webview   = np.array([s.strip().lower()=="true" for s in col("is_webview","false")])
received_at  = pd.to_datetime(df["received_at"].astype(float), unit="ms", utc=True) \
               if "received_at" in df.columns else None

print("\n" + "=" * 80)
print("STEP 2: UMAP")
print("=" * 80)
n_neighbors = min(15, max(2, len(X) // 8))
print(f"[2.1] Running UMAP (n_neighbors={n_neighbors})...")
reducer = umap_lib.UMAP(n_neighbors=n_neighbors, min_dist=0.1, metric="cosine", random_state=SEED)
umap_2d = reducer.fit_transform(X)

print("\n" + "=" * 80)
print("STEP 3: K-MEANS CLUSTERING")
print("=" * 80)
K_RANGE = list(range(2, min(9, max(3, len(X) // 5 + 1))))
sil_scores = []; db_scores = []; clusterings = {}
for k in K_RANGE:
    km = KMeans(n_clusters=k, random_state=SEED, n_init=20)
    labels = km.fit_predict(X)
    sil = silhouette_score(X, labels, metric="cosine")
    db  = davies_bouldin_score(X, labels)
    sil_scores.append(sil); db_scores.append(db); clusterings[k] = (labels, km)
    print(f"  K={k}  Silhouette={sil:.4f}  DB={db:.4f}")

best_idx = int(np.argmax(sil_scores))
K_BEST = K_RANGE[best_idx]
best_labels, best_km = clusterings[K_BEST]
sizes = {c: int((best_labels==c).sum()) for c in range(K_BEST)}
print(f"\n  Best K={K_BEST}  Sil={sil_scores[best_idx]:.4f}")
print(f"  Cluster sizes: {sizes}")

print("\n" + "=" * 80)
print("STEP 4: PER-CLUSTER METADATA")
print("=" * 80)
SUSP_IPTYPES = {"datacenter","unknown"}; SUSP_DEVICES = {"bot","unknown"}
cluster_stats = {}
for cid in range(K_BEST):
    mask = best_labels == cid; n = int(mask.sum()); embs = X[mask]
    dots = embs @ embs.T; np.fill_diagonal(dots, np.nan)
    intra_cos = float(np.nanmean(dots)) if n > 1 else 1.0
    centroid = embs.mean(axis=0); centroid /= (np.linalg.norm(centroid)+1e-9)
    avg_dist = float((1.0-(embs@centroid)).mean())
    ipt = ip_types[mask]; devt = device_types[mask]
    cntry = ip_countries[mask]; wv = is_webview[mask]
    dc_pct = float(np.isin(ipt,list(SUSP_IPTYPES)).sum()/n*100)
    bot_pct = float(np.isin(devt,list(SUSP_DEVICES)).sum()/n*100)
    webview_pct = float(wv.sum()/n*100)
    uniq_c, cnt_c = np.unique(cntry, return_counts=True)
    top_country = uniq_c[np.argmax(cnt_c)]; top_cntry_pct = float(np.max(cnt_c)/n*100)
    ipt_dist = {str(v):int(c) for v,c in zip(*np.unique(ipt,return_counts=True))}
    devt_dist = {str(v):int(c) for v,c in zip(*np.unique(devt,return_counts=True))}
    hour_mean = float(received_at.iloc[mask].dt.hour.values.mean()) if received_at is not None else None
    cluster_stats[cid] = dict(n=n, intra_cos=intra_cos, avg_dist=avg_dist,
        dc_pct=dc_pct, bot_pct=bot_pct, webview_pct=webview_pct,
        top_country=top_country, top_cntry_pct=top_cntry_pct,
        hour_mean=hour_mean, ipt_dist=ipt_dist, devt_dist=devt_dist)

print(f"\n  {'Clu':<5}{'N':<6}{'IntraCos':<12}{'AvgDist':<10}{'DC%':<8}{'Bot%':<8}{'TopCtry'}")
print("  "+"-"*60)
for cid,st in sorted(cluster_stats.items()):
    print(f"  {cid:<5}{st['n']:<6}{st['intra_cos']:<12.4f}{st['avg_dist']:<10.4f}"
          f"{st['dc_pct']:<8.1f}{st['bot_pct']:<8.1f}{st['top_country']} {st['top_cntry_pct']:.1f}%")

print("\n" + "=" * 80)
print("STEP 5: FRAUD SCORING")
print("=" * 80)
MAX_FRAUD_SCORE = 14; fraud_scores = {}
for cid, st in cluster_stats.items():
    score = 0; reasons = []
    if st['intra_cos'] > 0.85: score+=3; reasons.append(f"Very high intra-cos ({st['intra_cos']:.3f})")
    elif st['intra_cos'] > 0.70: score+=1; reasons.append(f"Elevated intra-cos ({st['intra_cos']:.3f})")
    if st['dc_pct'] > 50: score+=3; reasons.append(f"{st['dc_pct']:.1f}% datacenter IPs")
    elif st['dc_pct'] > 20: score+=1; reasons.append(f"{st['dc_pct']:.1f}% datacenter IPs")
    if st['bot_pct'] > 30: score+=3; reasons.append(f"{st['bot_pct']:.1f}% bot/unknown device")
    elif st['bot_pct'] > 0: score+=1; reasons.append(f"{st['bot_pct']:.1f}% bot/unknown device")
    if st['webview_pct'] > 50: score+=2; reasons.append(f"{st['webview_pct']:.1f}% WebView")
    if st['top_cntry_pct'] > 90 and st['n'] >= 5: score+=1; reasons.append(f"Country concentration {st['top_country']}={st['top_cntry_pct']:.1f}%")
    if st['avg_dist'] < 0.05 and st['n'] >= 3: score+=2; reasons.append(f"Embedding collapse dist={st['avg_dist']:.4f}")
    fraud_scores[cid] = {"score":score,"reasons":reasons,**st}

for cid in sorted(fraud_scores, key=lambda c:-fraud_scores[c]["score"]):
    st = fraud_scores[cid]
    print(f"  Cluster {cid}: {st['score']}/{MAX_FRAUD_SCORE}  n={st['n']}  "
          f"intra_cos={st['intra_cos']:.3f}  dc%={st['dc_pct']:.1f}  bot%={st['bot_pct']:.1f}")
    for r in st['reasons']: print(f"    - {r}")

print("\n" + "=" * 80)
print("STEP 6: VISUALISATIONS")
print("=" * 80)
cmap_clusters = plt.cm.tab10(np.linspace(0, 0.9, K_BEST))
unique_countries = sorted(np.unique(ip_countries))

fig, ax = plt.subplots(figsize=(10, 8))
for cid in range(K_BEST):
    c_mask = best_labels == cid
    ax.scatter(umap_2d[c_mask,0], umap_2d[c_mask,1],
               color=cmap_clusters[cid], marker="o",
               s=100, alpha=0.8, edgecolors="black", linewidths=0.4,
               label=f"Cluster {cid}  (n={c_mask.sum()})")
    for idx in np.where(c_mask)[0]:
        ax.annotate(ip_countries[idx], (umap_2d[idx,0], umap_2d[idx,1]),
                    fontsize=6, ha="center", va="bottom",
                    xytext=(0,4), textcoords="offset points", alpha=0.7)
ax.set_xlabel("UMAP-1"); ax.set_ylabel("UMAP-2")
ax.set_title(f"Session Clusters (UMAP) — {_selected_org} / {_selected_country} / {_selected_hostname}")
ax.legend(bbox_to_anchor=(1.02,1), loc="upper left", fontsize=9)
plt.tight_layout()
out = os.path.join(OUTPUT_DIR, "umap_clusters.png")
plt.savefig(out, dpi=150, bbox_inches="tight"); plt.close()
print(f"      Saved: {out}")

feat_keys  = ["intra_cos","avg_dist","dc_pct","bot_pct","webview_pct","top_cntry_pct"]
feat_names = ["Intra-cos","Avg Dist","DC IP%","Bot%","WebView%","Top Ctry%"]
hmap_rows = [[cluster_stats[c][k] for k in feat_keys] for c in sorted(cluster_stats)]
row_labels = [f"Cluster {c} (n={cluster_stats[c]['n']})" for c in sorted(cluster_stats)]
hmap_arr = np.array(hmap_rows, dtype=float)
col_max = hmap_arr.max(axis=0); col_max[col_max==0] = 1.0
hmap_norm = hmap_arr / col_max
fig, ax = plt.subplots(figsize=(12, max(3, len(row_labels))))
sns.heatmap(hmap_norm, annot=hmap_arr, fmt=".2f", cmap="RdYlBu_r",
            xticklabels=feat_names, yticklabels=row_labels, ax=ax, linewidths=0.5)
ax.set_title("Cluster Feature Profiles")
plt.tight_layout()
out = os.path.join(OUTPUT_DIR, "cluster_feature_heatmap.png")
plt.savefig(out, dpi=150, bbox_inches="tight"); plt.close()
print(f"      Saved: {out}")

fig, axes = plt.subplots(1,2,figsize=(10,4))
axes[0].plot(K_RANGE, sil_scores, "o-", color="steelblue", linewidth=2)
axes[0].axvline(K_BEST, color="crimson", linestyle="--", label=f"Best K={K_BEST}")
axes[0].set_xlabel("K"); axes[0].set_ylabel("Silhouette"); axes[0].set_title("Silhouette vs K"); axes[0].legend()
axes[1].plot(K_RANGE, db_scores, "o-", color="seagreen", linewidth=2)
axes[1].axvline(K_BEST, color="crimson", linestyle="--", label=f"Best K={K_BEST}")
axes[1].set_xlabel("K"); axes[1].set_ylabel("Davies-Bouldin"); axes[1].set_title("DB Score vs K"); axes[1].legend()
plt.tight_layout()
out = os.path.join(OUTPUT_DIR, "clustering_scores.png")
plt.savefig(out, dpi=150, bbox_inches="tight"); plt.close()
print(f"      Saved: {out}")

print("\n" + "=" * 80)
print("ANALYSIS COMPLETE")
print("=" * 80)
print(f"  Sessions   : {len(X)}")
print(f"  Best K     : {K_BEST}  Silhouette={sil_scores[best_idx]:.4f}")
print(f"  Output dir : {OUTPUT_DIR}")
