#!/bin/bash
# =============================================================================
# RunPod setup script for metricade H-GRU training
# Run once after the pod starts:
#   bash scripts/setup_runpod.sh
# =============================================================================
set -e

echo "=== Metricade RunPod Setup ==="
echo ""

# ── 1. Install Python deps ────────────────────────────────────────────────
echo "[1/4] Installing Python dependencies..."
pip install -q httpx numpy

# torch is pre-installed on RunPod PyTorch images — verify
python -c "import torch; print(f'  PyTorch {torch.__version__}  CUDA={torch.cuda.is_available()}  GPU={torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"none\"}')"

echo ""

# ── 2. Create output dirs ─────────────────────────────────────────────────
echo "[2/4] Creating output directories..."
mkdir -p packages/vector-worker/models
mkdir -p scripts/output/training
echo "  Done"
echo ""

# ── 3. Bootstrap model weights ────────────────────────────────────────────
echo "[3/4] Generating bootstrap weights..."
python scripts/bootstrap_hgru.py
echo ""

# ── 4. Verify ClickHouse connection ───────────────────────────────────────
echo "[4/4] Verifying ClickHouse connection..."
if [ -z "$CLICKHOUSE_PASSWORD" ]; then
  echo "  WARNING: CLICKHOUSE_PASSWORD not set."
  echo "  Set it before training:"
  echo "    export CLICKHOUSE_PASSWORD=hQzYu~_CqZ7gR"
else
  python - <<'PYEOF'
import os, sys
sys.path.insert(0, 'packages/vector-worker')
os.environ.setdefault('CLICKHOUSE_HOST', 'https://y390vosagc.us-east1.gcp.clickhouse.cloud:8443')
os.environ.setdefault('CLICKHOUSE_USER', 'default')
from src.clickhouse import get_all_orgs
orgs = get_all_orgs()
print(f"  Connected. Orgs found: {orgs}")
PYEOF
fi

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo ""
echo "  # Train the model (replace password if needed):"
echo "  python scripts/train_hgru.py \\"
echo "    --ch-password \"\$CLICKHOUSE_PASSWORD\" \\"
echo "    --epochs 500 \\"
echo "    --batch 32"
echo ""
echo "  # Run inference + push to Upstash:"
echo "  python scripts/run_vectorizer.py \\"
echo "    --ch-password \"\$CLICKHOUSE_PASSWORD\" \\"
echo "    --vector-url  \"https://busy-macaque-12282-us1-vector.upstash.io\" \\"
echo "    --vector-token \"ABYFMGJ1c3ktbWFjYXF1ZS0xMjI4Mi11czFhZG1pbk4yTTJZV0l6T1RBdFptTTROUzAwTWpnekxXSmpPR1V0TVdaall6UTFNVFJqWW1NMA==\""
echo ""
echo "  # Or set env vars and run without flags:"
echo "  export CLICKHOUSE_PASSWORD=hQzYu~_CqZ7gR"
echo "  export UPSTASH_VECTOR_URL=https://busy-macaque-12282-us1-vector.upstash.io"
echo "  export UPSTASH_VECTOR_TOKEN=ABYFMGJ1c3kt..."
echo "  python scripts/train_hgru.py"
echo "  python scripts/run_vectorizer.py"
